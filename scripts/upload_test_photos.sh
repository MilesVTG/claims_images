#!/usr/bin/env bash
set -euo pipefail

# Upload test claim photos to GCS in the correct {contract_id}/{claim_id}/ layout.
# Creates sample directories and placeholder images to trigger the pipeline for demos.
#
# Usage:
#   ./upload_test_photos.sh                     # Use defaults
#   ./upload_test_photos.sh --dir ./my-photos   # Upload real photos from a directory
#   ./upload_test_photos.sh --generate          # Generate placeholder test images

PROJECT_ID=$(gcloud config get-value project 2>/dev/null)
BUCKET="${GCS_BUCKET:-${PROJECT_ID}-claim-photos}"
PHOTO_DIR=""
GENERATE=false

usage() {
  echo "Usage: $0 [--dir <photo-dir>] [--generate] [--bucket <bucket>]"
  echo ""
  echo "Options:"
  echo "  --dir <path>    Upload real photos from this directory"
  echo "  --generate      Generate placeholder JPEG test images"
  echo "  --bucket <name> Override GCS bucket name"
  echo ""
  echo "Without --dir or --generate, generates placeholder images."
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dir)      PHOTO_DIR="$2"; shift 2 ;;
    --generate) GENERATE=true; shift ;;
    --bucket)   BUCKET="$2"; shift 2 ;;
    --help|-h)  usage ;;
    *)          echo "Unknown option: $1"; usage ;;
  esac
done

# Default to generate if no dir specified
[[ -z "$PHOTO_DIR" ]] && GENERATE=true

# ── Test claim definitions ──────────────────────────────────────────
# Each entry: contract_id claim_id photo_count description
CLAIMS=(
  "CNT-1001 CLM-2001 3 clean-roof-damage"
  "CNT-1001 CLM-2002 2 clean-water-damage"
  "CNT-1002 CLM-2003 4 suspicious-multiple-angles"
  "CNT-1003 CLM-2004 2 high-risk-stock-photos"
  "CNT-1004 CLM-2005 5 clean-vehicle-hail"
)

TEMP_DIR=$(mktemp -d)
trap 'rm -rf "$TEMP_DIR"' EXIT

generate_test_image() {
  local output="$1"
  local label="$2"
  # Create a minimal valid JPEG with EXIF-like data using Python
  python3 -c "
from PIL import Image, ImageDraw
import sys

img = Image.new('RGB', (640, 480), color=(
    hash(sys.argv[1]) % 200 + 55,
    hash(sys.argv[1] + 'g') % 200 + 55,
    hash(sys.argv[1] + 'b') % 200 + 55,
))
draw = ImageDraw.Draw(img)
draw.text((20, 20), f'Test: {sys.argv[1]}', fill='white')
draw.text((20, 50), 'Claims Photo Fraud Detection Demo', fill='white')
img.save(sys.argv[2], 'JPEG', quality=85)
" "$label" "$output" 2>/dev/null || {
    # Fallback: create a minimal 1x1 JPEG if Pillow not available
    printf '\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c $.\x27 ",#\x1c\x1c(7),01444\x1f\x27444444444444\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xda\x00\x08\x01\x01\x00\x00?\x00T\xdb\xe3\x9e\xf7\xd9\xff\xd9' > "$output"
  }
}

echo "=== Upload Test Photos ==="
echo "Bucket: gs://${BUCKET}"
echo ""

TOTAL=0

for claim_def in "${CLAIMS[@]}"; do
  read -r contract_id claim_id photo_count description <<< "$claim_def"
  gcs_prefix="${contract_id}/${claim_id}"

  echo "--- ${gcs_prefix} (${description}, ${photo_count} photos) ---"

  for i in $(seq 1 "$photo_count"); do
    filename="photo_$(printf '%02d' "$i").jpg"
    gcs_path="${gcs_prefix}/${filename}"

    if [[ "$GENERATE" == "true" ]]; then
      local_file="${TEMP_DIR}/${filename}"
      generate_test_image "$local_file" "${description}-${i}"
      gcloud storage cp "$local_file" "gs://${BUCKET}/${gcs_path}" --quiet
    else
      # Upload from provided directory — look for matching files
      src_dir="${PHOTO_DIR}/${contract_id}/${claim_id}"
      if [[ -d "$src_dir" ]]; then
        src_file=$(ls "${src_dir}"/*.{jpg,jpeg,png,webp} 2>/dev/null | sed -n "${i}p" || true)
        if [[ -n "$src_file" ]]; then
          gcloud storage cp "$src_file" "gs://${BUCKET}/${gcs_path}" --quiet
        else
          echo "  Warning: no photo #${i} in ${src_dir}, skipping"
          continue
        fi
      else
        echo "  Warning: ${src_dir} not found, skipping"
        continue
      fi
    fi

    echo "  Uploaded: gs://${BUCKET}/${gcs_path}"
    ((TOTAL++))
  done
done

echo ""
echo "=== Done: ${TOTAL} photos uploaded ==="
echo ""
echo "Uploaded claims layout:"
gcloud storage ls "gs://${BUCKET}/" --recursive 2>/dev/null | head -30 || true
