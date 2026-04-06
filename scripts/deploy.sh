#!/usr/bin/env bash
set -euo pipefail

###############################################################################
# deploy.sh — Build, deploy, and seed the Claims Photo Fraud Detection system
###############################################################################
#
# WHAT:
#   Builds Docker images via Cloud Build, pushes to Artifact Registry,
#   deploys to Cloud Run, and optionally seeds the database. Handles
#   API, Worker, Dashboard services, and a seed Cloud Run job.
#
# WHY:
#   Single command to get code from local to production. No manual Docker
#   builds, no clicking through GCP Console, no forgetting env vars.
#
# USAGE:
#   ./deploy.sh --all              # Deploy all 3 services
#   ./deploy.sh --all --seed       # Deploy all 3 services + seed the DB
#   ./deploy.sh --seed             # Just seed the DB (services already up)
#   ./deploy.sh api                # Just the API
#   ./deploy.sh api worker         # API and Worker
#   ./deploy.sh dashboard          # Just the Dashboard
#   ./deploy.sh api --seed         # Redeploy API + seed the DB
#
#   Flags:
#     --all       Build + deploy all 3 services (api, worker, dashboard)
#     --seed      Build + run the seed Cloud Run job (users, prompts, test data)
#     --help      Show this help
#
#   Services: api, worker, dashboard (pass one or more by name)
#
# WHEN TO RUN:
#   1. Fresh provision:  ./deploy.sh --all --seed
#   2. Code changes:     ./deploy.sh api          (or whichever service changed)
#   3. New users/prompts: ./deploy.sh --seed
#   4. Full cycle:       preflight → provision → deploy --all --seed → health_check
#
# PREREQUISITES:
#   - provision.sh completed (infra exists)
#   - gcloud authenticated with correct project
#   - Secrets in Secret Manager (provision.sh creates these)
#   - Service accounts created by Terraform
#
# WHAT IT DOES:
#   api:       Builds, deploys to claims-api (512Mi/1CPU, authenticated)
#   worker:    Builds, deploys to claims-worker (1Gi/2CPU, authenticated),
#              wires Pub/Sub push subscription to worker /process endpoint
#   dashboard: Builds, deploys to claims-dashboard (256Mi/1CPU, domain-auth),
#              injects API URL as env var, grants vtg-services.net access
#   --seed:    Builds scripts/Dockerfile.seed, runs as a Cloud Run job
#              inside the VPC (can reach private Cloud SQL). Seeds users,
#              prompts, and test claims. Reads SEED_USER_N_* from .env.
#
# IF IT FAILS:
#   - Cloud Build fails:     Check Dockerfile, check build logs in GCP Console
#   - Deploy fails:          Check service account exists, check VPC connector
#   - Pub/Sub wire fails:    Non-fatal — will wire on next deploy cycle
#   - Dashboard can't reach API: Check API_SERVICE_URL env var on dashboard
#   - Seed job fails:        Check Cloud Run job logs in GCP Console
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
RUN_SEED=false

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${SCRIPT_DIR}/.."

usage() {
  echo "Usage: ./deploy.sh [--all | --seed | service1 service2 ...]"
  echo "  --all       Build and deploy all services"
  echo "  --seed      Run database seed job (schema + users + prompts + test data)"
  echo "  service     One or more of: ${ALL_SERVICES[*]}"
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --all)      TARGETS=("${ALL_SERVICES[@]}"); shift ;;
    --seed)     RUN_SEED=true; shift ;;
    --help|-h)  usage ;;
    *)          TARGETS+=("$1"); shift ;;
  esac
done

[[ ${#TARGETS[@]} -eq 0 && "$RUN_SEED" == "false" ]] && usage

# ── Colors ─────────────────────────────────────────────────────────
C="\033[36m"       # cyan — banners
O="\033[38;5;208m" # orange — section headers
R="\033[31m"       # red — errors
G="\033[32m"       # green — success
B="\033[1m"        # bold
X="\033[0m"        # reset

echo ""
printf "${C}${B}══════════════════════════════════════════════════${X}\n"
printf "${C}${B}  DEPLOY — Claims Photo Fraud Detection${X}\n"
printf "${C}${B}  Project: ${PROJECT_ID}${X}\n"
printf "${C}${B}  Services: ${TARGETS[*]+"${TARGETS[*]}"}${RUN_SEED:+ (+seed)}${X}\n"
printf "${C}${B}══════════════════════════════════════════════════${X}\n"

for svc in ${TARGETS[@]+"${TARGETS[@]}"}; do
  echo ""
  printf "${O}${B}─ Building ${svc}${X}\n"
  gcloud builds submit "${PROJECT_ROOT}/${svc}" --tag="${REPO}/${svc}:latest"

  printf "${O}${B}─ Deploying ${svc}${X}\n"
  case "$svc" in
    api)
      gcloud run deploy claims-api \
        --image="${REPO}/api:latest" \
        --region="${REGION}" \
        --memory=512Mi --cpu=1 \
        --set-env-vars="GCS_BUCKET=${PROJECT_ID}-claim-photos,GEMINI_MODEL=gemini-2.5-flash,CLOUD_SQL_CONNECTION_NAME=${PROJECT_ID}:${REGION}:fraud-detection-db,DB_NAME=fraud_detection,DB_USER=fraud_user" \
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
        --set-env-vars="GCS_BUCKET=${PROJECT_ID}-claim-photos,GEMINI_MODEL=gemini-2.5-flash,ENABLE_CLOUD_VISION=true,CLOUD_SQL_CONNECTION_NAME=${PROJECT_ID}:${REGION}:fraud-detection-db,DB_NAME=fraud_detection,DB_USER=fraud_user" \
        --set-secrets="GEMINI_API_KEY=gemini-api-key:latest,DB_PASSWORD=db-password:latest,EXCHANGE_PASSWORD=exchange-password:latest" \
        --service-account="claims-worker@${PROJECT_ID}.iam.gserviceaccount.com" \
        --vpc-connector=claims-vpc-connector \
        --no-allow-unauthenticated

      # Wire Pub/Sub push subscription to worker endpoint
      WORKER_URL=$(gcloud run services describe claims-worker --region="${REGION}" --format='value(status.url)')
      gcloud pubsub subscriptions update worker-photo-sub \
        --push-endpoint="${WORKER_URL}/process" \
        --push-auth-service-account="claims-worker@${PROJECT_ID}.iam.gserviceaccount.com" \
        || echo "  Note: Pub/Sub subscription will be wired on next provision + deploy cycle"
      ;;
    dashboard)
      API_URL=$(gcloud run services describe claims-api --region="${REGION}" --format='value(status.url)' 2>/dev/null || echo "")
      if [[ -z "$API_URL" ]]; then
        printf "  ${R}WARNING: API not deployed yet — dashboard will not be able to reach it${X}\n"
        API_URL="https://claims-api-placeholder.run.app"
      fi
      gcloud run deploy claims-dashboard \
        --image="${REPO}/dashboard:latest" \
        --region="${REGION}" \
        --memory=256Mi --cpu=1 \
        --set-env-vars="API_SERVICE_URL=${API_URL}" \
        --no-allow-unauthenticated

      # Grant domain access — org policy blocks allUsers
      echo "  Granting dashboard access to vtg-services.net domain ..."
      gcloud run services add-iam-policy-binding claims-dashboard \
        --region="${REGION}" \
        --member="domain:vtg-services.net" \
        --role=roles/run.invoker \
        --quiet
      ;;
  esac
done

# ── Seed Job (optional) ───────────────────────────────────────────
if [[ "$RUN_SEED" == "true" ]]; then
  echo ""
  printf "${O}${B}─ Seed Job${X}\n"

  # Load .env for non-secret values (emails, names, roles)
  ENV_FILE="${PROJECT_ROOT}/.env"
  if [[ -f "$ENV_FILE" ]]; then
    set -a; source "$ENV_FILE"; set +a
  fi

  echo "  Building seed image ..."
  gcloud builds submit "${PROJECT_ROOT}/scripts" \
    --tag="${REPO}/seed:latest"

  # All env vars in ONE flag (multiple flags overwrite each other).
  # Passwords go via --set-secrets to avoid special char issues.
  SEED_ENV="CLOUD_SQL_CONNECTION_NAME=${PROJECT_ID}:${REGION}:fraud-detection-db"
  SEED_ENV="${SEED_ENV},CLOUD_SQL_DB=fraud_detection,CLOUD_SQL_USER=fraud_user"
  SEED_ENV="${SEED_ENV},SEED_USER_1_EMAIL=${SEED_USER_1_EMAIL:-}"
  SEED_ENV="${SEED_ENV},SEED_USER_1_NAME=${SEED_USER_1_NAME:-}"
  SEED_ENV="${SEED_ENV},SEED_USER_1_ROLE=${SEED_USER_1_ROLE:-admin}"
  SEED_ENV="${SEED_ENV},SEED_USER_2_EMAIL=${SEED_USER_2_EMAIL:-}"
  SEED_ENV="${SEED_ENV},SEED_USER_2_NAME=${SEED_USER_2_NAME:-}"
  SEED_ENV="${SEED_ENV},SEED_USER_2_ROLE=${SEED_USER_2_ROLE:-reviewer}"

  SEED_SECRETS="DB_PASSWORD=db-password:latest"
  SEED_SECRETS="${SEED_SECRETS},SEED_USER_1_PASSWORD=seed-user-1-password:latest"
  SEED_SECRETS="${SEED_SECRETS},SEED_USER_2_PASSWORD=seed-user-2-password:latest"

  # Create or update the job (check existence first — don't swallow errors)
  if gcloud run jobs describe claims-seed --region="${REGION}" &>/dev/null; then
    echo "  Updating seed job ..."
    gcloud run jobs update claims-seed \
      --image="${REPO}/seed:latest" \
      --region="${REGION}" \
      --vpc-connector=claims-vpc-connector \
      --set-env-vars="${SEED_ENV}" \
      --set-secrets="${SEED_SECRETS}" \
      --service-account="claims-api@${PROJECT_ID}.iam.gserviceaccount.com"
  else
    echo "  Creating seed job ..."
    gcloud run jobs create claims-seed \
      --image="${REPO}/seed:latest" \
      --region="${REGION}" \
      --vpc-connector=claims-vpc-connector \
      --set-env-vars="${SEED_ENV}" \
      --set-secrets="${SEED_SECRETS}" \
      --service-account="claims-api@${PROJECT_ID}.iam.gserviceaccount.com"
  fi

  echo "  Executing seed job ..."
  gcloud run jobs execute claims-seed --region="${REGION}" --wait

  # Check execution status (--wait exits 0 even if the job failed)
  EXEC_STATUS=$(gcloud run jobs executions list --job=claims-seed \
    --region="${REGION}" --sort-by=~createTime --limit=1 \
    --format='value(status.conditions[0].type)' 2>/dev/null)
  if [[ "$EXEC_STATUS" != "Completed" ]]; then
    printf "  ${R}ERROR: Seed job failed. Check logs:${X}\n"
    echo "    gcloud run jobs executions list --job=claims-seed --region=${REGION}"
    exit 1
  fi
  echo "  Seed job complete."
fi

echo ""
printf "${C}${B}══════════════════════════════════════════════════${X}\n"
printf "${G}${B}  Deploy complete${X}\n"
printf "${C}${B}══════════════════════════════════════════════════${X}\n"
gcloud run services list --region="${REGION}" --format="table(SERVICE,URL,LAST_DEPLOYED)"
