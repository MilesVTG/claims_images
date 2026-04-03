#!/usr/bin/env bash
set -euo pipefail

###############################################################################
# deploy.sh — Build and deploy services to Cloud Run
###############################################################################
#
# WHAT:
#   Builds Docker images via Cloud Build, pushes to Artifact Registry, and
#   deploys to Cloud Run. Handles API, Worker, and Dashboard services.
#
# WHY:
#   Single command to get code from local to production. No manual Docker
#   builds, no clicking through GCP Console, no forgetting env vars.
#
# WHEN TO RUN:
#   - After provision.sh has created all infrastructure
#   - After code changes that need to go live
#   - After updating secrets in Secret Manager
#   Run preflight.sh first if unsure about your environment.
#
# USAGE:
#   ./deploy.sh --all              # Build + deploy all 3 services
#   ./deploy.sh api                # Just the API
#   ./deploy.sh api worker         # API and Worker
#   ./deploy.sh dashboard          # Just the Dashboard
#
# PREREQUISITES:
#   - provision.sh completed (infra exists)
#   - gcloud authenticated with correct project
#   - Secrets in Secret Manager (provision.sh creates these)
#   - Service accounts created by Terraform
#
# WHAT IT DOES PER SERVICE:
#   api:       Builds, deploys to claims-api (512Mi/1CPU, authenticated)
#   worker:    Builds, deploys to claims-worker (1Gi/2CPU, authenticated),
#              wires Pub/Sub push subscription to worker /process endpoint
#   dashboard: Builds, deploys to claims-dashboard (256Mi/1CPU, public),
#              injects API URL as env var
#
# IF IT FAILS:
#   - Cloud Build fails:     Check Dockerfile, check build logs in GCP Console
#   - Deploy fails:          Check service account exists, check VPC connector
#   - Pub/Sub wire fails:    Non-fatal — will wire on next deploy cycle
#   - Dashboard can't reach API: Check API_SERVICE_URL env var on dashboard
#   - Permission denied:     Check IAM roles on service accounts
#   - Image not found:       Artifact Registry repo may not exist — run provision.sh
#
# NEXT STEP:
#   After deploy completes: ./scripts/health_check.sh
#
###############################################################################

PROJECT_ID=$(gcloud config get-value project)
REGION="${GCP_REGION:-us-central1}"
REPO="${REGION}-docker.pkg.dev/${PROJECT_ID}/claims-images"
ALL_SERVICES=("api" "worker" "dashboard")
TARGETS=()

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${SCRIPT_DIR}/.."

usage() {
  echo "Usage: ./deploy.sh [--all | service1 service2 ...]"
  echo "  --all       Build and deploy all services"
  echo "  service     One or more of: ${ALL_SERVICES[*]}"
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --all)      TARGETS=("${ALL_SERVICES[@]}"); shift ;;
    --help|-h)  usage ;;
    *)          TARGETS+=("$1"); shift ;;
  esac
done

[[ ${#TARGETS[@]} -eq 0 ]] && usage

for svc in "${TARGETS[@]}"; do
  echo ""
  echo "=== Building ${svc} ==="
  gcloud builds submit "${PROJECT_ROOT}/${svc}" --tag="${REPO}/${svc}:latest"

  echo "=== Deploying ${svc} to Cloud Run ==="
  case "$svc" in
    api)
      gcloud run deploy claims-api \
        --image="${REPO}/api:latest" \
        --region="${REGION}" \
        --memory=512Mi --cpu=1 \
        --set-env-vars="GCS_BUCKET=${PROJECT_ID}-claim-photos,GEMINI_MODEL=gemini-2.5-flash,CLOUD_SQL_CONNECTION_NAME=${PROJECT_ID}:${REGION}:fraud-detection-db" \
        --set-secrets="GEMINI_API_KEY=gemini-api-key:latest,DB_PASSWORD=db-password:latest,SESSION_SECRET=session-secret:latest" \
        --service-account="claims-api@${PROJECT_ID}.iam.gserviceaccount.com" \
        --vpc-connector=claims-vpc-connector \
        --no-allow-unauthenticated
      ;;
    worker)
      gcloud run deploy claims-worker \
        --image="${REPO}/worker:latest" \
        --region="${REGION}" \
        --memory=1Gi --cpu=2 \
        --set-env-vars="GCS_BUCKET=${PROJECT_ID}-claim-photos,GEMINI_MODEL=gemini-2.5-flash,ENABLE_CLOUD_VISION=true,CLOUD_SQL_CONNECTION_NAME=${PROJECT_ID}:${REGION}:fraud-detection-db" \
        --set-secrets="GEMINI_API_KEY=gemini-api-key:latest,DB_PASSWORD=db-password:latest,EXCHANGE_PASSWORD=exchange-password:latest" \
        --service-account="claims-worker@${PROJECT_ID}.iam.gserviceaccount.com" \
        --vpc-connector=claims-vpc-connector \
        --no-allow-unauthenticated

      # Wire Pub/Sub push subscription to worker endpoint
      WORKER_URL=$(gcloud run services describe claims-worker --region="${REGION}" --format='value(status.url)')
      gcloud pubsub subscriptions update worker-photo-sub \
        --push-endpoint="${WORKER_URL}/process" \
        --push-auth-service-account="claims-worker@${PROJECT_ID}.iam.gserviceaccount.com" \
        2>/dev/null || \
      echo "  Note: Pub/Sub subscription will be wired on next provision + deploy cycle"
      ;;
    dashboard)
      API_URL=$(gcloud run services describe claims-api --region="${REGION}" --format='value(status.url)')
      gcloud run deploy claims-dashboard \
        --image="${REPO}/dashboard:latest" \
        --region="${REGION}" \
        --memory=256Mi --cpu=1 \
        --set-env-vars="API_SERVICE_URL=${API_URL}" \
        --allow-unauthenticated
      ;;
  esac
done

echo ""
echo "=== Deploy complete ==="
gcloud run services list --region="${REGION}" --format="table(SERVICE,URL,LAST_DEPLOYED)"
