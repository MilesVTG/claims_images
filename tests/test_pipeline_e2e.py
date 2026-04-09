"""Pipeline end-to-end test (CI-033).

Tests the worker's Pub/Sub push handler routing, message parsing,
idempotency, non-image filtering, and health endpoint.

Uses monkeypatch on the worker module object (loaded separately from the
API app module to avoid sys.modules conflicts).
"""

import importlib.util
import json
import os
import sys
from contextlib import contextmanager
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


# ---------------------------------------------------------------------------
# Load worker modules without conflicting with API app module cache
# ---------------------------------------------------------------------------

_worker_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "worker"))


def _load_module_from_path(module_name, file_path):
    """Load a Python module from an absolute file path."""
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


# Load worker modules under unique names to avoid conflicts
_worker_config = _load_module_from_path(
    "worker_config", os.path.join(_worker_dir, "app", "config.py")
)
_worker_exif = _load_module_from_path(
    "worker_exif", os.path.join(_worker_dir, "app", "services", "exif_service.py")
)
_worker_risk = _load_module_from_path(
    "worker_risk", os.path.join(_worker_dir, "app", "services", "risk_service.py")
)


# ---------------------------------------------------------------------------
# Pipeline mock helper
# ---------------------------------------------------------------------------

@contextmanager
def mock_pipeline(wmain, exif_data=None, vision_data=None, gemini_result=None):
    """Temporarily replace all external-service functions on the worker module.

    Mocks: download_photo, extract_exif, reverse_image_lookup,
    download_photos_for_claim, analyze_claim_with_gemini, send_high_risk_alert.
    compute_risk_score is left real — it's pure logic.
    """
    _exif = exif_data if exif_data is not None else {}
    _vision = vision_data if vision_data is not None else {}
    _gemini = gemini_result if gemini_result is not None else {
        "risk_score": 10, "red_flags": [],
    }

    originals = {}
    names = [
        "download_photo", "extract_exif", "reverse_image_lookup",
        "download_photos_for_claim", "analyze_claim_with_gemini",
        "send_high_risk_alert",
    ]
    for name in names:
        originals[name] = getattr(wmain, name)

    wmain.download_photo = lambda bucket_name, object_key: b"fake-image-bytes"
    wmain.extract_exif = lambda image_bytes: _exif
    wmain.reverse_image_lookup = lambda gs_uri: _vision
    wmain.download_photos_for_claim = lambda bucket_name, cid, clid: [b"fake-image"]
    wmain.analyze_claim_with_gemini = (
        lambda db, contract_id, claim_id, claim_data, exif_data, vision_data, image_bytes_list: _gemini
    )
    wmain.send_high_risk_alert = (
        lambda db, contract_id, claim_id, risk_score, red_flags: None
    )

    try:
        yield
    finally:
        for name, orig in originals.items():
            setattr(wmain, name, orig)


# ---------------------------------------------------------------------------
# SQLite schema (mirrors Postgres)
# ---------------------------------------------------------------------------

SQLITE_SCHEMA = """
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
CREATE TABLE IF NOT EXISTS error_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT DEFAULT (datetime('now')),
    service TEXT NOT NULL,
    endpoint TEXT,
    method TEXT,
    status_code INTEGER,
    error_type TEXT,
    message TEXT,
    traceback TEXT,
    request_id TEXT,
    pipeline_stage TEXT
);
"""


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def e2e_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _register_functions(dbapi_conn, connection_record):
        dbapi_conn.create_function("NOW", 0, lambda: datetime.utcnow().isoformat())

    with engine.connect() as conn:
        for stmt in SQLITE_SCHEMA.split(";"):
            stmt = stmt.strip()
            if stmt:
                conn.execute(text(stmt))
        conn.commit()
    return engine


@pytest.fixture
def e2e_session(e2e_engine):
    factory = sessionmaker(bind=e2e_engine)
    session = factory()
    yield session
    session.rollback()
    session.close()


@pytest.fixture
def worker_client(e2e_engine, e2e_session):
    """TestClient for the worker app.

    Loads the worker FastAPI app in isolation by temporarily swapping
    sys.modules so 'app' resolves to the worker package.
    """
    # Save current app modules
    saved = {}
    for k in list(sys.modules):
        if k == "app" or k.startswith("app."):
            saved[k] = sys.modules.pop(k)

    # Load worker
    sys.path.insert(0, _worker_dir)
    import app.main as wmain
    import app.database as wdb
    worker_app = wmain.app
    worker_get_db = wdb.get_db

    def _override_get_db():
        try:
            yield e2e_session
        finally:
            pass

    worker_app.dependency_overrides[worker_get_db] = _override_get_db
    client = TestClient(worker_app)

    yield client, wmain

    # Cleanup
    worker_app.dependency_overrides.clear()
    sys.path.remove(_worker_dir)
    # Remove worker modules and restore API modules
    for k in list(sys.modules):
        if k == "app" or k.startswith("app."):
            del sys.modules[k]
    sys.modules.update(saved)


# ---------------------------------------------------------------------------
# End-to-end tests
# ---------------------------------------------------------------------------

class TestPipelineEndToEnd:
    """Pub/Sub push → Worker routing → DB verification."""

    def test_clean_claim_pipeline(self, worker_client, e2e_session):
        """Clean claim flows through, gets low risk score, stored in DB."""
        client, wmain = worker_client

        with mock_pipeline(
            wmain,
            exif_data={"DateTimeOriginal": "2026:03:15 10:00:00"},
            vision_data={"full_matching_images": [], "partial_matching_images": []},
            gemini_result={"risk_score": 25, "red_flags": [], "geo_timestamp_check": {}},
        ):
            resp = client.post("/process", json={
                "message": {"attributes": {
                    "bucketId": "claims-photos",
                    "objectId": "E2E_CTR/CLM_E2E/front.jpg",
                }}
            })
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "processed"
            assert data["contract_id"] == "E2E_CTR"
            assert data["claim_id"] == "CLM_E2E"
            assert isinstance(data["risk_score"], (int, float))

            # Verify in DB
            photo = e2e_session.execute(
                text("SELECT id FROM processed_photos WHERE storage_key = :k"),
                {"k": "E2E_CTR/CLM_E2E/front.jpg"},
            ).fetchone()
            assert photo is not None

            claim = e2e_session.execute(
                text("SELECT risk_score FROM claims WHERE contract_id = :c AND claim_id = :cl"),
                {"c": "E2E_CTR", "cl": "CLM_E2E"},
            ).fetchone()
            assert claim is not None

    def test_idempotent_processing(self, worker_client, e2e_session):
        """Processing same photo twice: first processed, second skipped."""
        client, wmain = worker_client

        with mock_pipeline(wmain):
            msg = {"message": {"attributes": {"bucketId": "b", "objectId": "IDEMP/CLM_ID/photo.jpg"}}}
            resp1 = client.post("/process", json=msg)
            assert resp1.json()["status"] == "processed"

            resp2 = client.post("/process", json=msg)
            assert resp2.json()["status"] == "skipped"

    def test_ignores_non_image(self, worker_client):
        client, _ = worker_client
        resp = client.post("/process", json={
            "message": {"attributes": {"bucketId": "b", "objectId": "CTR/CLM/doc.pdf"}}
        })
        assert resp.json()["status"] == "ignored"

    def test_ignores_empty_object_id(self, worker_client):
        client, _ = worker_client
        resp = client.post("/process", json={
            "message": {"attributes": {"bucketId": "b", "objectId": ""}}
        })
        assert resp.json()["status"] == "ignored"

    def test_worker_health(self, worker_client):
        client, _ = worker_client
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestPipelineFraudDetection:
    """Fraud scenario: high risk score from pipeline."""

    def test_fraud_claim_high_risk(self, worker_client, e2e_session):
        client, wmain = worker_client

        with mock_pipeline(
            wmain,
            exif_data={},
            vision_data={"full_matching_images": ["url"], "partial_matching_images": []},
            gemini_result={
                "risk_score": 90,
                "red_flags": ["Stock photo", "Manipulated"],
                "geo_timestamp_check": {},
                "reverse_image_flag": True,
            },
        ):
            resp = client.post("/process", json={
                "message": {"attributes": {"bucketId": "b", "objectId": "FRAUD_E2E/CLM_FRD/sus.jpg"}}
            })
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "processed"
            assert data["risk_score"] >= 50
            assert data["red_flags_count"] > 0


class TestPipelineMessageParsing:
    """Edge cases in Pub/Sub message parsing."""

    def test_missing_message_attributes(self, worker_client):
        client, _ = worker_client
        resp = client.post("/process", json={"message": {}})
        assert resp.json()["status"] == "ignored"

    def test_empty_envelope(self, worker_client):
        client, _ = worker_client
        resp = client.post("/process", json={})
        assert resp.json()["status"] == "ignored"

    def test_supports_multiple_image_extensions(self, worker_client):
        client, wmain = worker_client

        with mock_pipeline(wmain):
            for ext in [".jpg", ".jpeg", ".png", ".webp"]:
                resp = client.post("/process", json={
                    "message": {"attributes": {"bucketId": "b", "objectId": f"CTR_EXT/CLM_{ext}/photo{ext}"}}
                })
                assert resp.json()["status"] == "processed", f"Extension {ext} should be processed"
