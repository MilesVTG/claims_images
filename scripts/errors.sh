#!/usr/bin/env bash
set -uo pipefail

###############################################################################
# errors.sh — Query error logs from the API for quick CLI diagnostics
###############################################################################
#
# USAGE:
#   ./scripts/errors.sh [OPTIONS]
#
# OPTIONS:
#   --service api|worker   Filter by service
#   --stage STAGE          Filter by pipeline stage (e.g. gemini_analysis)
#   --type TYPE            Filter by error type (e.g. ValueError)
#   --since DATE           Show errors since date (ISO format, e.g. 2026-04-01)
#   --limit N              Number of results (default: 20)
#   --stats                Show aggregate counts instead of error list
#   --url URL              API base URL (default: http://localhost:8000)
#   --help                 Show this help
#
###############################################################################

# ── Defaults ──────────────────────────────────────────────────────────
API_BASE="${API_URL:-http://localhost:8000}"
SERVICE=""
STAGE=""
ERROR_TYPE=""
SINCE=""
LIMIT=20
SHOW_STATS=false

# ── Colors ────────────────────────────────────────────────────────────
C="\033[36m"       # cyan
O="\033[38;5;208m" # orange
R="\033[31m"       # red
G="\033[32m"       # green
Y="\033[33m"       # yellow
B="\033[1m"        # bold
D="\033[2m"        # dim
X="\033[0m"        # reset

# ── Parse args ────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --service)  SERVICE="$2"; shift 2 ;;
    --stage)    STAGE="$2"; shift 2 ;;
    --type)     ERROR_TYPE="$2"; shift 2 ;;
    --since)    SINCE="$2"; shift 2 ;;
    --limit)    LIMIT="$2"; shift 2 ;;
    --stats)    SHOW_STATS=true; shift ;;
    --url)      API_BASE="$2"; shift 2 ;;
    --help|-h)
      sed -n '/^# USAGE:/,/^###/p' "$0" | head -n -1 | sed 's/^# \?//'
      exit 0
      ;;
    *)
      echo "Unknown option: $1 (try --help)"
      exit 1
      ;;
  esac
done

# ── Stats mode ────────────────────────────────────────────────────────
if $SHOW_STATS; then
  QUERY=""
  [[ -n "$SERVICE" ]] && QUERY="${QUERY}&service=${SERVICE}"
  [[ -n "$SINCE" ]]   && QUERY="${QUERY}&since=${SINCE}"
  QUERY="${QUERY#&}"

  URL="${API_BASE}/api/errors/stats"
  [[ -n "$QUERY" ]] && URL="${URL}?${QUERY}"

  RESP=$(curl -sf -m 10 "$URL" 2>&1) || {
    printf "${R}Failed to reach ${URL}${X}\n"
    exit 1
  }

  printf "\n${C}${B}══ Error Stats ══${X}\n\n"

  TOTAL=$(echo "$RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['total'])")
  printf "${B}Total errors: ${TOTAL}${X}\n\n"

  printf "${O}${B}By Service:${X}\n"
  echo "$RESP" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for item in data.get('by_service', []):
    print(f\"  {item['service']:<12} {item['count']}\")
" 2>/dev/null || printf "  ${D}(none)${X}\n"

  printf "\n${O}${B}By Error Type:${X}\n"
  echo "$RESP" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for item in data.get('by_error_type', []):
    print(f\"  {item['error_type']:<30} {item['count']}\")
" 2>/dev/null || printf "  ${D}(none)${X}\n"

  printf "\n${O}${B}By Pipeline Stage:${X}\n"
  echo "$RESP" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for item in data.get('by_pipeline_stage', []):
    print(f\"  {item['pipeline_stage']:<20} {item['count']}\")
" 2>/dev/null || printf "  ${D}(none)${X}\n"

  echo ""
  exit 0
fi

# ── List mode ─────────────────────────────────────────────────────────
QUERY="per_page=${LIMIT}"
[[ -n "$SERVICE" ]]    && QUERY="${QUERY}&service=${SERVICE}"
[[ -n "$STAGE" ]]      && QUERY="${QUERY}&pipeline_stage=${STAGE}"
[[ -n "$ERROR_TYPE" ]] && QUERY="${QUERY}&error_type=${ERROR_TYPE}"
[[ -n "$SINCE" ]]      && QUERY="${QUERY}&since=${SINCE}"

URL="${API_BASE}/api/errors?${QUERY}"

RESP=$(curl -sf -m 10 "$URL" 2>&1) || {
  printf "${R}Failed to reach ${URL}${X}\n"
  exit 1
}

TOTAL=$(echo "$RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['total'])")
COUNT=$(echo "$RESP" | python3 -c "import sys,json; print(len(json.load(sys.stdin)['items']))")

printf "\n${C}${B}══ Error Logs ══${X}  ${D}(showing ${COUNT} of ${TOTAL})${X}\n\n"

if [[ "$COUNT" == "0" ]]; then
  printf "${G}No errors found.${X}\n\n"
  exit 0
fi

echo "$RESP" | python3 -c "
import sys, json

data = json.load(sys.stdin)
for e in data['items']:
    svc = e.get('service', '?')
    ts  = (e.get('timestamp') or '?')[:19]
    etype = e.get('error_type') or '?'
    msg = (e.get('message') or '')[:120]
    stage = e.get('pipeline_stage') or ''
    ep  = e.get('endpoint') or ''

    color_svc = '\033[36m' if svc == 'api' else '\033[33m'
    print(f\"  \033[2m{ts}\033[0m  {color_svc}\033[1m{svc:<7}\033[0m  \033[31m{etype}\033[0m\")
    if stage:
        print(f\"    stage: {stage}  endpoint: {ep}\")
    elif ep:
        print(f\"    endpoint: {ep}\")
    if msg:
        print(f\"    {msg}\")
    print()
"

exit 0
