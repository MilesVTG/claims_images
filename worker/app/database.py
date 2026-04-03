"""Database engine and session management for the worker."""

import os
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

DATABASE_URL = os.environ.get("DATABASE_URL")

if DATABASE_URL:
    engine = create_engine(
        DATABASE_URL,
        pool_size=5,
        pool_recycle=1800,
    )
else:
    from google.cloud.sql.connector import Connector

    INSTANCE_CONNECTION_NAME = os.environ.get(
        "CLOUD_SQL_CONNECTION_NAME",
        "claims-project:us-central1:claims-db",
    )
    DB_USER = os.environ.get("DB_USER", "fraud_user")
    DB_PASS = os.environ.get("DB_PASSWORD", "")
    DB_NAME = os.environ.get("DB_NAME", "claims")

    connector = Connector(refresh_strategy="lazy")

    def _getconn():
        return connector.connect(
            INSTANCE_CONNECTION_NAME,
            "pg8000",
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
    """Yields a session, auto-closes."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
