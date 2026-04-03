#!/usr/bin/env bash
set -euo pipefail

###############################################################################
# provision.sh — One-time GCP infrastructure setup
###############################################################################
#
# WHAT:
#   Creates all GCP infrastructure for the Claims Photo Fraud Detection
#   system. Enables APIs, creates Artifact Registry, pushes secrets to
#   Secret Manager, and runs Terraform to create Cloud SQL, VPC, GCS,
#   Pub/Sub, and IAM resources.
#
# WHY:
#   Everything in prod must be script-created, not click-created. This is
#   the single entry point for standing up the project from zero.
#
# WHEN TO RUN:
#   - Once, on initial project setup
#   - After wiping infrastructure (terraform destroy)
#   - When adding new secrets to Secret Manager
#   Run preflight.sh first to catch misconfig before this burns time.
#
# PREREQUISITES:
#   - gcloud authenticated: gcloud auth login mchick@vtg-services.net
#   - Project set: gcloud config set project propane-landing-491118-r7
#   - .env file with secrets (GEMINI_API_KEY, DB_PASSWORD, SESSION_SECRET,
#     EXCHANGE_PASSWORD) — provision reads from .env, no manual typing
#   - terraform installed: brew install terraform
#
# WHAT IT DOES (in order):
#   1. Enables 10 GCP APIs (one at a time, with progress output)
#   2. Creates Artifact Registry repo (claims-images) if not exists
#   3. Reads secrets from .env, pushes to GCP Secret Manager
#   4. Runs terraform init + plan (shows what will be created)
#   5. Asks for confirmation, then terraform apply
#
# IF IT FAILS:
#   - API enable fails:     Check billing, check quotas in GCP Console
#   - Secret create fails:  Secret may already exist (safe to ignore)
#   - Terraform plan fails: Read the error — usually a naming conflict or
#                           quota issue. Fix and re-run (idempotent).
#   - Terraform apply fails: Check Cloud SQL quota (one instance per project
#                            on free tier). VPC peering can take 5+ minutes.
#   - .env not found:       Create it — see .env section in INITIAL.md
#   - Secret var empty:     Set the missing value in .env
#
# NEXT STEP:
#   After provision completes: ./scripts/deploy.sh --all
#
###############################################################################

PROJECT_ID=$(gcloud config get-value project)
REGION="${GCP_REGION:-us-central1}"

echo ""
printf "\033[1m══════════════════════════════════════════════════\033[0m\n"
printf "\033[1m  PROVISION — Claims Photo Fraud Detection\033[0m\n"
printf "\033[1m  Project: ${PROJECT_ID}\033[0m\n"
printf "\033[1m══════════════════════════════════════════════════\033[0m\n"

# Enable required APIs
APIS=(
  run.googleapis.com
  sqladmin.googleapis.com
  storage.googleapis.com
  vision.googleapis.com
  secretmanager.googleapis.com
  artifactregistry.googleapis.com
  pubsub.googleapis.com
  vpcaccess.googleapis.com
  servicenetworking.googleapis.com
  cloudbuild.googleapis.com
)

echo ""
printf "\033[1m─ Enabling APIs\033[0m\n"
for api in "${APIS[@]}"; do
  echo "  Enabling ${api} ..."
  gcloud services enable "$api" --project="$PROJECT_ID"
done
echo "  All APIs enabled."

echo ""
printf "\033[1m─ Loading .env\033[0m\n"
ENV_FILE="${SCRIPT_DIR}/../.env"
if [[ -f "$ENV_FILE" ]]; then
  echo "  Loading secrets from .env"
  set -a; source "$ENV_FILE"; set +a
  export TF_VAR_db_password="${DB_PASSWORD:-}"
  export TF_VAR_project_id="${PROJECT_ID}"
else
  echo "  ERROR: .env not found at $ENV_FILE — create it with secret values first"
  exit 1
fi

# Run Terraform (creates: Artifact Registry, secrets, Cloud SQL, VPC, GCS, Pub/Sub, IAM)
TERRAFORM_DIR="${SCRIPT_DIR}/../terraform"

echo ""
printf "\033[1m─ Terraform\033[0m\n"
cd "$TERRAFORM_DIR"
terraform init
terraform plan -var="project_id=$PROJECT_ID" -var="db_password=${DB_PASSWORD:-}"
echo ""
read -p "Apply? (y/N): " confirm
[[ "$confirm" == "y" ]] && terraform apply -var="project_id=$PROJECT_ID" -var="db_password=${DB_PASSWORD:-}"

# Push secret values to Secret Manager (Terraform creates the secrets, this adds the values)
echo ""
printf "\033[1m─ Secret Values\033[0m\n"
push_secret() {
  local secret_name="$1"
  local value="$2"
  if [[ -z "$value" ]]; then
    echo "  WARNING: No value for $secret_name in .env, skipping"
    return
  fi
  local version_count
  version_count=$(gcloud secrets versions list "$secret_name" --project="$PROJECT_ID" --format='value(name)' 2>/dev/null | wc -l)
  if [[ "$version_count" -eq 0 ]]; then
    echo "  Adding value for: $secret_name"
    echo -n "$value" | gcloud secrets versions add "$secret_name" \
      --data-file=- --project="$PROJECT_ID"
  else
    echo "  $secret_name already has a value (use 'gcloud secrets versions add' to update)"
  fi
}

push_secret "gemini-api-key"    "${GEMINI_API_KEY:-}"
push_secret "db-password"       "${DB_PASSWORD:-}"
push_secret "session-secret"    "${SESSION_SECRET:-}"
push_secret "exchange-password" "${EXCHANGE_PASSWORD:-}"

echo ""
printf "\033[1m══════════════════════════════════════════════════\033[0m\n"
printf "\033[1m  Provisioning complete\033[0m\n"
printf "\033[1m══════════════════════════════════════════════════\033[0m\n"
echo "Next: ./scripts/deploy.sh --all"
