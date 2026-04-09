#!/usr/bin/env bash
set -euo pipefail

###############################################################################
# ensure_auth.sh — Verify and refresh GCP authentication
###############################################################################
#
# WHAT:
#   Checks that gcloud auth tokens are valid for the account/project in .env.
#   If tokens are expired, prompts for re-authentication. Exits non-zero if
#   auth can't be established.
#
# WHY:
#   Expired OAuth tokens cause every gcloud/deploy/provision command to fail
#   with a confusing "Reauthentication failed" error. This script catches it
#   early and fixes it in one place.
#
# USAGE:
#   ./scripts/ensure_auth.sh          # Standalone — verify + fix auth
#   source ./scripts/ensure_auth.sh   # Call from other scripts
#
# WHAT IT CHECKS:
#   1. .env exists and has GCP_ACCOUNT / GCP_PROJECT_ID
#   2. gcloud CLI is installed
#   3. Account is in gcloud's credentialed list
#   4. Tokens are valid (makes a real API call to verify)
#   5. Active project matches .env
#
# IF IT FAILS:
#   - No .env: create one (see .env.example or provision.sh)
#   - Account not credentialed: run gcloud auth login
#   - Tokens expired: script will launch gcloud auth login for you
#   - Wrong project: script sets it automatically
#
###############################################################################

# ── Colors ─────────────────────────────────────────────────────────
C="\033[36m"       # cyan — banners
O="\033[38;5;208m" # orange — section headers
R="\033[31m"       # red — errors
G="\033[32m"       # green — success
B="\033[1m"        # bold
X="\033[0m"        # reset

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${SCRIPT_DIR}/.."
ENV_FILE="${PROJECT_ROOT}/.env"

echo ""
printf "${C}${B}══════════════════════════════════════════════════${X}\n"
printf "${C}${B}  AUTH CHECK — Claims Photo Fraud Detection${X}\n"
printf "${C}${B}══════════════════════════════════════════════════${X}\n"

# ── 1. Load .env ──────────────────────────────────────────────────
printf "\n${O}${B}─ Loading .env${X}\n"
if [[ ! -f "$ENV_FILE" ]]; then
  printf "  ${R}ERROR: .env not found at ${ENV_FILE}${X}\n"
  exit 1
fi

set -a; source "$ENV_FILE"; set +a

ACCOUNT="${GCP_ACCOUNT:-}"
PROJECT="${GCP_PROJECT_ID:-}"

if [[ -z "$ACCOUNT" ]]; then
  printf "  ${R}ERROR: GCP_ACCOUNT not set in .env${X}\n"
  exit 1
fi
if [[ -z "$PROJECT" ]]; then
  printf "  ${R}ERROR: GCP_PROJECT_ID not set in .env${X}\n"
  exit 1
fi
printf "  Account:  ${ACCOUNT}\n"
printf "  Project:  ${PROJECT}\n"

# ── 2. gcloud installed ──────────────────────────────────────────
printf "\n${O}${B}─ Checking gcloud CLI${X}\n"
if ! command -v gcloud &>/dev/null; then
  printf "  ${R}ERROR: gcloud not found. Install: https://cloud.google.com/sdk/docs/install${X}\n"
  exit 1
fi
printf "  ${G}gcloud found${X}\n"

# ── 3. Account credentialed ──────────────────────────────────────
printf "\n${O}${B}─ Checking credentialed accounts${X}\n"
if ! gcloud auth list --format='value(account)' 2>/dev/null | grep -q "^${ACCOUNT}$"; then
  printf "  ${R}Account ${ACCOUNT} not found in gcloud auth list${X}\n"
  printf "  Launching login ...\n"
  gcloud auth login "$ACCOUNT"
fi
printf "  ${G}${ACCOUNT} is credentialed${X}\n"

# ── 4. Set active account ────────────────────────────────────────
printf "\n${O}${B}─ Setting active account${X}\n"
CURRENT_ACCOUNT=$(gcloud config get-value account 2>/dev/null)
if [[ "$CURRENT_ACCOUNT" != "$ACCOUNT" ]]; then
  gcloud config set account "$ACCOUNT" 2>/dev/null
  printf "  Switched from ${CURRENT_ACCOUNT} → ${ACCOUNT}\n"
else
  printf "  ${G}Already active${X}\n"
fi

# ── 5. Validate tokens (real API call) ───────────────────────────
printf "\n${O}${B}─ Validating auth tokens${X}\n"
if ! gcloud projects describe "$PROJECT" &>/dev/null; then
  printf "  ${R}Tokens expired or invalid — re-authenticating ...${X}\n"
  gcloud auth login "$ACCOUNT"
  # Verify again after login
  if ! gcloud projects describe "$PROJECT" &>/dev/null; then
    printf "  ${R}ERROR: Still can't access project ${PROJECT} after login${X}\n"
    printf "  ${R}Check that ${ACCOUNT} has access to this project${X}\n"
    exit 1
  fi
fi
printf "  ${G}Tokens valid${X}\n"

# ── 6. Set active project ────────────────────────────────────────
printf "\n${O}${B}─ Setting active project${X}\n"
CURRENT_PROJECT=$(gcloud config get-value project 2>/dev/null)
if [[ "$CURRENT_PROJECT" != "$PROJECT" ]]; then
  gcloud config set project "$PROJECT" 2>/dev/null
  printf "  Switched from ${CURRENT_PROJECT} → ${PROJECT}\n"
else
  printf "  ${G}Already set${X}\n"
fi

# ── Done ──────────────────────────────────────────────────────────
echo ""
printf "${C}${B}══════════════════════════════════════════════════${X}\n"
printf "${G}${B}  Auth OK — ${ACCOUNT} → ${PROJECT}${X}\n"
printf "${C}${B}══════════════════════════════════════════════════${X}\n"
