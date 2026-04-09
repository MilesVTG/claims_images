"""Worker FastAPI application — Pub/Sub trigger handler (Section 3).

Receives GCS upload push messages via POST /process, orchestrates per-photo
processing (EXIF + Vision), then claim-level analysis (Gemini + risk scoring).
Idempotency via processed_photos table.
"""

import logging
from typing import Any

from fastapi import FastAPI, Request, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session
from google.cloud import storage

from app.config import settings
from app.database import get_db
from app.services.exif_service import extract_exif, extract_ids_from_path
from app.services.vision_service import reverse_image_lookup
from app.services.gemini_service import analyze_claim_with_gemini
from app.services.risk_service import compute_risk_score
from app.services.email_service import send_high_risk_alert

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Claims Photo Fraud Detection Worker",
    version="0.1.0",
)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok", "service": "worker"}


# ---------------------------------------------------------------------------
# GCS helpers
# ---------------------------------------------------------------------------

def download_photo(bucket_name: str, object_key: str) -> bytes:
    """Download photo bytes from GCS."""
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(object_key)
    return blob.download_as_bytes()


def download_photos_for_claim(
    bucket_name: str, contract_id: str, claim_id: str,
) -> list[bytes]:
    """Download all photo bytes for a claim from GCS."""
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    prefix = f"{contract_id}/{claim_id}/"
    blobs = list(bucket.list_blobs(prefix=prefix))
    image_bytes_list = []
    for blob in blobs:
        if blob.name.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
            image_bytes_list.append(blob.download_as_bytes())
    return image_bytes_list


# ---------------------------------------------------------------------------
# Per-photo processing
# ---------------------------------------------------------------------------

def process_single_photo(
    db: Session,
    bucket: str,
    object_key: str,
) -> dict[str, Any]:
    """Run per-photo pipeline: EXIF extraction + Cloud Vision.

    Returns dict with exif_data and vision_data.
    """
    gs_uri = f"gs://{bucket}/{object_key}"
    ids = extract_ids_from_path(object_key)

    # Download and extract EXIF
    logger.info("Downloading photo: %s", object_key)
    image_bytes = download_photo(bucket, object_key)

    logger.info("Extracting EXIF for: %s", object_key)
    exif_data = extract_exif(image_bytes)

    # Cloud Vision (if enabled)
    vision_data: dict[str, Any] = {}
    if settings.enable_cloud_vision:
        logger.info("Running Cloud Vision for: %s", gs_uri)
        try:
            vision_data = reverse_image_lookup(gs_uri)
        except Exception as exc:
            logger.error("Vision API failed for %s: %s", gs_uri, exc)
            vision_data = {"error": str(exc)}

    # Mark photo as processed (idempotency)
    db.execute(
        text("""
            INSERT INTO processed_photos (storage_key, contract_id, claim_id, status)
            VALUES (:key, :cid, :clid, 'completed')
            ON CONFLICT (storage_key) DO NOTHING
        """),
        {
            "key": object_key,
            "cid": ids["contract_id"],
            "clid": ids["claim_id"],
        },
    )
    db.commit()

    return {
        "exif_data": exif_data,
        "vision_data": vision_data,
        "ids": ids,
    }


# ---------------------------------------------------------------------------
# Claim-level analysis
# ---------------------------------------------------------------------------

def run_claim_analysis(
    db: Session,
    bucket: str,
    contract_id: str,
    claim_id: str,
    exif_data: dict[str, Any],
    vision_data: dict[str, Any],
) -> dict[str, Any]:
    """Run claim-level Gemini analysis and risk scoring.

    Aggregates all photos for the claim, calls Gemini, computes composite
    risk score, and updates the claims table.
    """
    # Get claim data from DB (may not exist yet for brand new claims)
    claim_row = db.execute(
        text("SELECT * FROM claims WHERE contract_id = :cid AND claim_id = :clid"),
        {"cid": contract_id, "clid": claim_id},
    ).fetchone()

    claim_data: dict[str, Any] = {}
    if claim_row:
        claim_data = {
            "reported_loss_date": str(claim_row.reported_loss_date) if claim_row.reported_loss_date else None,
            "service_drive_location": claim_row.service_drive_location,
            "service_drive_coords": claim_row.service_drive_coords,
        }

    # Download all photos for this claim
    logger.info("Downloading all photos for %s/%s", contract_id, claim_id)
    image_bytes_list = download_photos_for_claim(bucket, contract_id, claim_id)
    if not image_bytes_list:
        logger.warning("No photos found in GCS for %s/%s", contract_id, claim_id)
        image_bytes_list = [download_photo(bucket, f"{contract_id}/{claim_id}/")]

    # Call Gemini
    logger.info("Running Gemini analysis for %s/%s (%d photos)", contract_id, claim_id, len(image_bytes_list))
    try:
        gemini_result = analyze_claim_with_gemini(
            db=db,
            contract_id=contract_id,
            claim_id=claim_id,
            claim_data=claim_data,
            exif_data=exif_data,
            vision_data=vision_data,
            image_bytes_list=image_bytes_list,
        )
    except Exception as exc:
        logger.error("Gemini analysis failed for %s/%s: %s", contract_id, claim_id, exc)
        gemini_result = {
            "risk_score": None,
            "red_flags": [f"Gemini analysis failed: {exc}"],
            "explanation": "Analysis could not be completed",
            "recommendation": "Manual review required",
        }

    # Compute composite risk score
    risk_result = compute_risk_score(exif_data, vision_data, gemini_result)

    # Upsert into claims table
    db.execute(
        text("""
            INSERT INTO claims (
                contract_id, claim_id,
                extracted_metadata, reverse_image_results,
                gemini_analysis, risk_score, red_flags
            ) VALUES (
                :cid, :clid,
                :meta::jsonb, :vision::jsonb,
                :gemini::jsonb, :score, :flags
            )
            ON CONFLICT (contract_id, claim_id)
            DO UPDATE SET
                extracted_metadata = :meta::jsonb,
                reverse_image_results = :vision::jsonb,
                gemini_analysis = :gemini::jsonb,
                risk_score = :score,
                red_flags = :flags,
                processed_at = NOW()
        """),
        {
            "cid": contract_id,
            "clid": claim_id,
            "meta": _to_json(exif_data),
            "vision": _to_json(vision_data),
            "gemini": _to_json(gemini_result),
            "score": risk_result["risk_score"],
            "flags": risk_result["red_flags"],
        },
    )
    db.commit()

    logger.info(
        "Claim %s/%s processed: risk_score=%.1f, %d flags",
        contract_id, claim_id, risk_result["risk_score"], len(risk_result["red_flags"]),
    )

    # High-risk email alert
    try:
        send_high_risk_alert(
            db=db,
            contract_id=contract_id,
            claim_id=claim_id,
            risk_score=risk_result["risk_score"],
            red_flags=risk_result["red_flags"],
        )
    except Exception as exc:
        logger.error("Failed to send high-risk alert for %s/%s: %s", contract_id, claim_id, exc)

    return {
        "risk_score": risk_result["risk_score"],
        "red_flags": risk_result["red_flags"],
        "gemini_analysis": gemini_result,
    }


def _to_json(data: Any) -> str:
    """Serialise to JSON string for JSONB casting."""
    import json
    return json.dumps(data, default=str)


# ---------------------------------------------------------------------------
# Pub/Sub push endpoint
# ---------------------------------------------------------------------------

@app.post("/process")
async def handle_pubsub_push(request: Request, db: Session = Depends(get_db)):
    """Receive Pub/Sub push message on GCS upload.

    Expected payload (GCS notification format):
    {
      "message": {
        "attributes": {
          "bucketId": "...",
          "objectId": "contract_id/claim_id/photo.jpg",
          "eventType": "OBJECT_FINALIZE"
        }
      }
    }

    Orchestrates: per-photo (EXIF + Vision) then claim-level (Gemini + risk).
    Idempotent — skips already-processed photos.
    """
    envelope = await request.json()

    # Parse Pub/Sub message
    message = envelope.get("message", {})
    attrs = message.get("attributes", {})
    bucket = attrs.get("bucketId", settings.gcs_bucket)
    object_key = attrs.get("objectId", "")
    event_type = attrs.get("eventType", "")

    if not object_key:
        logger.warning("Received push with no objectId, ignoring")
        return {"status": "ignored", "reason": "no objectId"}

    # Only process image uploads
    if not object_key.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
        logger.info("Ignoring non-image object: %s", object_key)
        return {"status": "ignored", "reason": "not an image"}

    # Idempotency check
    existing = db.execute(
        text("SELECT id FROM processed_photos WHERE storage_key = :key"),
        {"key": object_key},
    ).fetchone()

    if existing:
        logger.info("Photo already processed, skipping: %s", object_key)
        return {"status": "skipped", "reason": "already processed"}

    ids = extract_ids_from_path(object_key)
    contract_id = ids["contract_id"]
    claim_id = ids["claim_id"]

    logger.info(
        "Processing photo: bucket=%s, key=%s, contract=%s, claim=%s",
        bucket, object_key, contract_id, claim_id,
    )

    # Stage 1: Per-photo processing
    photo_result = process_single_photo(db, bucket, object_key)

    # Stage 2: Claim-level analysis
    analysis_result = run_claim_analysis(
        db=db,
        bucket=bucket,
        contract_id=contract_id,
        claim_id=claim_id,
        exif_data=photo_result["exif_data"],
        vision_data=photo_result["vision_data"],
    )

    return {
        "status": "processed",
        "contract_id": contract_id,
        "claim_id": claim_id,
        "risk_score": analysis_result["risk_score"],
        "red_flags_count": len(analysis_result["red_flags"]),
    }
