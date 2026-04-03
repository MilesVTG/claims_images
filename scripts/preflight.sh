#!/usr/bin/env bash
set -uo pipefail

###############################################################################
# preflight.sh — Pre-run validation for Claims Photo Fraud Detection
###############################################################################
#
# WHAT:
#   Validates that your local environment is ready to run provision.sh or
#   deploy.sh. Checks auth, secrets, tools, GCP project access, and safety
#   (gitignore). Does NOT check for GCP resources — that's health_check.sh.
#
# WHY:
#   provision.sh and deploy.sh are slow, hit GCP APIs, and can cost money.
#   Preflight catches misconfig fast so you don't waste 10 minutes waiting
#   for a Terraform plan to blow up because you forgot to set DB_PASSWORD.
#
# WHEN TO RUN:
#   - Before provision.sh (first-time infra setup)
#   - Before deploy.sh (building + deploying services)
#   - After changing .env or switching GCP projects
#   - After a fresh clone / new machine setup
#
# WHAT IT CHECKS:
#   1. gcloud CLI installed, authenticated, project set
#   2. .env exists with all required secrets (GEMINI_API_KEY, DB_PASSWORD,
#      SESSION_SECRET, EXCHANGE_PASSWORD, EXCHANGE_SERVER, EXCHANGE_EMAIL)
#   3. Required tools: terraform, docker, node, python3, Docker daemon
#   4. GCP project accessible + billing enabled
#   5. .env is gitignored (never commit secrets)
#
# OUTPUT:
#   Green ✓ = pass, Red ✗ = fail. Failures logged with timestamps and
#   error details to ./preflight_logs/preflight_YYYY-MM-DD_HH-MM-SS.log.
#   If all checks pass, no log file is created.
#
# IF IT FAILS:
#   - gcloud auth:     Run: gcloud auth login mchick@vtg-services.net
#   - Project not set: Run: gcloud config set project propane-landing-491118-r7
#   - .env missing:    Copy from a teammate or recreate with required vars
#   - Secret not set:  Add the missing var to .env (quote special chars!)
#   - terraform:       Run: brew install terraform
#   - Docker daemon:   Start Docker Desktop
#   - Billing:         Enable billing in GCP Console for the project
#   - .env not ignored: Add ".env" to .gitignore immediately
#
# ADDING CHECKS:
#   Use the check() function: check "description" command args...
#   It handles pass/fail output, logging, and counting automatically.
#
###############################################################################

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${SCRIPT_DIR}/.."
ENV_FILE="${PROJECT_ROOT}/.env"
LOG_DIR="${PROJECT_ROOT}/preflight_logs"
mkdir -p "$LOG_DIR"

TIMESTAMP=$(date '+%Y-%m-%d_%H-%M-%S')
LOG_FILE="${LOG_DIR}/preflight_${TIMESTAMP}.log"

PASS=0
FAIL=0
HAS_ERRORS=false

check() {
  local name="$1"
  shift
  local output
  if output=$("$@" 2>&1); then
    printf "  \033[32m✓\033[0m %s\n" "$name"
    ((PASS++))
  else
    printf "  \033[31m✗\033[0m %s\n" "$name"
    echo "[${TIMESTAMP}] FAIL: ${name}" >> "$LOG_FILE"
    echo "  Command: $*" >> "$LOG_FILE"
    echo "  Output:  ${output}" >> "$LOG_FILE"
    echo "" >> "$LOG_FILE"
    ((FAIL++))
    HAS_ERRORS=true
  fi
}

echo ""
printf "\033[1m══════════════════════════════════════════════════\033[0m\n"
printf "\033[1m  PREFLIGHT — Claims Photo Fraud Detection\033[0m\n"
printf "\033[1m══════════════════════════════════════════════════\033[0m\n"

# ── Auth & Config ──────────────────────────────────────────────────
echo ""
printf "\033[1m─ GCP Auth\033[0m\n"
check "gcloud CLI installed" which gcloud
check "gcloud authenticated" gcloud auth print-access-token
check "Application Default Credentials" gcloud auth application-default print-access-token
check "Project set" gcloud config get-value project

PROJECT_ID=$(gcloud config get-value project 2>/dev/null || echo "")

# ── .env ───────────────────────────────────────────────────────────
echo ""
printf "\033[1m─ Local .env\033[0m\n"
check ".env file exists" test -f "$ENV_FILE"

if [[ -f "$ENV_FILE" ]]; then
  set -a; source "$ENV_FILE"; set +a
  check "GEMINI_API_KEY set" test -n "${GEMINI_API_KEY:-}"
  check "DB_PASSWORD set" test -n "${DB_PASSWORD:-}"
  check "SESSION_SECRET set" test -n "${SESSION_SECRET:-}"
  check "EXCHANGE_PASSWORD set" test -n "${EXCHANGE_PASSWORD:-}"
  check "EXCHANGE_SERVER set" test -n "${EXCHANGE_SERVER:-}"
  check "EXCHANGE_EMAIL set" test -n "${EXCHANGE_EMAIL:-}"
fi

# ── Tools ──────────────────────────────────────────────────────────
echo ""
printf "\033[1m─ Tools\033[0m\n"
check "terraform" which terraform
check "docker" which docker
check "node" which node
check "python3" which python3
check "Docker daemon" docker info

# ── GCP Project ────────────────────────────────────────────────────
echo ""
printf "\033[1m─ GCP Project\033[0m\n"
check "Project accessible" gcloud projects describe "$PROJECT_ID"
check "Billing enabled" bash -c "gcloud billing projects describe $PROJECT_ID 2>/dev/null | grep -q 'billingEnabled: true'"


# ── Terraform ─────────────────────────────────────────────────────
echo ""
printf "\033[1m─ Terraform\033[0m\n"
check "terraform validate" bash -c "cd ${PROJECT_ROOT}/terraform && terraform init -backend=false -input=false >/dev/null 2>&1 && terraform validate"

# ── Git ────────────────────────────────────────────────────────────
echo ""
printf "\033[1m─ Safety\033[0m\n"
check ".env gitignored" git check-ignore "$ENV_FILE"

# ── Summary ────────────────────────────────────────────────────────
echo ""
printf "\033[1m══════════════════════════════════════════════════\033[0m\n"
printf "\033[1m  ${PASS} passed, ${FAIL} failed\033[0m\n"
printf "\033[1m══════════════════════════════════════════════════\033[0m\n"

if [[ "$HAS_ERRORS" == true ]]; then
  echo "Errors logged to: ${LOG_FILE}"
  exit 1
fi

# No errors — no log file needed
rm -f "$LOG_FILE"
printf "\033[32mAll clear.\033[0m\n"
exit 0
