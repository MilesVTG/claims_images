#!/usr/bin/env bash
set -uo pipefail

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
#   5. Seed data — login as seed user, verify claims + prompts exist
#   6. Cloud SQL instance — exists and reachable
#   7. GCS bucket — photo storage bucket exists
#   8. Pub/Sub subscription — worker push sub exists
#   9. Pub/Sub topic — photo-uploads topic exists
#  10. Artifact Registry — Docker image repo exists
#  11. VPC connector — private network bridge exists
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

# ── Colors ─────────────────────────────────────────────────────────
C="\033[36m"       # cyan — banners
O="\033[38;5;208m" # orange — section headers
R="\033[31m"       # red — errors
G="\033[32m"       # green — success
B="\033[1m"        # bold
X="\033[0m"        # reset

PASS=0
FAIL=0
ERRORS=()

check() {
  local name="$1"
  shift
  local output exit_code
  output=$("$@" 2>&1) && exit_code=0 || exit_code=$?
  if [[ $exit_code -eq 0 ]]; then
    printf "  ${G}✓${X} %s\n" "$name"
    ((PASS++)) || true
  else
    printf "  ${R}✗${X} %s (exit code: %d)\n" "$name" "$exit_code"
    if [[ -n "$output" ]]; then
      # Strip HTML tags for readability, show first 5 lines
      echo "$output" | sed 's/<[^>]*>//g' | sed '/^$/d' | head -5 | sed 's/^/    /'
    fi
    ERRORS+=("$name")
    ((FAIL++)) || true
  fi
}

echo ""
printf "${C}${B}══════════════════════════════════════════════════${X}\n"
printf "${C}${B}  HEALTH CHECK — Claims Photo Fraud Detection${X}\n"
printf "${C}${B}  Project: ${PROJECT_ID}${X}\n"
printf "${C}${B}══════════════════════════════════════════════════${X}\n"

# ── Resolve Cloud Run URLs ──────────────────────────────────────────
echo ""
printf "${O}${B}─ Resolving Service URLs${X}\n"

API_URL="${API_URL:-$(gcloud run services describe claims-api --region="${REGION}" --format='value(status.url)' 2>/dev/null || echo "")}"
WORKER_URL="${WORKER_URL:-$(gcloud run services describe claims-worker --region="${REGION}" --format='value(status.url)' 2>/dev/null || echo "")}"
DASHBOARD_URL="${DASHBOARD_URL:-$(gcloud run services describe claims-dashboard --region="${REGION}" --format='value(status.url)' 2>/dev/null || echo "")}"

# Get identity token for authenticated services
ID_TOKEN=$(gcloud auth print-identity-token 2>/dev/null || echo "")

# ── 1. API /health ──────────────────────────────────────────────────
echo ""
printf "${O}${B}─ Service Health${X}\n"

if [[ -n "$API_URL" ]]; then
  check "API /api/health" \
    curl -sf -m 10 -H "Authorization: Bearer ${ID_TOKEN}" "${API_URL}/api/health"
else
  printf "  ${R}✗${X} API /api/health (service not deployed)\n"
  ERRORS+=("API /api/health")
  ((FAIL++)) || true
fi

# ── 2. Worker /health ───────────────────────────────────────────────
if [[ -n "$WORKER_URL" ]]; then
  check "Worker /health" \
    curl -sf -m 10 -H "Authorization: Bearer ${ID_TOKEN}" "${WORKER_URL}/health"
else
  printf "  ${R}✗${X} Worker /health (service not deployed)\n"
  ERRORS+=("Worker /health")
  ((FAIL++)) || true
fi

# ── 3. Dashboard serves HTML ────────────────────────────────────────
if [[ -n "$DASHBOARD_URL" ]]; then
  check "Dashboard serves HTML" \
    bash -c "curl -sf -m 10 -H 'Authorization: Bearer ${ID_TOKEN}' '${DASHBOARD_URL}/' | grep -qi '</html>'"
else
  printf "  ${R}✗${X} Dashboard serves HTML (service not deployed)\n"
  ERRORS+=("Dashboard serves HTML")
  ((FAIL++)) || true
fi

# ── 4. GCP APIs ─────────────────────────────────────────────────────
echo ""
printf "${O}${B}─ GCP APIs${X}\n"

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

# ── 5. Seed Data Verification ─────────────────────────────────────
echo ""
printf "${O}${B}─ Seed Data${X}\n"

if [[ -n "$API_URL" && -n "$ID_TOKEN" ]]; then
  # Try to login as seed user — proves users table exists and was seeded
  LOGIN_RESP=$(curl -sf -m 10 -X POST \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer ${ID_TOKEN}" \
    -d '{"username":"mchick@vtg-services.com","password":"gandalf!"}' \
    "${API_URL}/api/auth/login" 2>/dev/null || echo "")
  if echo "$LOGIN_RESP" | grep -q '"token"'; then
    printf "  ${G}✓${X} Seed user login (mchick@vtg-services.com)\n"
    ((PASS++))

    # Use GCP identity token (not app JWT) for Cloud Run IAM auth on data endpoints
    check "Claims endpoint returns data" \
      bash -c "curl -sf -m 10 -H 'Authorization: Bearer ${ID_TOKEN}' '${API_URL}/api/claims' | grep -q 'claim_id'"

    check "System prompts seeded" \
      bash -c "curl -sf -m 10 -H 'Authorization: Bearer ${ID_TOKEN}' '${API_URL}/api/prompts' | grep -q 'fraud_system_instruction'"
  else
    printf "  ${R}✗${X} Seed user login (mchick@vtg-services.com)\n"
    ERRORS+=("Seed user login")
    ((FAIL++))
    echo "    Seed may not have run — try: ./deploy.sh --seed"
  fi
else
  printf "  ${R}✗${X} Seed data (API not available)\n"
  ERRORS+=("Seed data")
  ((FAIL++)) || true
fi

# ── 6. Infrastructure ──────────────────────────────────────────────
echo ""
printf "${O}${B}─ Infrastructure${X}\n"

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
printf "${C}${B}══════════════════════════════════════════════════${X}\n"
printf "${C}${B}  ${PASS} passed, ${FAIL} failed${X}\n"
printf "${C}${B}══════════════════════════════════════════════════${X}\n"

if [[ ${FAIL} -gt 0 ]]; then
  printf "${R}${B}Failed checks:${X}\n"
  for err in "${ERRORS[@]}"; do
    printf "  ${R}✗${X} %s\n" "$err"
  done
  exit 1
fi

printf "${G}${B}All checks passed.${X}\n"
exit 0
