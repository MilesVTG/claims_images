"""Seed script — create POC users and default Gemini system prompts (Sections 18B, 13B).

Usage:
    python3 scripts/seed.py

Loads .env automatically from the project root. No need to `source .env` first.

Seed users are read from .env as SEED_USER_N_EMAIL, SEED_USER_N_PASSWORD,
SEED_USER_N_NAME, SEED_USER_N_ROLE (N = 1, 2, 3, ...).
"""

import os
import sys
from pathlib import Path


def _load_env():
    """Load .env file from project root, exporting all vars to os.environ."""
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        # No .env is OK in Cloud Run — env vars are set by the platform
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            # Strip surrounding quotes
            if (value.startswith("'") and value.endswith("'")) or \
               (value.startswith('"') and value.endswith('"')):
                value = value[1:-1]
            os.environ.setdefault(key, value)


_load_env()

import bcrypt as _bcrypt
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session


def _build_engine():
    """Build SQLAlchemy engine — direct URL or Cloud SQL connector."""
    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        return create_engine(database_url)

    try:
        from google.cloud.sql.connector import Connector
    except ImportError:
        print("ERROR: google-cloud-sql-connector not installed.")
        print("  Install: pip install 'cloud-sql-python-connector[pg8000]'")
        print("  Or set DATABASE_URL for direct Postgres access.")
        sys.exit(1)

    # Build connection name: project:region:instance
    instance = os.environ.get("CLOUD_SQL_CONNECTION_NAME")
    if not instance:
        project = os.environ.get("GCP_PROJECT_ID")
        region = os.environ.get("GCP_REGION", "us-central1")
        sql_instance = os.environ.get("CLOUD_SQL_INSTANCE", "fraud-detection-db")
        if not project:
            print("ERROR: Need CLOUD_SQL_CONNECTION_NAME or GCP_PROJECT_ID in .env")
            sys.exit(1)
        instance = f"{project}:{region}:{sql_instance}"

    db_user = os.environ.get("CLOUD_SQL_USER", "fraud_user")
    db_name = os.environ.get("CLOUD_SQL_DB", "fraud_detection")
    db_pass = os.environ.get("DB_PASSWORD")
    if not db_pass:
        print("ERROR: DB_PASSWORD not set in .env")
        sys.exit(1)

    print(f"  Connecting to Cloud SQL: {instance} as {db_user}/{db_name}")

    from google.cloud.sql.connector import IPTypes
    connector = Connector(refresh_strategy="lazy")

    def _getconn():
        return connector.connect(instance, "pg8000", ip_type=IPTypes.PRIVATE, user=db_user, password=db_pass, db=db_name)

    return create_engine("postgresql+pg8000://", creator=_getconn)


def _load_seed_users() -> list[tuple[str, str, str, str]]:
    """Read SEED_USER_N_* env vars. Returns list of (email, password, name, role)."""
    users = []
    n = 1
    while True:
        email = os.environ.get(f"SEED_USER_{n}_EMAIL")
        if not email:
            break
        password = os.environ.get(f"SEED_USER_{n}_PASSWORD")
        if not password:
            print(f"ERROR: SEED_USER_{n}_PASSWORD is required for {email}")
            sys.exit(1)
        name = os.environ.get(f"SEED_USER_{n}_NAME", email.split("@")[0])
        role = os.environ.get(f"SEED_USER_{n}_ROLE", "reviewer")
        users.append((email, password, name, role))
        n += 1
    if not users:
        print("ERROR: No seed users found. Set SEED_USER_1_EMAIL / SEED_USER_1_PASSWORD in .env")
        sys.exit(1)
    return users


def seed_users(session: Session) -> None:
    """Insert seed users from .env (SEED_USER_N_* vars)."""
    users = _load_seed_users()
    for email, password, display_name, role in users:
        pw_hash = _bcrypt.hashpw(password.encode(), _bcrypt.gensalt()).decode()
        session.execute(
            text("""
                INSERT INTO users (username, password_hash, display_name, role)
                VALUES (:u, :pw, :dn, :r)
                ON CONFLICT (username) DO UPDATE
                    SET password_hash = EXCLUDED.password_hash,
                        display_name = EXCLUDED.display_name,
                        role = EXCLUDED.role
            """),
            {"u": email, "pw": pw_hash, "dn": display_name, "r": role},
        )
    print(f"  Seeded {len(users)} users.")


def seed_prompts(session: Session) -> None:
    """Insert default Gemini system prompts (Section 13B)."""
    prompts = [
        (
            "fraud_system_instruction",
            "System Instruction - Fraud Investigator",
            "system_instruction",
            (
                "You are a senior insurance fraud investigator with 20 years of experience. "
                "Be extremely strict and factual. Never speculate without evidence. "
                "Always cite specific visual details to support your findings."
            ),
        ),
        (
            "fraud_analysis_template",
            "Fraud Analysis - Main Template",
            "analysis",
            (
                "Analyze these photos for fraud indicators.\n"
                "\n"
                "CONTRACT: {contract_id}\n"
                "\n"
                "PREVIOUS CLAIMS (last 24 months):\n"
                "{history_text}\n"
                "\n"
                "CURRENT CLAIM:\n"
                "  Claim ID: {claim_id}\n"
                "  Reported Loss Date: {reported_loss_date}\n"
                "  Service Drive Location: {service_drive_location}\n"
                "  Service Drive Coordinates: {service_drive_coords}\n"
                "  Photo EXIF Timestamp: {exif_timestamp}\n"
                "  Photo GPS: {gps_lat}, {gps_lon}\n"
                "  Reverse Image Hits: {full_matches} exact matches, {similar} similar\n"
                "\n"
                "REQUIRED ANALYSIS:\n"
                "  1. Extract visible tire brand(s) from ALL photos (read logos/text).\n"
                "  2. Extract vehicle color from ALL photos.\n"
                "  3. Check for recycled/duplicate images.\n"
                "  4. Assess damage authenticity (fresh vs. staged).\n"
                "  5. Flag inconsistencies: tire brand change, color change, impossible damage timeline.\n"
                "  6. Compare EXIF GPS to service drive coords -- flag if >5 miles apart.\n"
                "  7. Compare EXIF timestamp to reported loss date -- flag if >48 hrs.\n"
                "  8. Note any reverse image search hits as strong fraud indicators.\n"
                "  9. Overall fraud risk score (0-100).\n"
                "\n"
                "RESPOND WITH ONLY VALID JSON:\n"
                "{{\n"
                '  "risk_score": <0-100>,\n'
                '  "red_flags": ["flag1", "flag2"],\n'
                '  "tire_brands_detected": {{"current": "...", "previous": ["..."]}},\n'
                '  "vehicle_colors_detected": {{"current": "...", "previous": ["..."]}},\n'
                '  "damage_assessment": "...",\n'
                '  "geo_timestamp_check": {{\n'
                '    "gps_vs_service_drive": "MATCH|MISMATCH (distance)",\n'
                '    "timestamp_vs_loss_date": "MATCH|MISMATCH (details)"\n'
                "  }},\n"
                '  "reverse_image_flag": true|false,\n'
                '  "explanation": "...",\n'
                '  "recommendation": "..."\n'
                "}}"
            ),
        ),
        (
            "photo_qa_system",
            "Q&A System Instruction",
            "system_instruction",
            (
                "You are an expert photo analyst for insurance claims. Answer questions "
                "about the provided photo accurately and concisely."
            ),
        ),
        (
            "photo_qa_template",
            "Photo Q&A Template",
            "qa",
            "Photo context:\n{existing_analysis}\n\nUser question: {question}",
        ),
        (
            "high_risk_email_template",
            "High Risk Alert Email",
            "notification",
            (
                "A claim has been flagged as HIGH RISK by the fraud detection system.\n"
                "\n"
                "Contract ID: {contract_id}\n"
                "Claim ID:    {claim_id}\n"
                "Risk Score:  {risk_score}\n"
                "\n"
                "Red Flags:\n"
                "{flags_text}\n"
                "\n"
                "Review in dashboard: {dashboard_url}\n"
            ),
        ),
        (
            "batch_analysis_template",
            "Batch Analysis Template",
            "analysis",
            (
                "Analyze these photos for fraud indicators (batch mode).\n\n"
                "Process each photo in the batch and return a consolidated JSON response "
                "with per-photo findings and an overall risk assessment."
            ),
        ),
        (
            "high_risk_email_subject",
            "High Risk Alert Email Subject",
            "notification",
            "HIGH RISK: Claim {claim_id} scored {risk_score}",
        ),
    ]

    for slug, name, category, content in prompts:
        session.execute(
            text("""
                INSERT INTO system_prompts (slug, name, category, content)
                VALUES (:s, :n, :c, :co)
                ON CONFLICT (slug) DO NOTHING
            """),
            {"s": slug, "n": name, "c": category, "co": content},
        )
    print(f"  Seeded {len(prompts)} default prompts.")


def seed_test_claims(session: Session) -> None:
    """Insert sample test claims for POC development."""
    session.execute(
        text("""
            INSERT INTO claims (contract_id, claim_id, claim_date, risk_score, red_flags, photo_uris)
            VALUES
              ('TEST_CONTRACT_001', 'CLM_001', '2026-01-15', 82.5,
               ARRAY['Tire brand changed: Michelin to Goodyear', 'Timestamp mismatch: 5 days before loss'],
               ARRAY['photos/TEST_CONTRACT_001/CLM_001/front.jpg']),
              ('TEST_CONTRACT_001', 'CLM_002', '2026-03-01', 15.0,
               ARRAY[]::TEXT[],
               ARRAY['photos/TEST_CONTRACT_001/CLM_002/front.jpg']),
              ('TEST_CONTRACT_002', 'CLM_003', '2026-02-20', 91.0,
               ARRAY['Exact web match found', 'Photo GPS 200 miles from service drive'],
               ARRAY['photos/TEST_CONTRACT_002/CLM_003/damage.jpg'])
            ON CONFLICT (contract_id, claim_id) DO NOTHING
        """)
    )
    print("  Seeded test claims.")


def run_schema(engine) -> None:
    """Create tables and views if they don't exist."""
    schema_path = Path(__file__).resolve().parent / "schema.sql"
    if not schema_path.exists():
        print("  WARNING: schema.sql not found, skipping schema creation")
        return
    print("  Running schema.sql ...")
    sql = schema_path.read_text()
    with engine.connect() as conn:
        for stmt in sql.split(";"):
            stmt = stmt.strip()
            if stmt:
                conn.execute(text(stmt))
        conn.commit()
    print("  Schema ready.")


def seed():
    """Run all seed operations."""
    engine = _build_engine()
    run_schema(engine)
    with Session(engine) as session:
        print("Seeding database...")
        seed_users(session)
        seed_prompts(session)
        seed_test_claims(session)
        session.commit()
    print("Seed complete: users, prompts, and test claims inserted.")


if __name__ == "__main__":
    seed()
