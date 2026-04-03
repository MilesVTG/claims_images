terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# ── Enable Required APIs ─────────────────────────────────────────────
resource "google_project_service" "apis" {
  for_each = toset([
    "run.googleapis.com",
    "sqladmin.googleapis.com",
    "secretmanager.googleapis.com",
    "artifactregistry.googleapis.com",
    "vision.googleapis.com",
    "pubsub.googleapis.com",
    "vpcaccess.googleapis.com",
    "servicenetworking.googleapis.com",
    "cloudbuild.googleapis.com",
  ])
  service            = each.value
  disable_on_destroy = false
}

# ── VPC (private networking for Cloud SQL) ───────────────────────────
resource "google_compute_network" "vpc" {
  name                    = "claims-vpc"
  auto_create_subnetworks = true
}

resource "google_compute_global_address" "private_ip" {
  name          = "claims-sql-ip"
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 16
  network       = google_compute_network.vpc.id
}

resource "google_service_networking_connection" "private_vpc" {
  network                 = google_compute_network.vpc.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.private_ip.name]
}

# ── Cloud SQL Postgres 17 ────────────────────────────────────────────
resource "google_sql_database_instance" "fraud_db" {
  name             = "fraud-detection-db"
  database_version = "POSTGRES_17"
  region           = var.region

  depends_on = [google_service_networking_connection.private_vpc]

  settings {
    tier              = var.db_tier
    edition           = "ENTERPRISE"
    availability_type = "ZONAL"

    ip_configuration {
      ipv4_enabled    = false
      private_network = google_compute_network.vpc.id
    }

    backup_configuration {
      enabled                        = true
      point_in_time_recovery_enabled = true
    }
  }

  deletion_protection = var.deletion_protection
}

resource "google_sql_database" "fraud_detection" {
  name     = "fraud_detection"
  instance = google_sql_database_instance.fraud_db.name
}

resource "google_sql_user" "fraud_user" {
  name     = "fraud_user"
  instance = google_sql_database_instance.fraud_db.name
  password = var.db_password
}

# ── GCS (Photo storage) ──────────────────────────────────────────────
resource "google_storage_bucket" "photos" {
  name                        = "${var.project_id}-claim-photos"
  location                    = "US"
  uniform_bucket_level_access = true
  versioning { enabled = true }

  lifecycle_rule {
    action {
      type          = "SetStorageClass"
      storage_class = "NEARLINE"
    }
    condition {
      age = 90
    }
  }
}

# ── Pub/Sub (GCS upload events) ──────────────────────────────────────
resource "google_pubsub_topic" "photo_uploads" {
  name = "photo-uploads"
}

resource "google_pubsub_subscription" "worker_sub" {
  name  = "worker-photo-sub"
  topic = google_pubsub_topic.photo_uploads.id

  # Push endpoint is set after first deploy via deploy.sh
  # gcloud pubsub subscriptions update worker-photo-sub \
  #   --push-endpoint="${WORKER_URL}/process" \
  #   --push-auth-service-account=claims-worker@${PROJECT_ID}.iam.gserviceaccount.com

  ack_deadline_seconds = 300
}

# Grant GCS service account permission to publish to Pub/Sub
data "google_storage_project_service_account" "gcs_sa" {}

resource "google_pubsub_topic_iam_member" "gcs_publish" {
  topic  = google_pubsub_topic.photo_uploads.id
  role   = "roles/pubsub.publisher"
  member = "serviceAccount:${data.google_storage_project_service_account.gcs_sa.email_address}"
}

resource "google_storage_notification" "photo_notification" {
  bucket         = google_storage_bucket.photos.name
  payload_format = "JSON_API_V1"
  topic          = google_pubsub_topic.photo_uploads.id
  event_types    = ["OBJECT_FINALIZE"]

  depends_on = [google_pubsub_topic_iam_member.gcs_publish]
}

# ── Artifact Registry (Docker image storage) ─────────────────────────
resource "google_artifact_registry_repository" "claims_images" {
  location      = var.region
  repository_id = "claims-images"
  format        = "DOCKER"
}

# ── Secret Manager ───────────────────────────────────────────────────
resource "google_secret_manager_secret" "gemini_api_key" {
  secret_id = "gemini-api-key"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret" "session_secret" {
  secret_id = "session-secret"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret" "exchange_password" {
  secret_id = "exchange-password"
  replication {
    auto {}
  }
}

# ── Service Accounts ─────────────────────────────────────────────────
resource "google_service_account" "api" {
  account_id   = "claims-api"
  display_name = "Claims API Service"
}

resource "google_service_account" "worker" {
  account_id   = "claims-worker"
  display_name = "Claims Worker Service"
}

# ── IAM Bindings ─────────────────────────────────────────────────────
# API: read/write GCS, connect Cloud SQL, read secrets
resource "google_project_iam_member" "api_storage" {
  project = var.project_id
  role    = "roles/storage.objectAdmin"
  member  = "serviceAccount:${google_service_account.api.email}"
}

resource "google_project_iam_member" "api_sql" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.api.email}"
}

resource "google_project_iam_member" "api_secrets" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.api.email}"
}

# Worker: read GCS, connect Cloud SQL, read secrets, use Vision API
resource "google_project_iam_member" "worker_storage" {
  project = var.project_id
  role    = "roles/storage.objectViewer"
  member  = "serviceAccount:${google_service_account.worker.email}"
}

resource "google_project_iam_member" "worker_sql" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.worker.email}"
}

resource "google_project_iam_member" "worker_secrets" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.worker.email}"
}

# ── VPC Connector (Cloud Run -> Cloud SQL private access) ────────────
resource "google_vpc_access_connector" "connector" {
  name          = "claims-vpc-connector"
  region        = var.region
  network       = google_compute_network.vpc.name
  ip_cidr_range = "10.8.0.0/28"
  min_instances = 2
  max_instances = 3
}

# ── Cloud Run services are NOT managed by Terraform ──────────────────
# Cloud Run deployments are handled by deploy.sh (Section 17B).
# Terraform creates the infrastructure that Cloud Run services use:
#   - Artifact Registry, GCS, Cloud SQL, Pub/Sub, Secret Manager,
#     VPC, IAM service accounts + bindings, API enablement.
# deploy.sh creates/updates the actual Cloud Run services because
# they change frequently (new image on every deploy) and Terraform
# would create state drift on every gcloud run deploy.
