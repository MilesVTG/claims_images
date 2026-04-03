"""API integration tests — /api/health endpoint."""

import pytest


class TestHealthEndpoint:
    """Tests for GET /api/health."""

    def test_health_returns_ok(self, test_client):
        resp = test_client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ("ok", "degraded")
        assert "db" in data

    def test_health_reports_db_status(self, test_client):
        resp = test_client.get("/api/health")
        data = resp.json()
        # With SQLite test DB, should be connected
        assert data["db"] == "connected"
        assert data["status"] == "ok"
