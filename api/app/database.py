"""Database engine and session management via Cloud SQL Python Connector (Section 9J).

Uses pg8000 as the database driver — the GCP-recommended approach for Cloud Run.
The connector handles IAM auth, socket management, and private IP connectivity.

For local development without Cloud SQL, set DATABASE_URL to a direct Postgres URL
(e.g. postgresql+pg8000://user:pass@localhost/claims) and the connector is bypassed.
"""

import os
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

# Direct URL takes precedence (local dev / testing)
DATABASE_URL = os.environ.get("DATABASE_URL")

if DATABASE_URL:
    engine = create_engine(
        DATABASE_URL,
        pool_size=5,
        pool_recycle=1800,
    )
else:
    # Cloud SQL connector path (production on Cloud Run)
    from google.cloud.sql.connector import Connector, IPTypes

    INSTANCE_CONNECTION_NAME = os.environ.get(
        "CLOUD_SQL_CONNECTION_NAME",
        "claims-project:us-central1:fraud-detection-db",
    )
    DB_USER = os.environ.get("DB_USER", "fraud_user")
    DB_PASS = os.environ.get("DB_PASSWORD", "")
    DB_NAME = os.environ.get("DB_NAME", "fraud_detection")

    connector = Connector(refresh_strategy="lazy")

    def _getconn():
        return connector.connect(
            INSTANCE_CONNECTION_NAME,
            "pg8000",
            ip_type=IPTypes.PRIVATE,
            user=DB_USER,
            password=DB_PASS,
            db=DB_NAME,
        )

    engine = create_engine(
        "postgresql+pg8000://",
        creator=_getconn,
        pool_size=5,
        pool_recycle=1800,
    )

SessionLocal = sessionmaker(bind=engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency — yields a session, auto-closes."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
