"""API integration tests — /api/claims endpoints."""

import json
import pytest
from tests.conftest import seed_test_claim, seed_test_photo

# Claims list uses Postgres-specific SQL (JSON operators, NULLS LAST/FIRST)
# that won't work in SQLite. These tests are for Postgres integration testing.
requires_postgres = pytest.mark.skipif(
    True,  # Always skip in SQLite; set to False when running against Postgres
    reason="Requires Postgres (uses JSON operators and NULLS LAST/FIRST)",
)


class TestListClaims:
    """Tests for GET /api/claims.

    Note: list_claims uses Postgres JSONB operators (->>, jsonb_array_length)
    and NULLS LAST/FIRST syntax. These tests require a real Postgres database.
    """

    @requires_postgres
    def test_list_claims_empty(self, test_client):
        resp = test_client.get("/api/claims")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "per_page" in data
        assert "pages" in data

    @requires_postgres
    def test_list_claims_with_data(self, test_client, db_session):
        seed_test_claim(db_session, contract_id="CTR_A", claim_id="CLM_A1", risk_score=80.0)
        seed_test_claim(db_session, contract_id="CTR_A", claim_id="CLM_A2", risk_score=20.0)

        resp = test_client.get("/api/claims")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 2

    @requires_postgres
    def test_list_claims_pagination(self, test_client, db_session):
        for i in range(5):
            seed_test_claim(
                db_session,
                contract_id=f"CTR_PAG_{i}",
                claim_id=f"CLM_PAG_{i}",
                risk_score=float(i * 20),
            )

        resp = test_client.get("/api/claims?page=1&per_page=2")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) <= 2
        assert data["per_page"] == 2

    @requires_postgres
    def test_list_claims_risk_filter(self, test_client, db_session):
        seed_test_claim(db_session, contract_id="CTR_RISK_H", claim_id="CLM_RH", risk_score=90.0)
        seed_test_claim(db_session, contract_id="CTR_RISK_L", claim_id="CLM_RL", risk_score=10.0)

        resp = test_client.get("/api/claims?risk_min=70&risk_max=100")
        assert resp.status_code == 200
        data = resp.json()
        for item in data["items"]:
            assert item["risk_score"] >= 70

    @requires_postgres
    def test_list_claims_contract_filter(self, test_client, db_session):
        seed_test_claim(db_session, contract_id="CTR_FILTER", claim_id="CLM_F1")
        seed_test_claim(db_session, contract_id="CTR_OTHER", claim_id="CLM_O1")

        resp = test_client.get("/api/claims?contract_id=CTR_FILTER")
        assert resp.status_code == 200
        data = resp.json()
        for item in data["items"]:
            assert item["contract_id"] == "CTR_FILTER"

    @requires_postgres
    def test_list_claims_sort_asc(self, test_client, db_session):
        seed_test_claim(db_session, contract_id="CTR_S1", claim_id="CLM_S1", risk_score=90.0)
        seed_test_claim(db_session, contract_id="CTR_S2", claim_id="CLM_S2", risk_score=10.0)

        resp = test_client.get("/api/claims?sort_by=risk_score&sort_dir=asc")
        assert resp.status_code == 200
        data = resp.json()
        scores = [i["risk_score"] for i in data["items"] if i["risk_score"] is not None]
        assert scores == sorted(scores)

    def test_list_claims_invalid_sort(self, test_client):
        resp = test_client.get("/api/claims?sort_by=invalid_column")
        assert resp.status_code == 422

    def test_list_claims_invalid_page(self, test_client):
        resp = test_client.get("/api/claims?page=0")
        assert resp.status_code == 422

    def test_list_claims_per_page_limit(self, test_client):
        resp = test_client.get("/api/claims?per_page=500")
        assert resp.status_code == 422


class TestGetClaimDetail:
    """Tests for GET /api/claims/{claim_db_id}."""

    def test_get_claim_detail(self, test_client, db_session):
        claim_id = seed_test_claim(
            db_session,
            contract_id="CTR_DETAIL",
            claim_id="CLM_DETAIL",
            risk_score=85.0,
            red_flags=["Tire brand changed", "GPS mismatch"],
        )

        resp = test_client.get(f"/api/claims/{claim_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == claim_id
        assert data["contract_id"] == "CTR_DETAIL"
        assert data["risk_score"] == 85.0
        assert "photos" in data
        assert "contract_history" in data

    def test_get_claim_with_photos(self, test_client, db_session):
        claim_id = seed_test_claim(
            db_session, contract_id="CTR_PHOTO", claim_id="CLM_PHOTO",
        )
        seed_test_photo(
            db_session,
            storage_key="CTR_PHOTO/CLM_PHOTO/front.jpg",
            contract_id="CTR_PHOTO",
            claim_id="CLM_PHOTO",
        )

        resp = test_client.get(f"/api/claims/{claim_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["photos"]) >= 1
        assert data["photos"][0]["storage_key"] == "CTR_PHOTO/CLM_PHOTO/front.jpg"

    def test_get_claim_with_contract_history(self, test_client, db_session):
        seed_test_claim(db_session, contract_id="CTR_HIST", claim_id="CLM_H1", risk_score=30.0)
        claim_id_2 = seed_test_claim(db_session, contract_id="CTR_HIST", claim_id="CLM_H2", risk_score=80.0)

        resp = test_client.get(f"/api/claims/{claim_id_2}")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["contract_history"]) >= 1

    def test_get_claim_not_found(self, test_client):
        resp = test_client.get("/api/claims/99999")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()
