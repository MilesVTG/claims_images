"""Risk scoring service (Section implied by CI-017).

Computes a composite 0-100 risk score from EXIF anomalies, Cloud Vision web
matches, and Gemini fraud indicators.  Produces an explainable red flag list.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Scoring weights (total max ~100)
# ---------------------------------------------------------------------------
WEIGHT_GEMINI_SCORE = 0.50       # Gemini's own 0-100 score contributes up to 50
WEIGHT_WEB_EXACT_MATCH = 20.0    # Per exact web match (capped)
WEIGHT_WEB_PARTIAL_MATCH = 8.0   # Per partial web match (capped)
WEIGHT_EXIF_TIMESTAMP_MISMATCH = 10.0
WEIGHT_EXIF_GPS_MISMATCH = 10.0
WEIGHT_EXIF_SOFTWARE_EDIT = 8.0
WEIGHT_EXIF_NO_DATA = 5.0

# Known photo editing software signatures
EDITING_SOFTWARE = {
    "photoshop", "gimp", "lightroom", "affinity", "pixelmator", "snapseed",
    "adobe", "canva", "paint.net", "corel", "faceapp", "facetune",
}

MAX_SCORE = 100.0


def _check_exif_anomalies(exif_data: dict[str, Any]) -> tuple[float, list[str]]:
    """Score EXIF-based anomalies and return (points, flags)."""
    points = 0.0
    flags: list[str] = []

    if not exif_data:
        points += WEIGHT_EXIF_NO_DATA
        flags.append("No EXIF metadata found — possible screenshot or edited image")
        return points, flags

    # Software/editing detection
    software = (exif_data.get("Software") or "").lower()
    if software:
        for editor in EDITING_SOFTWARE:
            if editor in software:
                points += WEIGHT_EXIF_SOFTWARE_EDIT
                flags.append(f"Photo editing software detected: {exif_data['Software']}")
                break

    # Timestamp check is handled by Gemini's geo_timestamp_check but we
    # also flag if DateTimeOriginal is completely missing
    if not exif_data.get("DateTimeOriginal"):
        points += 2.0
        flags.append("Missing DateTimeOriginal EXIF tag")

    return points, flags


def _check_vision_anomalies(vision_data: dict[str, Any]) -> tuple[float, list[str]]:
    """Score Cloud Vision web detection anomalies."""
    points = 0.0
    flags: list[str] = []

    if not vision_data:
        return points, flags

    full_matches = vision_data.get("full_matching_images", [])
    partial_matches = vision_data.get("partial_matching_images", [])
    pages = vision_data.get("pages_with_matching_images", [])

    if full_matches:
        match_points = min(len(full_matches) * WEIGHT_WEB_EXACT_MATCH, 25.0)
        points += match_points
        flags.append(
            f"Exact web match: {len(full_matches)} identical image(s) found online"
        )
        # Include first URL for context
        if full_matches:
            flags.append(f"  First match URL: {full_matches[0]}")

    if partial_matches:
        partial_points = min(len(partial_matches) * WEIGHT_WEB_PARTIAL_MATCH, 15.0)
        points += partial_points
        flags.append(
            f"Partial web match: {len(partial_matches)} cropped/modified version(s) found"
        )

    if pages:
        flags.append(
            f"Image appears on {len(pages)} web page(s)"
        )

    return points, flags


def _check_gemini_anomalies(gemini_data: dict[str, Any]) -> tuple[float, list[str]]:
    """Score from Gemini's own analysis."""
    points = 0.0
    flags: list[str] = []

    if not gemini_data:
        return points, flags

    # Gemini risk score (weighted)
    gemini_score = gemini_data.get("risk_score")
    if gemini_score is not None and isinstance(gemini_score, (int, float)):
        points += gemini_score * WEIGHT_GEMINI_SCORE

    # Gemini red flags
    gemini_flags = gemini_data.get("red_flags", [])
    if gemini_flags:
        flags.extend(gemini_flags)

    # Geo/timestamp checks from Gemini
    geo_check = gemini_data.get("geo_timestamp_check", {})
    if geo_check:
        gps_status = (geo_check.get("gps_vs_service_drive") or "").upper()
        if "MISMATCH" in gps_status:
            points += WEIGHT_EXIF_GPS_MISMATCH
            flags.append(f"GPS mismatch with service drive: {geo_check['gps_vs_service_drive']}")

        ts_status = (geo_check.get("timestamp_vs_loss_date") or "").upper()
        if "MISMATCH" in ts_status:
            points += WEIGHT_EXIF_TIMESTAMP_MISMATCH
            flags.append(f"Timestamp mismatch: {geo_check['timestamp_vs_loss_date']}")

    # Reverse image flag from Gemini
    if gemini_data.get("reverse_image_flag") is True:
        # Already counted in vision anomalies, but note it
        flags.append("Gemini confirmed reverse image match significance")

    return points, flags


def compute_risk_score(
    exif_data: dict[str, Any],
    vision_data: dict[str, Any],
    gemini_data: dict[str, Any],
) -> dict[str, Any]:
    """Compute composite risk score from all analysis sources.

    Returns:
        Dict with ``risk_score`` (0-100 float), ``red_flags`` (list of strings),
        and ``score_breakdown`` explaining each component.
    """
    total = 0.0
    all_flags: list[str] = []
    breakdown: dict[str, float] = {}

    # EXIF anomalies
    exif_points, exif_flags = _check_exif_anomalies(exif_data)
    total += exif_points
    all_flags.extend(exif_flags)
    breakdown["exif_anomalies"] = round(exif_points, 1)

    # Vision web matches
    vision_points, vision_flags = _check_vision_anomalies(vision_data)
    total += vision_points
    all_flags.extend(vision_flags)
    breakdown["vision_web_matches"] = round(vision_points, 1)

    # Gemini analysis
    gemini_points, gemini_flags = _check_gemini_anomalies(gemini_data)
    total += gemini_points
    all_flags.extend(gemini_flags)
    breakdown["gemini_analysis"] = round(gemini_points, 1)

    # Clamp to 0-100
    final_score = round(min(max(total, 0.0), MAX_SCORE), 1)

    # De-duplicate flags while preserving order
    seen = set()
    unique_flags = []
    for flag in all_flags:
        if flag not in seen:
            seen.add(flag)
            unique_flags.append(flag)

    logger.info(
        "Risk score computed: %.1f (exif=%.1f, vision=%.1f, gemini=%.1f), %d flags",
        final_score, exif_points, vision_points, gemini_points, len(unique_flags),
    )

    return {
        "risk_score": final_score,
        "red_flags": unique_flags,
        "score_breakdown": breakdown,
    }
