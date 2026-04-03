"""Seed script — create POC users and default Gemini system prompts (Sections 18B, 13B).

Usage (local dev with Cloud SQL connector):
    source .env && python scripts/seed.py

Usage (local dev with direct Postgres):
    DATABASE_URL=postgresql+pg8000://user:pass@localhost/claims python scripts/seed.py

Required env vars for Cloud SQL path:
    CLOUD_SQL_CONNECTION_NAME, DB_PASSWORD, MILES_PW, GREG_PW
Optional:
    DB_USER (default: fraud_user), DB_NAME (default: claims), DATABASE_URL
"""

import os
import sys

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from passlib.hash import bcrypt


def _build_engine():
    """Build SQLAlchemy engine — direct URL or Cloud SQL connector."""
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


def seed_users(session: Session) -> None:
    """Insert POC users (miles, greg). Passwords MUST be set in env."""
    miles_pw = os.environ.get("MILES_PW")
    greg_pw = os.environ.get("GREG_PW")

    if not miles_pw or not greg_pw:
        print("ERROR: MILES_PW and GREG_PW environment variables are required.")
        sys.exit(1)

    users = [
        ("miles", miles_pw, "Miles", "admin"),
        ("greg", greg_pw, "Greg", "admin"),
    ]

    for username, password, display_name, role in users:
        pw_hash = bcrypt.hash(password)
        session.execute(
            text("""
                INSERT INTO users (username, password_hash, display_name, role)
                VALUES (:u, :pw, :dn, :r)
                ON CONFLICT (username) DO UPDATE SET password_hash = EXCLUDED.password_hash
            """),
            {"u": username, "pw": pw_hash, "dn": display_name, "r": role},
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
                "Analyze these photos for fraud indicators.\n\n"
                "CONTRACT: {contract_id}\n"
                "CLAIM: {claim_id}\n"
                "CLAIM DATE: {claim_date}\n"
                "REPORTED LOSS DATE: {reported_loss_date}\n\n"
                "For each photo, examine:\n"
                "1. Tire brands visible (compare across photos and prior claims)\n"
                "2. Vehicle color consistency\n"
                "3. Damage patterns and severity\n"
                "4. Background/environment clues\n"
                "5. EXIF metadata anomalies (timestamps, GPS, camera model)\n"
                "6. Signs of image manipulation or stock photo usage\n\n"
                "PRIOR CLAIMS FOR THIS CONTRACT:\n{prior_claims}\n\n"
                "Respond with a JSON object containing:\n"
                "- risk_score (0-100)\n"
                "- red_flags (array of strings)\n"
                "- tire_brands_detected (string)\n"
                "- vehicle_colors_detected (string)\n"
                "- damage_assessment (string)\n"
                "- detailed_findings (string)"
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
                "ALERT: Claim {claim_id} (Contract {contract_id}) scored {risk_score}/100.\n"
                "Red flags: {red_flags}\n"
                "Review at: {dashboard_url}"
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


def seed():
    """Run all seed operations."""
    engine = _build_engine()
    with Session(engine) as session:
        print("Seeding database...")
        seed_users(session)
        seed_prompts(session)
        seed_test_claims(session)
        session.commit()
    print("Seed complete: users, prompts, and test claims inserted.")


if __name__ == "__main__":
    seed()
