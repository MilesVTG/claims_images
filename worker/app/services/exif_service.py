"""EXIF extraction service (Section 4).

Extracts camera model, GPS coordinates, timestamps, software, and all other
EXIF metadata from photo bytes using Pillow.
"""

import io
import logging
from typing import Any

from PIL import Image, ExifTags

logger = logging.getLogger(__name__)


def parse_gps(gps_info: dict) -> dict[str, float | None]:
    """Convert EXIF GPS DMS (degrees/minutes/seconds) to decimal degrees.

    Handles both IFDRational tuples and plain float values that Pillow may
    return depending on the image source.
    """

    def _to_float(val) -> float:
        """Coerce an IFDRational or numeric to float."""
        if hasattr(val, "numerator") and hasattr(val, "denominator"):
            return float(val.numerator) / float(val.denominator) if val.denominator else 0.0
        return float(val)

    def dms_to_dd(dms, ref: str) -> float:
        degrees = _to_float(dms[0])
        minutes = _to_float(dms[1])
        seconds = _to_float(dms[2])
        dd = degrees + minutes / 60.0 + seconds / 3600.0
        return dd if ref in ("N", "E") else -dd

    try:
        # GPSInfo keys: 1=LatRef, 2=Lat, 3=LonRef, 4=Lon
        lat_ref = gps_info.get(1, "N")
        lat_dms = gps_info.get(2)
        lon_ref = gps_info.get(3, "E")
        lon_dms = gps_info.get(4)

        if lat_dms is None or lon_dms is None:
            return {"lat": None, "lon": None}

        lat = dms_to_dd(lat_dms, lat_ref)
        lon = dms_to_dd(lon_dms, lon_ref)
        return {"lat": round(lat, 6), "lon": round(lon, 6)}
    except (KeyError, IndexError, TypeError, ZeroDivisionError) as exc:
        logger.warning("GPS parsing failed: %s", exc)
        return {"lat": None, "lon": None}


def extract_exif(image_bytes: bytes) -> dict[str, Any]:
    """Extract all EXIF metadata from image bytes.

    Returns a flat dict with human-readable tag names as keys.  GPS data is
    extracted into top-level ``gps_lat``, ``gps_lon``, and ``gps_location``
    fields.  All values are serialisable (str/int/float/None).
    """
    metadata: dict[str, Any] = {}

    try:
        img = Image.open(io.BytesIO(image_bytes))
    except Exception as exc:
        logger.error("Failed to open image for EXIF extraction: %s", exc)
        return metadata

    exif = img.getexif()
    if not exif:
        logger.info("No EXIF data found in image")
        return metadata

    for tag_id, value in exif.items():
        tag_name = ExifTags.TAGS.get(tag_id, str(tag_id))

        if tag_name == "GPSInfo":
            # GPSInfo is a nested IFD — resolve it
            gps_ifd = exif.get_ifd(ExifTags.IFD.GPSInfo) if hasattr(ExifTags, "IFD") else value
            if isinstance(gps_ifd, dict):
                gps = parse_gps(gps_ifd)
            else:
                gps = parse_gps(value if isinstance(value, dict) else {})
            metadata["gps_lat"] = gps["lat"]
            metadata["gps_lon"] = gps["lon"]
            if gps["lat"] is not None and gps["lon"] is not None:
                metadata["gps_location"] = f"{gps['lat']},{gps['lon']}"
        elif isinstance(value, bytes):
            metadata[tag_name] = value.decode(errors="ignore")
        else:
            metadata[tag_name] = str(value)

    return metadata


def extract_ids_from_path(object_key: str) -> dict[str, str]:
    """Extract contract and claim IDs from a GCS object path.

    Expected format: ``{contract_id}/{claim_id}/filename.jpg``
    """
    parts = object_key.strip("/").split("/")
    return {
        "contract_id": parts[0] if len(parts) > 0 else "UNKNOWN",
        "claim_id": parts[1] if len(parts) > 1 else "UNKNOWN",
        "filename": parts[-1] if parts else object_key,
    }
