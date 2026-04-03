"""Seed golden dataset — generate test photos and upload to GCS.

Creates synthetic test images (fraud + clean) with controlled EXIF metadata,
uploads them to the GCS test bucket under golden/ prefix, and inserts
golden_dataset records into the database.

Usage (local dev):
    DATABASE_URL=postgresql+pg8000://user:pass@localhost/claims python scripts/seed_golden_dataset.py

Usage (Cloud SQL):
    source .env && python scripts/seed_golden_dataset.py

Options:
    --skip-upload   Skip GCS upload (DB records only)
    --bucket NAME   Override GCS bucket name
"""

import io
import json
import os
import struct
import sys

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

# Add project root so we can import samples
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from tests.golden_dataset.samples import ALL_SAMPLES, FRAUD_SAMPLES, CLEAN_SAMPLES


# ---------------------------------------------------------------------------
# Database engine (same pattern as seed.py)
# ---------------------------------------------------------------------------

def _build_engine():
    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        return create_engine(database_url)

    from google.cloud.sql.connector import Connector

    instance = os.environ["CLOUD_SQL_CONNECTION_NAME"]
    db_user = os.environ.get("DB_USER", "fraud_user")
    db_pass = os.environ["DB_PASSWORD"]
    db_name = os.environ.get("DB_NAME", "claims")

    connector = Connector(refresh_strategy="lazy")

    def _getconn():
        return connector.connect(instance, "pg8000", user=db_user, password=db_pass, db=db_name)

    return create_engine("postgresql+pg8000://", creator=_getconn)


# ---------------------------------------------------------------------------
# Synthetic image generation
# ---------------------------------------------------------------------------

def _make_minimal_jpeg(width: int = 100, height: int = 100, color: tuple = (200, 50, 50)) -> bytes:
    """Create a minimal valid JPEG image without Pillow.

    Generates a small solid-color JPEG using raw JFIF encoding.
    """
    try:
        from PIL import Image
        img = Image.new("RGB", (width, height), color)
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        return buf.getvalue()
    except ImportError:
        # Fallback: create a minimal valid JPEG header + data
        # This is a 1x1 red pixel JPEG
        return (
            b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00'
            b'\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t'
            b'\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a'
            b'\x1f\x1e\x1d\x1a\x1c\x1c $.\' ",#\x1c\x1c(7),01444\x1f\'9=82<.342'
            b'\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00'
            b'\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00'
            b'\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b'
            b'\xff\xc4\x00\xb5\x10\x00\x02\x01\x03\x03\x02\x04\x03\x05\x05\x04'
            b'\x04\x00\x00\x01}\x01\x02\x03\x00\x04\x11\x05\x12!1A\x06\x13Qa\x07'
            b'"q\x142\x81\x91\xa1\x08#B\xb1\xc1\x15R\xd1\xf0$3br\x82\t\n\x16\x17'
            b'\x18\x19\x1a%&\'()*456789:CDEFGHIJSTUVWXYZcdefghijstuvwxyz'
            b'\x83\x84\x85\x86\x87\x88\x89\x8a\x92\x93\x94\x95\x96\x97\x98\x99'
            b'\x9a\xa2\xa3\xa4\xa5\xa6\xa7\xa8\xa9\xaa\xb2\xb3\xb4\xb5\xb6\xb7'
            b'\xb8\xb9\xba\xc2\xc3\xc4\xc5\xc6\xc7\xc8\xc9\xca\xd2\xd3\xd4\xd5'
            b'\xd6\xd7\xd8\xd9\xda\xe1\xe2\xe3\xe4\xe5\xe6\xe7\xe8\xe9\xea\xf1'
            b'\xf2\xf3\xf4\xf5\xf6\xf7\xf8\xf9\xfa'
            b'\xff\xda\x00\x08\x01\x01\x00\x00?\x00T\xdb\x9e\xa7\x13\xfc\xd3'
            b'\xff\xd9'
        )


def _make_jpeg_with_exif(
    width: int = 100,
    height: int = 100,
    color: tuple = (200, 50, 50),
    software: str | None = None,
    datetime_original: str | None = None,
    gps_lat: float | None = None,
    gps_lon: float | None = None,
    strip_exif: bool = False,
) -> bytes:
    """Create a JPEG with specific EXIF tags for testing."""
    try:
        from PIL import Image
        import piexif
    except ImportError:
        # Without Pillow/piexif, return a basic JPEG
        return _make_minimal_jpeg(width, height, color)

    img = Image.new("RGB", (width, height), color)

    if strip_exif:
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        return buf.getvalue()

    exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}}

    if software:
        exif_dict["0th"][piexif.ImageIFD.Software] = software.encode()

    if datetime_original:
        exif_dict["Exif"][piexif.ExifIFD.DateTimeOriginal] = datetime_original.encode()

    if gps_lat is not None and gps_lon is not None:
        lat_ref = b"N" if gps_lat >= 0 else b"S"
        lon_ref = b"E" if gps_lon >= 0 else b"W"
        lat_abs = abs(gps_lat)
        lon_abs = abs(gps_lon)

        lat_d = int(lat_abs)
        lat_m = int((lat_abs - lat_d) * 60)
        lat_s = int(((lat_abs - lat_d) * 60 - lat_m) * 60 * 100)

        lon_d = int(lon_abs)
        lon_m = int((lon_abs - lon_d) * 60)
        lon_s = int(((lon_abs - lon_d) * 60 - lon_m) * 60 * 100)

        exif_dict["GPS"][piexif.GPSIFD.GPSLatitudeRef] = lat_ref
        exif_dict["GPS"][piexif.GPSIFD.GPSLatitude] = (
            (lat_d, 1), (lat_m, 1), (lat_s, 100),
        )
        exif_dict["GPS"][piexif.GPSIFD.GPSLongitudeRef] = lon_ref
        exif_dict["GPS"][piexif.GPSIFD.GPSLongitude] = (
            (lon_d, 1), (lon_m, 1), (lon_s, 100),
        )

    exif_bytes = piexif.dump(exif_dict)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif_bytes)
    return buf.getvalue()


# Image specs for each golden sample
IMAGE_SPECS = {
    "fraud_stock_tire_damage": {
        "color": (180, 60, 40),
        "datetime_original": "2026:01:10 14:30:00",
    },
    "fraud_tire_brand_mismatch": {
        "color": (50, 50, 50),
        "datetime_original": "2026:03:15 09:00:00",
        "gps_lat": 41.8781,
        "gps_lon": -87.6298,
    },
    "fraud_photoshop_edited": {
        "color": (100, 30, 30),
        "software": "Adobe Photoshop CC 2024",
        "datetime_original": "2026:02:20 11:00:00",
    },
    "fraud_gps_mismatch": {
        "color": (80, 80, 80),
        "datetime_original": "2026:02:25 16:45:00",
        "gps_lat": 34.0522,  # LA — far from Chicago service drive
        "gps_lon": -118.2437,
    },
    "fraud_stripped_exif": {
        "color": (150, 150, 150),
        "strip_exif": True,
    },
    "fraud_timestamp_mismatch": {
        "color": (70, 70, 120),
        "datetime_original": "2025:12:01 08:00:00",  # 30+ days before loss
        "gps_lat": 41.8781,
        "gps_lon": -87.6298,
    },
    "clean_legitimate_front_damage": {
        "color": (30, 90, 180),
        "datetime_original": "2026:03:20 10:15:00",
        "gps_lat": 41.8819,
        "gps_lon": -87.6278,
    },
    "clean_consistent_tires": {
        "color": (20, 20, 20),
        "datetime_original": "2026:03:22 14:30:00",
        "gps_lat": 41.8800,
        "gps_lon": -87.6290,
    },
    "clean_gps_matches": {
        "color": (40, 60, 180),
        "datetime_original": "2026:03:25 11:00:00",
        "gps_lat": 41.8785,
        "gps_lon": -87.6300,
    },
}


def generate_test_images() -> dict[str, bytes]:
    """Generate all golden dataset test images.

    Returns dict mapping sample name -> JPEG bytes.
    """
    images = {}
    for sample in ALL_SAMPLES:
        name = sample["name"]
        spec = IMAGE_SPECS.get(name, {})
        images[name] = _make_jpeg_with_exif(**spec)
        print(f"  Generated: {name} ({len(images[name])} bytes)")
    return images


# ---------------------------------------------------------------------------
# GCS upload
# ---------------------------------------------------------------------------

def upload_to_gcs(images: dict[str, bytes], bucket_name: str) -> None:
    """Upload golden dataset images to GCS."""
    from google.cloud import storage

    client = storage.Client()
    bucket = client.bucket(bucket_name)

    sample_map = {s["name"]: s for s in ALL_SAMPLES}

    for name, image_bytes in images.items():
        sample = sample_map[name]
        storage_key = sample["storage_key"]
        blob = bucket.blob(storage_key)
        blob.upload_from_string(image_bytes, content_type="image/jpeg")
        print(f"  Uploaded: gs://{bucket_name}/{storage_key}")

    print(f"  Uploaded {len(images)} images to gs://{bucket_name}/golden/")


# ---------------------------------------------------------------------------
# Database seeding
# ---------------------------------------------------------------------------

def seed_golden_dataset_records(session: Session) -> None:
    """Insert golden_dataset records into the database."""
    for sample in ALL_SAMPLES:
        session.execute(
            text("""
                INSERT INTO golden_dataset (
                    name, storage_key, expected_risk_min, expected_risk_max,
                    expected_flags, must_not_flags, expected_tire_brand,
                    expected_color, notes
                ) VALUES (
                    :name, :key, :risk_min, :risk_max,
                    :flags, :not_flags, :tire, :color, :notes
                )
                ON CONFLICT DO NOTHING
            """),
            {
                "name": sample["name"],
                "key": sample["storage_key"],
                "risk_min": sample["expected_risk_min"],
                "risk_max": sample["expected_risk_max"],
                "flags": sample["expected_flags"] or None,
                "not_flags": sample["must_not_flags"] or None,
                "tire": sample.get("expected_tire_brand"),
                "color": sample.get("expected_color"),
                "notes": sample.get("notes"),
            },
        )

    print(f"  Seeded {len(ALL_SAMPLES)} golden dataset records.")


def seed_golden_claims(session: Session) -> None:
    """Insert claim records that correspond to golden dataset entries.

    These set up the contract context (prior claims, service drive location)
    needed for the worker to produce meaningful analysis.
    """
    golden_claims = [
        # Fraud claims — set up service drive in Chicago so GPS mismatches are detectable
        ("FRAUD_CONTRACT_001", "CLM_FRAUD_001", "2026-01-15", "2026-01-10",
         "Chicago Service Center", "41.8781,-87.6298"),
        ("FRAUD_CONTRACT_002", "CLM_FRAUD_002", "2026-03-20", "2026-03-15",
         "Chicago Service Center", "41.8781,-87.6298"),
        # Prior claim for tire brand mismatch context
        ("FRAUD_CONTRACT_002", "CLM_FRAUD_002_PRIOR", "2025-12-01", "2025-11-28",
         "Chicago Service Center", "41.8781,-87.6298"),
        ("FRAUD_CONTRACT_003", "CLM_FRAUD_003", "2026-02-25", "2026-02-20",
         "Chicago Service Center", "41.8781,-87.6298"),
        ("FRAUD_CONTRACT_004", "CLM_FRAUD_004", "2026-03-01", "2026-02-25",
         "Chicago Service Center", "41.8781,-87.6298"),
        ("FRAUD_CONTRACT_005", "CLM_FRAUD_005", "2026-03-05", "2026-03-01",
         "Chicago Service Center", "41.8781,-87.6298"),
        ("FRAUD_CONTRACT_006", "CLM_FRAUD_006", "2026-03-10", "2026-01-05",
         "Chicago Service Center", "41.8781,-87.6298"),
        # Clean claims
        ("CLEAN_CONTRACT_001", "CLM_CLEAN_001", "2026-03-20", "2026-03-19",
         "Chicago Service Center", "41.8781,-87.6298"),
        ("CLEAN_CONTRACT_002", "CLM_CLEAN_002", "2026-03-22", "2026-03-21",
         "Chicago Service Center", "41.8781,-87.6298"),
        ("CLEAN_CONTRACT_003", "CLM_CLEAN_003", "2026-03-25", "2026-03-24",
         "Chicago Service Center", "41.8781,-87.6298"),
    ]

    for contract_id, claim_id, claim_date, loss_date, location, coords in golden_claims:
        session.execute(
            text("""
                INSERT INTO claims (
                    contract_id, claim_id, claim_date, reported_loss_date,
                    service_drive_location, service_drive_coords
                ) VALUES (:cid, :clid, :cd, :ld, :loc, :coords)
                ON CONFLICT (contract_id, claim_id) DO NOTHING
            """),
            {
                "cid": contract_id,
                "clid": claim_id,
                "cd": claim_date,
                "ld": loss_date,
                "loc": location,
                "coords": coords,
            },
        )

    # Set up prior claim for tire brand mismatch — Michelin tires on prior claim
    session.execute(
        text("""
            UPDATE claims
            SET gemini_analysis = :ga::jsonb
            WHERE contract_id = 'FRAUD_CONTRACT_002' AND claim_id = 'CLM_FRAUD_002_PRIOR'
        """),
        {
            "ga": json.dumps({
                "tire_brands_detected": {"current": "Michelin", "previous": []},
                "risk_score": 10,
                "red_flags": [],
            }),
        },
    )

    print(f"  Seeded {len(golden_claims)} golden claim records.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    skip_upload = "--skip-upload" in sys.argv
    bucket_override = None
    for i, arg in enumerate(sys.argv):
        if arg == "--bucket" and i + 1 < len(sys.argv):
            bucket_override = sys.argv[i + 1]

    bucket = bucket_override or os.environ.get("GCS_PHOTO_BUCKET", "claims-photos")

    print("=" * 60)
    print("Golden Dataset Seed Script")
    print("=" * 60)

    # 1. Generate test images
    print("\n1. Generating test images...")
    images = generate_test_images()

    # 2. Upload to GCS
    if skip_upload:
        print("\n2. Skipping GCS upload (--skip-upload)")
    else:
        print(f"\n2. Uploading to GCS bucket: {bucket}")
        try:
            upload_to_gcs(images, bucket)
        except Exception as exc:
            print(f"  WARNING: GCS upload failed: {exc}")
            print("  Continuing with DB seed only...")

    # 3. Seed database
    print("\n3. Seeding database records...")
    engine = _build_engine()
    with Session(engine) as session:
        seed_golden_dataset_records(session)
        seed_golden_claims(session)
        session.commit()

    print("\nGolden dataset seed complete.")
    print(f"  Fraud samples: {len(FRAUD_SAMPLES)}")
    print(f"  Clean samples: {len(CLEAN_SAMPLES)}")
    print(f"  Total: {len(ALL_SAMPLES)}")


if __name__ == "__main__":
    main()
