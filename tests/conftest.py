"""Shared pytest fixtures for Claims Images test suite.

Provides:
- In-memory SQLite database with schema matching Cloud SQL
- FastAPI TestClient with dependency overrides
- Auth helper (JWT tokens)
- Common test data factories
"""

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Generator

# CRITICAL: Set env vars BEFORE importing any app modules.
# database.py decides at import time whether to use Cloud SQL or direct URL.
os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("SESSION_SECRET", "test-secret-key")

import pytest
from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy import create_engine, text, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


# ---------------------------------------------------------------------------
# In-memory SQLite engine
# ---------------------------------------------------------------------------

# SQLite doesn't support ARRAY or JSONB natively — we use TEXT columns
# and override the schema to be SQLite-compatible.

SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    display_name TEXT,
    role TEXT DEFAULT 'reviewer',
    is_active INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS claims (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contract_id TEXT NOT NULL,
    claim_id TEXT NOT NULL,
    claim_date TEXT,
    reported_loss_date TEXT,
    service_drive_location TEXT,
    service_drive_coords TEXT,
    photo_uris TEXT,
    extracted_metadata TEXT,
    reverse_image_results TEXT,
    gemini_analysis TEXT,
    risk_score REAL,
    red_flags TEXT,
    processed_at TEXT DEFAULT (datetime('now')),
    UNIQUE(contract_id, claim_id)
);

CREATE TABLE IF NOT EXISTS processed_photos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    storage_key TEXT UNIQUE NOT NULL,
    contract_id TEXT,
    claim_id TEXT,
    processed_at TEXT DEFAULT (datetime('now')),
    status TEXT DEFAULT 'completed'
);

CREATE TABLE IF NOT EXISTS system_prompts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    content TEXT NOT NULL,
    model TEXT DEFAULT 'gemini-2.5-flash',
    is_active INTEGER DEFAULT 1,
    version INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    updated_by TEXT
);

CREATE TABLE IF NOT EXISTS prompt_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prompt_id INTEGER,
    version INTEGER NOT NULL,
    content TEXT NOT NULL,
    changed_by TEXT,
    changed_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (prompt_id) REFERENCES system_prompts(id)
);

CREATE TABLE IF NOT EXISTS golden_dataset (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    storage_key TEXT NOT NULL,
    expected_risk_min REAL NOT NULL,
    expected_risk_max REAL NOT NULL,
    expected_flags TEXT,
    must_not_flags TEXT,
    expected_tire_brand TEXT,
    expected_color TEXT,
    notes TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
"""


@pytest.fixture(scope="session")
def db_engine():
    """Create an in-memory SQLite engine for the test session."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # Enable WAL mode, foreign keys, and register Postgres-compatible functions
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
        # Register NOW() for SQLite (Postgres compat)
        dbapi_conn.create_function("NOW", 0, lambda: datetime.utcnow().isoformat())

    # Create schema
    with engine.connect() as conn:
        for stmt in SQLITE_SCHEMA.split(";"):
            stmt = stmt.strip()
            if stmt:
                conn.execute(text(stmt))
        conn.commit()

    return engine


@pytest.fixture(scope="session")
def SessionFactory(db_engine):
    """Session factory bound to the test engine."""
    return sessionmaker(bind=db_engine)


@pytest.fixture
def db_session(SessionFactory) -> Generator[Session, None, None]:
    """Per-test database session with auto-rollback."""
    session = SessionFactory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


# ---------------------------------------------------------------------------
# SQLite compatibility helpers for Postgres-specific SQL
# ---------------------------------------------------------------------------

def _sqlite_jsonb_array_length(json_str, *args):
    """SQLite replacement for jsonb_array_length."""
    if not json_str:
        return 0
    try:
        data = json.loads(json_str)
        if isinstance(data, list):
            return len(data)
        return 0
    except (json.JSONDecodeError, TypeError):
        return 0


def _sqlite_coalesce_json(val, default):
    """COALESCE helper that parses JSON paths."""
    return val if val is not None else default


# ---------------------------------------------------------------------------
# FastAPI TestClient
# ---------------------------------------------------------------------------

@pytest.fixture
def test_client(db_engine, db_session) -> Generator[TestClient, None, None]:
    """FastAPI TestClient with database dependency override.

    Patches the API's get_db to use the test SQLite session.
    """
    from app.database import get_db
    from app.main import app

    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

TEST_SECRET = "test-secret-key"
TEST_ALGORITHM = "HS256"


def make_auth_token(
    username: str = "testuser",
    role: str = "admin",
    secret: str = TEST_SECRET,
    expire_minutes: int = 60,
) -> str:
    """Generate a valid JWT token for testing."""
    payload = {
        "sub": username,
        "role": role,
        "exp": datetime.utcnow() + timedelta(minutes=expire_minutes),
    }
    return jwt.encode(payload, secret, algorithm=TEST_ALGORITHM)


def make_expired_token(
    username: str = "testuser",
    role: str = "admin",
    secret: str = TEST_SECRET,
) -> str:
    """Generate an expired JWT token for testing."""
    payload = {
        "sub": username,
        "role": role,
        "exp": datetime.utcnow() - timedelta(minutes=10),
    }
    return jwt.encode(payload, secret, algorithm=TEST_ALGORITHM)


def auth_header(token: str | None = None) -> dict:
    """Return Authorization header dict. Generates a default token if none given."""
    if token is None:
        token = make_auth_token()
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin_token() -> str:
    """Valid admin JWT token."""
    return make_auth_token(username="miles", role="admin")


@pytest.fixture
def reviewer_token() -> str:
    """Valid reviewer JWT token."""
    return make_auth_token(username="reviewer1", role="reviewer")


# ---------------------------------------------------------------------------
# Test data factories
# ---------------------------------------------------------------------------

def seed_test_user(session: Session, username: str = "miles", password_hash: str = None, role: str = "admin") -> int:
    """Insert a test user and return their ID."""
    if password_hash is None:
        import bcrypt as _bcrypt
        pw_hash = _bcrypt.hashpw(b"testpassword123", _bcrypt.gensalt()).decode()
    else:
        pw_hash = password_hash
    session.execute(
        text("""
            INSERT OR IGNORE INTO users (username, password_hash, display_name, role)
            VALUES (:u, :pw, :dn, :r)
        """),
        {"u": username, "pw": pw_hash, "dn": username.title(), "r": role},
    )
    session.commit()
    row = session.execute(text("SELECT id FROM users WHERE username = :u"), {"u": username}).fetchone()
    return row[0]


def seed_test_claim(
    session: Session,
    contract_id: str = "TEST_CTR_001",
    claim_id: str = "CLM_TEST_001",
    risk_score: float | None = 75.0,
    red_flags: list[str] | None = None,
    gemini_analysis: dict | None = None,
    reverse_image_results: dict | None = None,
) -> int:
    """Insert a test claim and return its ID."""
    flags_json = json.dumps(red_flags or [])
    gemini_json = json.dumps(gemini_analysis) if gemini_analysis else None
    vision_json = json.dumps(reverse_image_results) if reverse_image_results else None

    session.execute(
        text("""
            INSERT OR REPLACE INTO claims (
                contract_id, claim_id, claim_date, risk_score,
                red_flags, gemini_analysis, reverse_image_results
            ) VALUES (
                :cid, :clid, '2026-03-15', :score,
                :flags, :gemini, :vision
            )
        """),
        {
            "cid": contract_id,
            "clid": claim_id,
            "score": risk_score,
            "flags": flags_json,
            "gemini": gemini_json,
            "vision": vision_json,
        },
    )
    session.commit()
    row = session.execute(
        text("SELECT id FROM claims WHERE contract_id = :cid AND claim_id = :clid"),
        {"cid": contract_id, "clid": claim_id},
    ).fetchone()
    return row[0]


def seed_test_prompt(
    session: Session,
    slug: str = "test_prompt",
    name: str = "Test Prompt",
    category: str = "analysis",
    content: str = "Test prompt content",
) -> int:
    """Insert a test prompt and return its ID."""
    session.execute(
        text("""
            INSERT OR IGNORE INTO system_prompts (slug, name, category, content)
            VALUES (:s, :n, :c, :co)
        """),
        {"s": slug, "n": name, "c": category, "co": content},
    )
    session.commit()
    row = session.execute(text("SELECT id FROM system_prompts WHERE slug = :s"), {"s": slug}).fetchone()
    return row[0]


def seed_test_photo(
    session: Session,
    storage_key: str = "TEST_CTR_001/CLM_TEST_001/photo.jpg",
    contract_id: str = "TEST_CTR_001",
    claim_id: str = "CLM_TEST_001",
    status: str = "completed",
) -> int:
    """Insert a test processed photo and return its ID."""
    session.execute(
        text("""
            INSERT OR IGNORE INTO processed_photos (storage_key, contract_id, claim_id, status)
            VALUES (:key, :cid, :clid, :status)
        """),
        {"key": storage_key, "cid": contract_id, "clid": claim_id, "status": status},
    )
    session.commit()
    row = session.execute(text("SELECT id FROM processed_photos WHERE storage_key = :key"), {"key": storage_key}).fetchone()
    return row[0]
