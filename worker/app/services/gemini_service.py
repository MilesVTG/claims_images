"""Gemini claim-level fraud analysis service (Section 6).

Aggregates all photos for a claim, sends to Gemini via google-generativeai SDK
with the system prompt from the DB and contract history context.  Parses the
structured JSON response.
"""

import json
import logging
from typing import Any

import google.generativeai as genai
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Prompt helpers
# ---------------------------------------------------------------------------

def get_active_prompt(db: Session, slug: str) -> str:
    """Fetch the active prompt content by slug from the database."""
    result = db.execute(
        text("SELECT content FROM system_prompts WHERE slug = :slug AND is_active = true"),
        {"slug": slug},
    ).fetchone()
    if not result:
        raise ValueError(f"No active prompt found for slug: {slug}")
    return result[0]


def get_contract_history(db: Session, contract_id: str, before_claim_id: str) -> list[dict]:
    """Fetch previous claims for a contract to feed into the Gemini prompt."""
    rows = db.execute(
        text("""
            SELECT
                claim_id,
                claim_date,
                risk_score,
                red_flags,
                gemini_analysis->>'tire_brands_detected' AS tire_brands,
                gemini_analysis->>'vehicle_colors_detected' AS vehicle_colors,
                gemini_analysis->>'damage_assessment' AS damage_summary,
                photo_uris
            FROM claims
            WHERE contract_id = :contract_id
              AND claim_id != :current_claim_id
            ORDER BY claim_date DESC
            LIMIT 10
        """),
        {"contract_id": contract_id, "current_claim_id": before_claim_id},
    ).fetchall()

    history = []
    for row in rows:
        history.append({
            "claim_id": row[0],
            "claim_date": str(row[1]) if row[1] else None,
            "risk_score": row[2],
            "red_flags": row[3],
            "tire_brands": row[4],
            "vehicle_colors": row[5],
            "damage_summary": row[6],
            "photo_uris": row[7],
        })
    return history


# ---------------------------------------------------------------------------
# Prompt building
# ---------------------------------------------------------------------------

def build_analysis_prompt(
    contract_id: str,
    claim_id: str,
    claim_data: dict[str, Any],
    exif_data: dict[str, Any],
    vision_data: dict[str, Any],
    history: list[dict],
) -> str:
    """Build the per-claim analysis prompt from template data."""
    history_text = "None (first claim for this contract)"
    if history:
        lines = []
        for h in history:
            lines.append(
                f"  - Claim {h['claim_id']} on {h['claim_date']}: "
                f"risk={h['risk_score']}, tires={h['tire_brands']}, "
                f"colors={h['vehicle_colors']}, damage={h['damage_summary']}"
            )
        history_text = "\n".join(lines)

    full_matches = len(vision_data.get("full_matching_images", []))
    similar = len(vision_data.get("visually_similar_images", []))

    prompt = f"""Analyze these photos for fraud indicators.

CONTRACT: {contract_id}

PREVIOUS CLAIMS (last 24 months):
{history_text}

CURRENT CLAIM:
  Claim ID: {claim_id}
  Reported Loss Date: {claim_data.get('reported_loss_date', 'N/A')}
  Service Drive Location: {claim_data.get('service_drive_location', 'N/A')}
  Service Drive Coordinates: {claim_data.get('service_drive_coords', 'N/A')}
  Photo EXIF Timestamp: {exif_data.get('DateTimeOriginal', 'N/A')}
  Photo GPS: {exif_data.get('gps_lat', 'N/A')}, {exif_data.get('gps_lon', 'N/A')}
  Reverse Image Hits: {full_matches} exact matches, {similar} similar

REQUIRED ANALYSIS:
  1. Extract visible tire brand(s) from ALL photos (read logos/text).
  2. Extract vehicle color from ALL photos.
  3. Check for recycled/duplicate images.
  4. Assess damage authenticity (fresh vs. staged).
  5. Flag inconsistencies: tire brand change, color change, impossible damage timeline.
  6. Compare EXIF GPS to service drive coords -- flag if >5 miles apart.
  7. Compare EXIF timestamp to reported loss date -- flag if >48 hrs.
  8. Note any reverse image search hits as strong fraud indicators.
  9. Overall fraud risk score (0-100).

RESPOND WITH ONLY VALID JSON:
{{
  "risk_score": <0-100>,
  "red_flags": ["flag1", "flag2"],
  "tire_brands_detected": {{"current": "...", "previous": ["..."]}},
  "vehicle_colors_detected": {{"current": "...", "previous": ["..."]}},
  "damage_assessment": "...",
  "geo_timestamp_check": {{
    "gps_vs_service_drive": "MATCH|MISMATCH (distance)",
    "timestamp_vs_loss_date": "MATCH|MISMATCH (details)"
  }},
  "reverse_image_flag": true|false,
  "explanation": "...",
  "recommendation": "..."
}}"""
    return prompt


# ---------------------------------------------------------------------------
# Gemini call
# ---------------------------------------------------------------------------

def analyze_claim_with_gemini(
    db: Session,
    contract_id: str,
    claim_id: str,
    claim_data: dict[str, Any],
    exif_data: dict[str, Any],
    vision_data: dict[str, Any],
    image_bytes_list: list[bytes],
    model: str | None = None,
) -> dict[str, Any]:
    """Send claim photos + prompt to Gemini for fraud analysis.

    Returns the parsed JSON response from Gemini.
    """
    model_name = model or settings.gemini_model
    genai.configure(api_key=settings.gemini_api_key)

    # Load prompts from DB
    system_instruction = get_active_prompt(db, "fraud_system_instruction")
    history = get_contract_history(db, contract_id, claim_id)

    analysis_prompt = build_analysis_prompt(
        contract_id, claim_id, claim_data, exif_data, vision_data, history
    )

    model_instance = genai.GenerativeModel(
        model_name=model_name,
        system_instruction=system_instruction,
    )

    # Build multimodal content: text prompt + images
    content_parts: list[Any] = [analysis_prompt]
    for img_bytes in image_bytes_list:
        content_parts.append({"mime_type": "image/jpeg", "data": img_bytes})

    logger.info(
        "Calling Gemini (%s) for contract=%s claim=%s with %d images",
        model_name, contract_id, claim_id, len(image_bytes_list),
    )

    response = model_instance.generate_content(content_parts)

    # Parse JSON from response — strip markdown fences if present
    response_text = response.text.strip()
    if response_text.startswith("```"):
        # Remove ```json ... ``` wrapper
        lines = response_text.split("\n")
        response_text = "\n".join(lines[1:-1]) if len(lines) > 2 else response_text

    try:
        result = json.loads(response_text)
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse Gemini JSON response: %s\nRaw: %s", exc, response_text[:500])
        result = {
            "risk_score": None,
            "red_flags": ["Gemini response was not valid JSON"],
            "raw_response": response_text[:2000],
            "explanation": "Analysis completed but response parsing failed",
            "recommendation": "Manual review required",
        }

    return result
