#!/usr/bin/env bash
set -uo pipefail

###############################################################################
# teardown.sh — Destroy all Claims Images infrastructure in GCP
###############################################################################
#
# WHAT:
#   Tears down everything provision.sh and deploy.sh created. Returns the
#   GCP project to a clean state — no Cloud Run services, no Cloud SQL,
#   no buckets, no Pub/Sub, no secrets, no Artifact Registry images.
#   Does NOT delete the GCP project itself.
#
# WHY:
#   Clean slate for reprovisioning, cost savings when not actively developing,
#   or recovering from a broken state where fixing is harder than rebuilding.
#
# WHEN TO RUN:
#   - When you want to start fresh (provision.sh will recreate everything)
#   - Before switching to a different GCP project
#   - To stop billing on idle resources (especially Cloud SQL)
#   - After a botched provision/deploy that's easier to redo than fix
#
# WHAT IT DESTROYS (in order):
#   1. Cloud Run services (API, Worker, Dashboard)
#   2. Pub/Sub subscription + topic (pre-clean so TF doesn't choke)
#   3. GCS notifications (pre-clean)
#   4. Cloud SQL deletion protection (disabled via gcloud + TF targeted apply)
#   5. Terraform destroy (everything: Cloud SQL, VPC, GCS, IAM, secrets, etc.)
#   6. Fallback cleanup — anything Terraform missed (Artifact Registry, secrets)
#
# WHAT IT KEEPS:
#   - The GCP project itself
#   - Enabled APIs (cheap/free, saves time on reprovision)
#   - Local files (.env, code, git history)
#   - gcloud auth/config
#
# IF IT FAILS:
#   - "resource not found" = already gone, safe to ignore
#   - VPC peering error = Cloud SQL still releasing, re-run in 2 minutes
#   - Terraform destroy partial fail = script retries once automatically
#   - Permission denied = re-auth: gcloud auth login
#   - Safe to re-run: all steps are idempotent
#
# RECOVERY:
#   After teardown: ./scripts/provision.sh && ./scripts/deploy.sh --all
#
###############################################################################

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${SCRIPT_DIR}/.."
TERRAFORM_DIR="${PROJECT_ROOT}/terraform"
ENV_FILE="${PROJECT_ROOT}/.env"

PROJECT_ID=$(gcloud config get-value project 2>/dev/null)
REGION="${GCP_REGION:-us-central1}"

ERRORS=()

# Load .env and export Terraform vars
if [[ -f "$ENV_FILE" ]]; then
  set -a; source "$ENV_FILE"; set +a
  export TF_VAR_db_password="${DB_PASSWORD:-}"
  export TF_VAR_project_id="${PROJECT_ID}"
fi

echo ""
printf "\033[1m══════════════════════════════════════════════════\033[0m\n"
printf "\033[1m  TEARDOWN — Claims Photo Fraud Detection\033[0m\n"
printf "\033[1m  Project: ${PROJECT_ID}\033[0m\n"
printf "\033[1m══════════════════════════════════════════════════\033[0m\n"
echo ""
printf "\033[31mThis will destroy ALL Claims Images infrastructure.\033[0m\n"
echo "The GCP project itself will NOT be deleted."
echo ""
read -p "Are you sure? Type 'teardown' to confirm: " confirm
if [[ "$confirm" != "teardown" ]]; then
  echo "Aborted."
  exit 1
fi

echo ""

# ── 1. Cloud Run services ─────────────────────────────────────────
printf "\033[1m─ Cloud Run Services\033[0m\n"
for svc in claims-api claims-worker claims-dashboard; do
  echo "  Deleting ${svc} ..."
  gcloud run services delete "$svc" \
    --region="$REGION" --project="$PROJECT_ID" --quiet 2>/dev/null \
    && echo "  Deleted ${svc}" \
    || echo "  ${svc} not found (skipped)"
done

# ── 2. Pub/Sub (pre-clean before Terraform) ───────────────────────
echo ""
printf "\033[1m─ Pub/Sub\033[0m\n"
gcloud pubsub subscriptions delete worker-photo-sub \
  --project="$PROJECT_ID" --quiet 2>/dev/null \
  && echo "  Deleted subscription" \
  || echo "  Subscription not found (skipped)"
gcloud pubsub topics delete photo-uploads \
  --project="$PROJECT_ID" --quiet 2>/dev/null \
  && echo "  Deleted topic" \
  || echo "  Topic not found (skipped)"

# ── 3. GCS notifications (pre-clean) ─────────────────────────────
echo ""
printf "\033[1m─ GCS Notifications\033[0m\n"
NOTIF_IDS=$(gcloud storage buckets notifications list "gs://${PROJECT_ID}-claim-photos" \
  --format='value(etag)' --project="$PROJECT_ID" 2>/dev/null || echo "")
if [[ -n "$NOTIF_IDS" ]]; then
  for nid in $NOTIF_IDS; do
    gcloud storage buckets notifications delete "gs://${PROJECT_ID}-claim-photos" \
      --notification-id="$nid" --project="$PROJECT_ID" --quiet 2>/dev/null
  done
  echo "  Removed GCS notifications"
else
  echo "  No notifications found (skipped)"
fi

# ── 4. Terraform destroy ──────────────────────────────────────────
echo ""
printf "\033[1m─ Terraform\033[0m\n"
if [[ -d "$TERRAFORM_DIR" ]]; then
  cd "$TERRAFORM_DIR"

  # Check if there's any state to destroy
  terraform init -input=false 2>/dev/null
  STATE_COUNT=$(terraform state list 2>/dev/null | wc -l | tr -d ' ')

  if [[ "$STATE_COUNT" -eq 0 ]]; then
    echo "  No resources in Terraform state (already clean)"
  else
    echo "  ${STATE_COUNT} resources in state"

    # Disable Cloud SQL deletion protection (both gcloud and TF state)
    if gcloud sql instances describe fraud-detection-db --project="$PROJECT_ID" &>/dev/null; then
      echo "  Disabling Cloud SQL deletion protection (gcloud) ..."
      gcloud sql instances patch fraud-detection-db \
        --no-deletion-protection --project="$PROJECT_ID" --quiet 2>/dev/null
      echo "  Updating Terraform state ..."
      terraform apply \
        -var="project_id=$PROJECT_ID" \
        -var="db_password=${DB_PASSWORD:-}" \
        -var="deletion_protection=false" \
        -target=google_sql_database_instance.fraud_db \
        -auto-approve 2>/dev/null || true
    fi

    # Pre-delete VPC peering — GCP holds it for minutes after Cloud SQL dies,
    # which blocks terraform destroy. Force-remove it via gcloud first.
    if gcloud compute networks peerings list --network=claims-vpc \
        --project="$PROJECT_ID" --format='value(name)' 2>/dev/null | grep -q servicenetworking; then
      echo "  Removing VPC peering (prevents terraform timeout) ..."
      gcloud compute networks peerings delete servicenetworking-googleapis-com \
        --network=claims-vpc --project="$PROJECT_ID" --quiet 2>/dev/null
      terraform state rm google_service_networking_connection.private_vpc 2>/dev/null || true
      echo "  VPC peering removed"
    fi

    # Destroy — first attempt
    echo "  Destroying infrastructure ..."
    if ! terraform destroy \
      -var="project_id=$PROJECT_ID" \
      -var="db_password=${DB_PASSWORD:-}" \
      -var="deletion_protection=false" \
      -auto-approve 2>&1; then

      # Retry with increasing waits — VPC peering needs time after Cloud SQL delete
      for wait in 30 60 90; do
        echo ""
        echo "  Destroy had errors. Waiting ${wait}s for GCP to release resources ..."
        sleep "$wait"
        echo "  Retrying ..."
        if terraform destroy \
          -var="project_id=$PROJECT_ID" \
          -var="db_password=${DB_PASSWORD:-}" \
          -var="deletion_protection=false" \
          -auto-approve 2>&1; then
          break
        fi
      done
      # Check if anything remains
      REMAINING=$(terraform state list 2>/dev/null | wc -l | tr -d ' ')
      if [[ "$REMAINING" -gt 0 ]]; then
        ERRORS+=("Terraform destroy (${REMAINING} resources remaining — re-run teardown)")
      fi
    fi
  fi

  cd "$SCRIPT_DIR"
else
  echo "  Terraform dir not found, skipping"
fi

# ── 5. Fallback cleanup (catches anything TF missed) ─────────────
echo ""
printf "\033[1m─ Fallback Cleanup\033[0m\n"

# Artifact Registry
gcloud artifacts repositories delete claims-images \
  --location="$REGION" --project="$PROJECT_ID" --quiet 2>/dev/null \
  && echo "  Deleted Artifact Registry repo" \
  || echo "  Artifact Registry not found (skipped)"

# Secrets
for secret in gemini-api-key db-password session-secret exchange-password; do
  gcloud secrets delete "$secret" \
    --project="$PROJECT_ID" --quiet 2>/dev/null \
    && echo "  Deleted secret: ${secret}" \
    || echo "  ${secret} not found (skipped)"
done

# Service accounts (if TF didn't clean them)
for sa in claims-api claims-worker; do
  gcloud iam service-accounts delete "${sa}@${PROJECT_ID}.iam.gserviceaccount.com" \
    --project="$PROJECT_ID" --quiet 2>/dev/null \
    && echo "  Deleted service account: ${sa}" \
    || echo "  ${sa} SA not found (skipped)"
done

# ── Summary ───────────────────────────────────────────────────────
echo ""
printf "\033[1m══════════════════════════════════════════════════\033[0m\n"
if [[ ${#ERRORS[@]} -gt 0 ]]; then
  printf "\033[1m\033[31m  Teardown completed with errors\033[0m\n"
  printf "\033[1m══════════════════════════════════════════════════\033[0m\n"
  for err in "${ERRORS[@]}"; do
    printf "  \033[31m✗\033[0m %s\n" "$err"
  done
  echo ""
  echo "Re-run: ./scripts/teardown.sh"
  exit 1
else
  printf "\033[1m  Teardown complete\033[0m\n"
  printf "\033[1m══════════════════════════════════════════════════\033[0m\n"
  echo "GCP project ${PROJECT_ID} is intact. Infrastructure destroyed."
  echo "To rebuild: ./scripts/provision.sh && ./scripts/deploy.sh --all"
  exit 0
fi
