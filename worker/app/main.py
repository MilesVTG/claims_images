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
from app.middleware.error_logging import log_pipeline_error, register_error_handlers
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

# -- Error logging --
register_error_handlers(app, service="worker")


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
    # --- Stage: pubsub_parse ---
    try:
        envelope = await request.json()
        message = envelope.get("message", {})
        attrs = message.get("attributes", {})
        bucket = attrs.get("bucketId", settings.gcs_bucket)
        object_key = attrs.get("objectId", "")
        event_type = attrs.get("eventType", "")
    except Exception as exc:
        log_pipeline_error("/process", exc, pipeline_stage="pubsub_parse")
        raise

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

    # --- Stage: exif_extraction ---
    try:
        logger.info("Downloading photo: %s", object_key)
        image_bytes = download_photo(bucket, object_key)
        logger.info("Extracting EXIF for: %s", object_key)
        exif_data = extract_exif(image_bytes)
    except Exception as exc:
        log_pipeline_error("/process", exc, pipeline_stage="exif_extraction")
        raise

    # --- Stage: cloud_vision ---
    vision_data: dict[str, Any] = {}
    if settings.enable_cloud_vision:
        try:
            gs_uri = f"gs://{bucket}/{object_key}"
            logger.info("Running Cloud Vision for: %s", gs_uri)
            vision_data = reverse_image_lookup(gs_uri)
        except Exception as exc:
            log_pipeline_error("/process", exc, pipeline_stage="cloud_vision")
            logger.error("Vision API failed for %s: %s", object_key, exc)
            vision_data = {"error": str(exc)}

    # Mark photo as processed (idempotency)
    db.execute(
        text("""
            INSERT INTO processed_photos (storage_key, contract_id, claim_id, status)
            VALUES (:key, :cid, :clid, 'completed')
            ON CONFLICT (storage_key) DO NOTHING
        """),
        {"key": object_key, "cid": contract_id, "clid": claim_id},
    )
    db.commit()

    # --- Stage: gemini_analysis ---
    try:
        logger.info("Downloading all photos for %s/%s", contract_id, claim_id)
        image_bytes_list = download_photos_for_claim(bucket, contract_id, claim_id)
        if not image_bytes_list:
            logger.warning("No photos found in GCS for %s/%s", contract_id, claim_id)
            image_bytes_list = [download_photo(bucket, f"{contract_id}/{claim_id}/")]

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

        logger.info("Running Gemini analysis for %s/%s (%d photos)", contract_id, claim_id, len(image_bytes_list))
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
        log_pipeline_error("/process", exc, pipeline_stage="gemini_analysis")
        logger.error("Gemini analysis failed for %s/%s: %s", contract_id, claim_id, exc)
        gemini_result = {
            "risk_score": None,
            "red_flags": [f"Gemini analysis failed: {exc}"],
            "explanation": "Analysis could not be completed",
            "recommendation": "Manual review required",
        }

    # --- Stage: risk_scoring ---
    try:
        risk_result = compute_risk_score(exif_data, vision_data, gemini_result)
    except Exception as exc:
        log_pipeline_error("/process", exc, pipeline_stage="risk_scoring")
        raise

    # --- Stage: db_upsert ---
    try:
        is_sqlite = db.bind.dialect.name == "sqlite"
        if is_sqlite:
            db.execute(
                text("""
                    INSERT INTO claims (
                        contract_id, claim_id,
                        extracted_metadata, reverse_image_results,
                        gemini_analysis, risk_score, red_flags
                    ) VALUES (
                        :cid, :clid,
                        :meta, :vision,
                        :gemini, :score, :flags
                    )
                    ON CONFLICT (contract_id, claim_id)
                    DO UPDATE SET
                        extracted_metadata = :meta,
                        reverse_image_results = :vision,
                        gemini_analysis = :gemini,
                        risk_score = :score,
                        red_flags = :flags,
                        processed_at = datetime('now')
                """),
                {
                    "cid": contract_id,
                    "clid": claim_id,
                    "meta": _to_json(exif_data),
                    "vision": _to_json(vision_data),
                    "gemini": _to_json(gemini_result),
                    "score": risk_result["risk_score"],
                    "flags": _to_json(risk_result["red_flags"]),
                },
            )
        else:
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
    except Exception as exc:
        log_pipeline_error("/process", exc, pipeline_stage="db_upsert")
        raise

    logger.info(
        "Claim %s/%s processed: risk_score=%.1f, %d flags",
        contract_id, claim_id, risk_result["risk_score"], len(risk_result["red_flags"]),
    )

    # --- Stage: email_alert ---
    try:
        send_high_risk_alert(
            db=db,
            contract_id=contract_id,
            claim_id=claim_id,
            risk_score=risk_result["risk_score"],
            red_flags=risk_result["red_flags"],
        )
    except Exception as exc:
        log_pipeline_error("/process", exc, pipeline_stage="email_alert")
        logger.error("Failed to send high-risk alert for %s/%s: %s", contract_id, claim_id, exc)

    return {
        "status": "processed",
        "contract_id": contract_id,
        "claim_id": claim_id,
        "risk_score": risk_result["risk_score"],
        "red_flags_count": len(risk_result["red_flags"]),
    }
