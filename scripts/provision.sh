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

echo "=== Provisioning GCP Project: $PROJECT_ID ==="

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

for api in "${APIS[@]}"; do
  echo "  Enabling ${api} ..."
  gcloud services enable "$api" --project="$PROJECT_ID"
done
echo "  All APIs enabled."

# Create Artifact Registry repo (if not exists)
gcloud artifacts repositories describe claims-images \
  --location="$REGION" --project="$PROJECT_ID" 2>/dev/null || \
gcloud artifacts repositories create claims-images \
  --repository-format=docker \
  --location="$REGION" \
  --project="$PROJECT_ID"

# Load secrets from .env
SCRIPT_DIR_TMP="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR_TMP}/../.env"
if [[ -f "$ENV_FILE" ]]; then
  echo "  Loading secrets from .env"
  set -a; source "$ENV_FILE"; set +a
else
  echo "  ERROR: .env not found at $ENV_FILE — create it with secret values first"
  exit 1
fi

# Map .env variable names to Secret Manager secret names
declare -A SECRET_MAP=(
  ["gemini-api-key"]="$GEMINI_API_KEY"
  ["db-password"]="$DB_PASSWORD"
  ["session-secret"]="$SESSION_SECRET"
  ["exchange-password"]="$EXCHANGE_PASSWORD"
)

for secret_name in "${!SECRET_MAP[@]}"; do
  value="${SECRET_MAP[$secret_name]}"
  if [[ -z "$value" ]]; then
    echo "  WARNING: No value for $secret_name in .env, skipping"
    continue
  fi
  if ! gcloud secrets describe "$secret_name" --project="$PROJECT_ID" &>/dev/null; then
    echo "  Creating secret: $secret_name"
    echo -n "$value" | gcloud secrets create "$secret_name" \
      --data-file=- --project="$PROJECT_ID"
  else
    echo "  Secret $secret_name already exists (use 'gcloud secrets versions add' to update)"
  fi
done

# Run Terraform
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TERRAFORM_DIR="${SCRIPT_DIR}/../terraform"

echo "=== Running Terraform ==="
cd "$TERRAFORM_DIR"
terraform init
terraform plan -var="project_id=$PROJECT_ID"
echo ""
read -p "Apply? (y/N): " confirm
[[ "$confirm" == "y" ]] && terraform apply -var="project_id=$PROJECT_ID"

echo "=== Provisioning complete ==="
