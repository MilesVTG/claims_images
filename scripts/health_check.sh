#!/usr/bin/env bash
set -euo pipefail

###############################################################################
# health_check.sh — Post-deploy verification for Claims Photo Fraud Detection
###############################################################################
#
# WHAT:
#   Validates that all deployed services and GCP infrastructure are alive
#   and reachable. This is the "did it work?" check — run after provision.sh
#   and deploy.sh, not before.
#
# WHY:
#   Deploys can succeed (exit 0) but leave broken services — bad env vars,
#   missing secrets, failed DB migrations, VPC misconfig. This script hits
#   every endpoint and resource to confirm the system is actually working.
#
# WHEN TO RUN:
#   - After deploy.sh completes
#   - After provision.sh + deploy.sh on first setup
#   - As a smoke test before demoing to stakeholders
#   - When debugging "it worked yesterday" issues
#
# WHAT IT CHECKS:
#   1. API /api/health — FastAPI responds, DB connection works
#   2. Worker /health — Worker service responds
#   3. Dashboard — serves HTML (nginx + React SPA)
#   4. GCP APIs — all 10 required APIs enabled
#   5. Cloud SQL instance — exists and reachable
#   6. GCS bucket — photo storage bucket exists
#   7. Pub/Sub subscription — worker push sub exists
#   8. Pub/Sub topic — photo-uploads topic exists
#   9. Artifact Registry — Docker image repo exists
#  10. VPC connector — private network bridge exists
#
# OUTPUT:
#   ✓ = pass, ✗ = fail. Exit 0 = all healthy, Exit 1 = failures found.
#   Failed checks listed in summary.
#
# IF IT FAILS:
#   - Service health:  Check Cloud Run logs: gcloud run services logs read claims-api --region=us-central1
#   - Cloud SQL:       Check instance state: gcloud sql instances describe fraud-detection-db
#   - GCS bucket:      Re-run provision.sh — Terraform creates it
#   - Pub/Sub:         Re-run provision.sh — Terraform creates topic + sub
#   - VPC connector:   Re-run provision.sh — may need to delete and recreate
#   - API not found:   Service not deployed — run deploy.sh api
#   - 401/403 errors:  Identity token expired — re-run gcloud auth login
#
###############################################################################

PROJECT_ID=$(gcloud config get-value project 2>/dev/null)
REGION="${GCP_REGION:-us-central1}"
BUCKET="${GCS_BUCKET:-${PROJECT_ID}-claim-photos}"
PUBSUB_SUB="worker-photo-sub"
SQL_INSTANCE="fraud-detection-db"

PASS=0
FAIL=0
ERRORS=()

check() {
  local name="$1"
  shift
  if "$@" >/dev/null 2>&1; then
    echo "  ✓ ${name}"
    ((PASS++))
  else
    echo "  ✗ ${name}"
    ERRORS+=("$name")
    ((FAIL++))
  fi
}

# ── Resolve Cloud Run URLs ──────────────────────────────────────────
echo "=== Resolving service URLs ==="

API_URL="${API_URL:-$(gcloud run services describe claims-api --region="${REGION}" --format='value(status.url)' 2>/dev/null || echo "")}"
WORKER_URL="${WORKER_URL:-$(gcloud run services describe claims-worker --region="${REGION}" --format='value(status.url)' 2>/dev/null || echo "")}"
DASHBOARD_URL="${DASHBOARD_URL:-$(gcloud run services describe claims-dashboard --region="${REGION}" --format='value(status.url)' 2>/dev/null || echo "")}"

# Get identity token for authenticated services
ID_TOKEN=$(gcloud auth print-identity-token 2>/dev/null || echo "")

# ── 1. API /health ──────────────────────────────────────────────────
echo ""
echo "=== Service Health ==="

if [[ -n "$API_URL" ]]; then
  check "API /api/health" \
    curl -sf -m 10 -H "Authorization: Bearer ${ID_TOKEN}" "${API_URL}/api/health"
else
  echo "  ✗ API /api/health (service not deployed)"
  ERRORS+=("API /api/health")
  ((FAIL++))
fi

# ── 2. Worker /health ───────────────────────────────────────────────
if [[ -n "$WORKER_URL" ]]; then
  check "Worker /health" \
    curl -sf -m 10 -H "Authorization: Bearer ${ID_TOKEN}" "${WORKER_URL}/health"
else
  echo "  ✗ Worker /health (service not deployed)"
  ERRORS+=("Worker /health")
  ((FAIL++))
fi

# ── 3. Dashboard serves HTML ────────────────────────────────────────
if [[ -n "$DASHBOARD_URL" ]]; then
  check "Dashboard serves HTML" \
    bash -c "curl -sf -m 10 '${DASHBOARD_URL}/' | grep -qi '</html>'"
else
  echo "  ✗ Dashboard serves HTML (service not deployed)"
  ERRORS+=("Dashboard serves HTML")
  ((FAIL++))
fi

# ── 4. GCP APIs ─────────────────────────────────────────────────────
echo ""
echo "=== GCP APIs ==="

REQUIRED_APIS=(
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
ENABLED_APIS=$(gcloud services list --enabled --format='value(config.name)' --project="${PROJECT_ID}" 2>/dev/null || echo "")
for api in "${REQUIRED_APIS[@]}"; do
  check "${api}" bash -c "echo '${ENABLED_APIS}' | grep -q '${api}'"
done

# ── 5. Infrastructure ──────────────────────────────────────────────
echo ""
echo "=== Infrastructure ==="

check "Cloud SQL instance (${SQL_INSTANCE})" \
  gcloud sql instances describe "${SQL_INSTANCE}" --format='value(state)' --project="${PROJECT_ID}"

check "GCS bucket (${BUCKET})" \
  gcloud storage buckets describe "gs://${BUCKET}" --project="${PROJECT_ID}"

check "Pub/Sub subscription (${PUBSUB_SUB})" \
  gcloud pubsub subscriptions describe "${PUBSUB_SUB}" --project="${PROJECT_ID}"

check "Pub/Sub topic (photo-uploads)" \
  gcloud pubsub topics describe photo-uploads --project="${PROJECT_ID}"

check "Artifact Registry (claims-images)" \
  gcloud artifacts repositories describe claims-images --location="${REGION}" --project="${PROJECT_ID}"

check "VPC connector" \
  gcloud compute networks vpc-access connectors describe claims-vpc-connector --region="${REGION}" --project="${PROJECT_ID}"

# ── Summary ─────────────────────────────────────────────────────────
echo ""
echo "=== Results: ${PASS} passed, ${FAIL} failed ==="

if [[ ${FAIL} -gt 0 ]]; then
  echo "Failed checks:"
  for err in "${ERRORS[@]}"; do
    echo "  - ${err}"
  done
  exit 1
fi

echo "All checks passed."
exit 0
