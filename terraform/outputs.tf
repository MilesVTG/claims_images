output "photos_bucket" {
  value = google_storage_bucket.photos.name
}

output "db_connection_name" {
  value = google_sql_database_instance.fraud_db.connection_name
}

output "artifact_registry_repo" {
  value = google_artifact_registry_repository.claims_images.id
}

output "vpc_connector_name" {
  value = google_vpc_access_connector.connector.name
}

output "api_service_account" {
  value = google_service_account.api.email
}

output "worker_service_account" {
  value = google_service_account.worker.email
}
