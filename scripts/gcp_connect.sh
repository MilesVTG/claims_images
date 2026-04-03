#!/usr/bin/env bash
#
# gcp_connect.sh — Verify GCP connectivity, auth, project, and required APIs
# Run this first before any other scripts.
#
set -euo pipefail

BOLD="\033[1m"
GREEN="\033[0;32m"
RED="\033[0;31m"
YELLOW="\033[0;33m"
RESET="\033[0m"

pass() { echo -e "  ${GREEN}✓${RESET} $1"; }
fail() { echo -e "  ${RED}✗${RESET} $1"; }
warn() { echo -e "  ${YELLOW}!${RESET} $1"; }
header() { echo -e "\n${BOLD}$1${RESET}"; }

ERRORS=0

# ─── 1. gcloud installed? ────────────────────────────────────────────────────
header "1. Checking gcloud CLI"
if ! command -v gcloud &>/dev/null; then
    fail "gcloud not found. Install: https://cloud.google.com/sdk/docs/install"
    exit 1
fi
GCLOUD_VERSION=$(gcloud version 2>/dev/null | head -1)
pass "gcloud installed — $GCLOUD_VERSION"

# ─── 2. Authenticated? ───────────────────────────────────────────────────────
header "2. Checking authentication"
ACCOUNT=$(gcloud config get-value account 2>/dev/null || true)
if [[ -z "$ACCOUNT" || "$ACCOUNT" == "(unset)" ]]; then
    fail "No active account. Run: gcloud auth login"
    ((ERRORS++))
else
    pass "Logged in as: $ACCOUNT"
fi

# Also check application-default credentials (needed by client libraries)
if gcloud auth application-default print-access-token &>/dev/null 2>&1; then
    pass "Application-default credentials OK"
else
    warn "No application-default credentials. Run: gcloud auth application-default login"
fi

# ─── 3. Project ──────────────────────────────────────────────────────────────
header "3. Checking GCP project"

ENV_FILE="$(cd "$(dirname "$0")/.." && pwd)/.env"

# Try to load from .env first
if [[ -f "$ENV_FILE" ]]; then
    source "$ENV_FILE" 2>/dev/null || true
fi

if [[ -z "${GCP_PROJECT_ID:-}" ]]; then
    # Check current gcloud config
    CURRENT_PROJECT=$(gcloud config get-value project 2>/dev/null || true)

    echo ""
    echo "  Available projects:"
    gcloud projects list --format="table(projectId, name)" 2>/dev/null | sed 's/^/    /'
    echo ""

    if [[ -n "$CURRENT_PROJECT" && "$CURRENT_PROJECT" != "(unset)" ]]; then
        read -rp "  GCP Project ID [$CURRENT_PROJECT]: " INPUT_PROJECT
        GCP_PROJECT_ID="${INPUT_PROJECT:-$CURRENT_PROJECT}"
    else
        read -rp "  GCP Project ID: " GCP_PROJECT_ID
    fi
fi

if [[ -z "$GCP_PROJECT_ID" ]]; then
    fail "No project ID provided."
    exit 1
fi

# Verify project exists and we have access
if gcloud projects describe "$GCP_PROJECT_ID" &>/dev/null; then
    PROJECT_NAME=$(gcloud projects describe "$GCP_PROJECT_ID" --format="value(name)" 2>/dev/null)
    PROJECT_NUMBER=$(gcloud projects describe "$GCP_PROJECT_ID" --format="value(projectNumber)" 2>/dev/null)
    pass "Project: $GCP_PROJECT_ID ($PROJECT_NAME) — #$PROJECT_NUMBER"
else
    fail "Cannot access project '$GCP_PROJECT_ID'. Check the ID and your permissions."
    ((ERRORS++))
fi

# Set as active project
gcloud config set project "$GCP_PROJECT_ID" &>/dev/null
pass "Active gcloud project set to: $GCP_PROJECT_ID"

# ─── 4. Region ───────────────────────────────────────────────────────────────
header "4. Checking region"
GCP_REGION="${GCP_REGION:-}"
if [[ -z "$GCP_REGION" ]]; then
    CURRENT_REGION=$(gcloud config get-value compute/region 2>/dev/null || true)
    DEFAULT_REGION="${CURRENT_REGION:-us-central1}"
    read -rp "  GCP Region [$DEFAULT_REGION]: " INPUT_REGION
    GCP_REGION="${INPUT_REGION:-$DEFAULT_REGION}"
fi
gcloud config set compute/region "$GCP_REGION" &>/dev/null
pass "Region: $GCP_REGION"

# ─── 5. Required APIs ────────────────────────────────────────────────────────
header "5. Checking required APIs"

REQUIRED_APIS=(
    "run.googleapis.com"                # Cloud Run
    "sqladmin.googleapis.com"           # Cloud SQL Admin
    "storage.googleapis.com"            # Cloud Storage
    "pubsub.googleapis.com"             # Pub/Sub
    "aiplatform.googleapis.com"         # Vertex AI (Gemini)
    "vision.googleapis.com"             # Cloud Vision
    "cloudbuild.googleapis.com"         # Cloud Build
    "secretmanager.googleapis.com"      # Secret Manager
    "artifactregistry.googleapis.com"   # Artifact Registry
)

ENABLED_APIS=$(gcloud services list --enabled --format="value(config.name)" 2>/dev/null)
MISSING_APIS=()

for api in "${REQUIRED_APIS[@]}"; do
    if echo "$ENABLED_APIS" | grep -q "^${api}$"; then
        pass "$api"
    else
        fail "$api — NOT ENABLED"
        MISSING_APIS+=("$api")
    fi
done

if [[ ${#MISSING_APIS[@]} -gt 0 ]]; then
    echo ""
    read -rp "  Enable ${#MISSING_APIS[@]} missing API(s)? [y/N]: " ENABLE_APIS
    if [[ "$ENABLE_APIS" =~ ^[Yy] ]]; then
        for api in "${MISSING_APIS[@]}"; do
            echo -n "  Enabling $api... "
            if gcloud services enable "$api" 2>/dev/null; then
                echo -e "${GREEN}done${RESET}"
            else
                echo -e "${RED}failed${RESET}"
                ((ERRORS++))
            fi
        done
    else
        warn "Skipped. Enable later with: gcloud services enable <api>"
        ((ERRORS += ${#MISSING_APIS[@]}))
    fi
fi

# ─── 6. Cloud SQL instances ──────────────────────────────────────────────────
header "6. Checking Cloud SQL instances"
SQL_INSTANCES=$(gcloud sql instances list --format="table(name, databaseVersion, region, state)" 2>/dev/null || true)
if [[ -n "$SQL_INSTANCES" ]]; then
    echo "$SQL_INSTANCES" | sed 's/^/    /'
else
    warn "No Cloud SQL instances found (will be created by provision.sh)"
fi

# ─── 7. GCS buckets ──────────────────────────────────────────────────────────
header "7. Checking GCS buckets"
BUCKETS=$(gcloud storage buckets list --format="value(name)" 2>/dev/null || true)
if [[ -n "$BUCKETS" ]]; then
    echo "$BUCKETS" | sed 's/^/    /'
else
    warn "No GCS buckets found (will be created by provision.sh)"
fi

# ─── 8. Write .env ───────────────────────────────────────────────────────────
header "8. Writing .env"

cat > "$ENV_FILE" <<EOF
# Claims Photo Fraud Detection — GCP Config
# Generated by gcp_connect.sh on $(date '+%Y-%m-%d %H:%M:%S')

GCP_PROJECT_ID=$GCP_PROJECT_ID
GCP_PROJECT_NUMBER=${PROJECT_NUMBER:-UNKNOWN}
GCP_REGION=$GCP_REGION
GCP_ACCOUNT=$ACCOUNT

# Cloud SQL (update after provision.sh)
CLOUD_SQL_INSTANCE=claims-db
CLOUD_SQL_DB=claims
CLOUD_SQL_USER=claims-api

# GCS
GCS_PHOTO_BUCKET=${GCP_PROJECT_ID}-claim-photos

# Cloud Run service names
CR_API=claims-api
CR_WORKER=claims-worker
CR_DASHBOARD=claims-dashboard
EOF

pass "Wrote $ENV_FILE"

# ─── 9. Summary ──────────────────────────────────────────────────────────────
header "9. Summary"
echo ""
echo "  Account:  $ACCOUNT"
echo "  Project:  $GCP_PROJECT_ID ($PROJECT_NAME)"
echo "  Number:   ${PROJECT_NUMBER:-?}"
echo "  Region:   $GCP_REGION"
echo ""

if [[ $ERRORS -eq 0 ]]; then
    echo -e "  ${GREEN}${BOLD}All checks passed. Ready to build.${RESET}"
else
    echo -e "  ${RED}${BOLD}$ERRORS issue(s) found. Fix them before proceeding.${RESET}"
fi

echo ""
