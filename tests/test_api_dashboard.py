"""API integration tests -- /api/dashboard endpoints."""

import pytest
from tests.conftest import seed_test_claim, seed_test_photo, auth_header


class TestDashboardSummary:
    """Tests for GET /api/dashboard/summary."""

    def test_summary_empty_db(self, test_client):
        resp = test_client.get("/api/dashboard/summary", headers=auth_header())
        assert resp.status_code == 200
        data = resp.json()
        assert "claims" in data
        assert "photos" in data
        assert "today" in data
        assert "recent_high_risk" in data

    def test_summary_structure(self, test_client):
        resp = test_client.get("/api/dashboard/summary", headers=auth_header())
        data = resp.json()

        claims = data["claims"]
        assert "total" in claims
        assert "high_risk" in claims
        assert "medium_risk" in claims
        assert "low_risk" in claims
        assert "avg_risk_score" in claims
        assert "with_web_matches" in claims
        assert "analyzed" in claims
        assert "pending_analysis" in claims

        photos = data["photos"]
        assert "total" in photos
        assert "completed" in photos
        assert "pending" in photos
        assert "failed" in photos

        today = data["today"]
        assert "claims_processed" in today
        assert "high_risk" in today
        assert "avg_risk_score" in today

    def test_summary_counts_risk_bands(self, test_client, db_session):
        seed_test_claim(db_session, contract_id="CTR_HR", claim_id="CLM_HR", risk_score=85.0)
        seed_test_claim(db_session, contract_id="CTR_MR", claim_id="CLM_MR", risk_score=55.0)
        seed_test_claim(db_session, contract_id="CTR_LR", claim_id="CLM_LR", risk_score=15.0)

        resp = test_client.get("/api/dashboard/summary", headers=auth_header())
        data = resp.json()
        assert data["claims"]["total"] >= 3

    def test_summary_photo_stats(self, test_client, db_session):
        seed_test_photo(db_session, storage_key="p1.jpg", status="completed")
        seed_test_photo(db_session, storage_key="p2.jpg", status="pending")
        seed_test_photo(db_session, storage_key="p3.jpg", status="failed")

        resp = test_client.get("/api/dashboard/summary", headers=auth_header())
        data = resp.json()
        assert data["photos"]["total"] >= 3

    def test_summary_recent_high_risk(self, test_client, db_session):
        seed_test_claim(db_session, contract_id="CTR_RHR", claim_id="CLM_RHR", risk_score=92.0)

        resp = test_client.get("/api/dashboard/summary", headers=auth_header())
        data = resp.json()
        assert isinstance(data["recent_high_risk"], list)
