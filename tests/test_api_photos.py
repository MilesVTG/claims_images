"""API integration tests -- /api/photos endpoints."""

import io
from unittest.mock import MagicMock, patch

import pytest
from tests.conftest import seed_test_claim, seed_test_photo, auth_header


# ---------------------------------------------------------------------------
# GCS mock helpers
# ---------------------------------------------------------------------------

def _make_mock_bucket(blobs=None):
    """Return a mock GCS bucket with optional blob listing."""
    bucket = MagicMock()
    bucket.list_blobs.return_value = blobs or []
    return bucket


def _make_mock_blob(name="test.jpg", exists=True, data=b"fake-image", content_type="image/jpeg"):
    """Return a mock GCS blob."""
    blob = MagicMock()
    blob.name = name
    blob.exists.return_value = exists
    blob.download_as_bytes.return_value = data
    blob.content_type = content_type
    return blob


def _patch_gcs(bucket):
    """Patch _get_bucket in the photos router to return the given mock bucket."""
    return patch("app.routers.photos._get_bucket", return_value=bucket)


# ---------------------------------------------------------------------------
# Upload tests
# ---------------------------------------------------------------------------

class TestUploadPhoto:
    """Tests for POST /api/photos/upload."""

    def test_upload_success(self, test_client, db_session):
        bucket = _make_mock_bucket(blobs=[])
        mock_blob = _make_mock_blob()
        bucket.blob.return_value = mock_blob

        with _patch_gcs(bucket):
            resp = test_client.post(
                "/api/photos/upload",
                headers=auth_header(),
                data={"contract_id": "CTR_UP", "claim_id": "CLM_UP"},
                files={"file": ("front.jpg", io.BytesIO(b"fake-jpg-data"), "image/jpeg")},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "uploaded"
        assert "storage_key" in data
        assert data["storage_key"].startswith("CTR_UP/CLM_UP/")

        # Verify blob was uploaded
        mock_blob.upload_from_string.assert_called_once()

    def test_upload_increments_photo_number(self, test_client, db_session):
        # Simulate 2 existing blobs
        existing = [MagicMock(name=f"CTR_UP2/CLM_UP2/photo_00{i}.jpg") for i in range(1, 3)]
        bucket = _make_mock_bucket(blobs=existing)
        mock_blob = _make_mock_blob()
        bucket.blob.return_value = mock_blob

        with _patch_gcs(bucket):
            resp = test_client.post(
                "/api/photos/upload",
                headers=auth_header(),
                data={"contract_id": "CTR_UP2", "claim_id": "CLM_UP2"},
                files={"file": ("tire.png", io.BytesIO(b"fake-png"), "image/png")},
            )

        assert resp.status_code == 200
        # Should be photo_003 since 2 already exist
        assert "photo_003" in resp.json()["storage_key"]

    def test_upload_invalid_extension(self, test_client):
        bucket = _make_mock_bucket()
        with _patch_gcs(bucket):
            resp = test_client.post(
                "/api/photos/upload",
                headers=auth_header(),
                data={"contract_id": "CTR_X", "claim_id": "CLM_X"},
                files={"file": ("doc.pdf", io.BytesIO(b"fake-pdf"), "application/pdf")},
            )

        assert resp.status_code == 400
        assert "not allowed" in resp.json()["detail"].lower()

    def test_upload_no_extension(self, test_client):
        bucket = _make_mock_bucket()
        with _patch_gcs(bucket):
            resp = test_client.post(
                "/api/photos/upload",
                headers=auth_header(),
                data={"contract_id": "CTR_X", "claim_id": "CLM_X"},
                files={"file": ("noext", io.BytesIO(b"data"), "application/octet-stream")},
            )

        assert resp.status_code == 400

    def test_upload_file_too_large(self, test_client):
        bucket = _make_mock_bucket()
        bucket.blob.return_value = _make_mock_blob()
        # 21 MB file
        large_data = b"x" * (21 * 1024 * 1024)

        with _patch_gcs(bucket):
            resp = test_client.post(
                "/api/photos/upload",
                headers=auth_header(),
                data={"contract_id": "CTR_X", "claim_id": "CLM_X"},
                files={"file": ("big.jpg", io.BytesIO(large_data), "image/jpeg")},
            )

        assert resp.status_code == 400
        assert "20 MB" in resp.json()["detail"]

    def test_upload_upserts_claim(self, test_client, db_session):
        """Upload should create or update claims row with photo_uris."""
        bucket = _make_mock_bucket(blobs=[])
        bucket.blob.return_value = _make_mock_blob()

        with _patch_gcs(bucket):
            resp = test_client.post(
                "/api/photos/upload",
                headers=auth_header(),
                data={"contract_id": "CTR_UPSERT", "claim_id": "CLM_UPSERT"},
                files={"file": ("test.jpg", io.BytesIO(b"data"), "image/jpeg")},
            )

        assert resp.status_code == 200

        # Verify claim row was created
        from sqlalchemy import text
        row = db_session.execute(
            text("SELECT photo_uris FROM claims WHERE contract_id = :cid AND claim_id = :clid"),
            {"cid": "CTR_UPSERT", "clid": "CLM_UPSERT"},
        ).fetchone()
        assert row is not None
        assert resp.json()["storage_key"] in row[0]

    def test_upload_requires_auth(self, test_client):
        resp = test_client.post(
            "/api/photos/upload",
            data={"contract_id": "X", "claim_id": "Y"},
            files={"file": ("test.jpg", io.BytesIO(b"data"), "image/jpeg")},
        )
        assert resp.status_code in (401, 422)

    def test_upload_accepted_extensions(self, test_client, db_session):
        """All allowed extensions should succeed."""
        for ext, ctype in [(".jpg", "image/jpeg"), (".jpeg", "image/jpeg"),
                           (".png", "image/png"), (".webp", "image/webp")]:
            bucket = _make_mock_bucket(blobs=[])
            bucket.blob.return_value = _make_mock_blob()

            with _patch_gcs(bucket):
                resp = test_client.post(
                    "/api/photos/upload",
                    headers=auth_header(),
                    data={"contract_id": f"CTR_EXT{ext}", "claim_id": "CLM_EXT"},
                    files={"file": (f"photo{ext}", io.BytesIO(b"data"), ctype)},
                )

            assert resp.status_code == 200, f"Failed for extension {ext}"


# ---------------------------------------------------------------------------
# Status tests
# ---------------------------------------------------------------------------

class TestPhotoStatus:
    """Tests for GET /api/photos/status/{storage_key}."""

    def test_status_found(self, test_client, db_session):
        seed_test_photo(
            db_session,
            storage_key="CTR_PS/CLM_PS/photo_001.jpg",
            contract_id="CTR_PS",
            claim_id="CLM_PS",
            status="completed",
        )

        resp = test_client.get(
            "/api/photos/status/CTR_PS/CLM_PS/photo_001.jpg",
            headers=auth_header(),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["storage_key"] == "CTR_PS/CLM_PS/photo_001.jpg"
        assert data["status"] == "completed"
        assert data["processed_at"] is not None

    def test_status_not_found_returns_pending(self, test_client):
        resp = test_client.get(
            "/api/photos/status/NONEXISTENT/KEY/photo.jpg",
            headers=auth_header(),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "pending"
        assert data["processed_at"] is None

    def test_status_requires_auth(self, test_client):
        resp = test_client.get("/api/photos/status/any/key.jpg")
        assert resp.status_code in (401, 422)


# ---------------------------------------------------------------------------
# Serve tests
# ---------------------------------------------------------------------------

class TestServePhoto:
    """Tests for GET /api/photos/serve/{storage_key}."""

    def test_serve_success(self, test_client):
        fake_data = b"\xff\xd8\xff\xe0fake-jpeg-bytes"
        bucket = _make_mock_bucket()
        mock_blob = _make_mock_blob(exists=True, data=fake_data, content_type="image/jpeg")
        bucket.blob.return_value = mock_blob

        with _patch_gcs(bucket):
            resp = test_client.get(
                "/api/photos/serve/CTR_SRV/CLM_SRV/photo_001.jpg",
                headers=auth_header(),
            )

        assert resp.status_code == 200
        assert resp.content == fake_data
        assert resp.headers["content-type"] == "image/jpeg"
        assert "max-age=3600" in resp.headers.get("cache-control", "")

    def test_serve_not_found(self, test_client):
        bucket = _make_mock_bucket()
        mock_blob = _make_mock_blob(exists=False)
        bucket.blob.return_value = mock_blob

        with _patch_gcs(bucket):
            resp = test_client.get(
                "/api/photos/serve/NO/SUCH/photo.jpg",
                headers=auth_header(),
            )

        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_serve_requires_auth(self, test_client):
        resp = test_client.get("/api/photos/serve/any/key.jpg")
        assert resp.status_code in (401, 422)


# ---------------------------------------------------------------------------
# Ask stub tests
# ---------------------------------------------------------------------------

class TestAskPhoto:
    """Tests for POST /api/photos/ask/{storage_key}."""

    def test_ask_returns_not_implemented(self, test_client):
        resp = test_client.post(
            "/api/photos/ask/CTR_ASK/CLM_ASK/photo.jpg",
            headers=auth_header(),
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "not_implemented"

    def test_ask_requires_auth(self, test_client):
        resp = test_client.post("/api/photos/ask/any/key.jpg")
        assert resp.status_code in (401, 422)


# ---------------------------------------------------------------------------
# List photos tests
# ---------------------------------------------------------------------------

class TestListPhotos:
    """Tests for GET /api/photos/{contract_id}/{claim_id}."""

    def test_list_photos_empty(self, test_client, db_session):
        bucket = _make_mock_bucket(blobs=[])

        with _patch_gcs(bucket):
            resp = test_client.get("/api/photos/CTR_LP/CLM_LP", headers=auth_header())

        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_photos_with_blobs(self, test_client, db_session):
        # Mock 2 blobs in GCS
        blob1 = MagicMock()
        blob1.name = "CTR_LPB/CLM_LPB/photo_001.jpg"
        blob2 = MagicMock()
        blob2.name = "CTR_LPB/CLM_LPB/photo_002.jpg"
        bucket = _make_mock_bucket(blobs=[blob1, blob2])

        # One has a processed_photos record
        seed_test_photo(
            db_session,
            storage_key="CTR_LPB/CLM_LPB/photo_001.jpg",
            contract_id="CTR_LPB",
            claim_id="CLM_LPB",
            status="completed",
        )

        with _patch_gcs(bucket):
            resp = test_client.get("/api/photos/CTR_LPB/CLM_LPB", headers=auth_header())

        assert resp.status_code == 200
        photos = resp.json()
        assert len(photos) == 2

        # First photo should be completed
        p1 = next(p for p in photos if "photo_001" in p["storage_key"])
        assert p1["status"] == "completed"
        assert p1["filename"] == "photo_001.jpg"
        assert p1["url"].startswith("/api/photos/serve/")

        # Second photo should be pending (no processed_photos record)
        p2 = next(p for p in photos if "photo_002" in p["storage_key"])
        assert p2["status"] == "pending"

    def test_list_photos_requires_auth(self, test_client):
        resp = test_client.get("/api/photos/CTR_X/CLM_X")
        assert resp.status_code in (401, 422)
