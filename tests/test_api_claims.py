"""API integration tests -- /api/claims endpoints."""

import json
import pytest
from tests.conftest import seed_test_claim, seed_test_photo, auth_header
from app.routers.claims import _derive_status


class TestListClaims:
    """Tests for GET /api/claims."""

    def test_list_claims_empty(self, test_client):
        resp = test_client.get("/api/claims", headers=auth_header())
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "per_page" in data
        assert "pages" in data

    def test_list_claims_with_data(self, test_client, db_session):
        seed_test_claim(db_session, contract_id="CTR_A", claim_id="CLM_A1", risk_score=80.0)
        seed_test_claim(db_session, contract_id="CTR_A", claim_id="CLM_A2", risk_score=20.0)

        resp = test_client.get("/api/claims", headers=auth_header())
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 2

    def test_list_claims_pagination(self, test_client, db_session):
        for i in range(5):
            seed_test_claim(
                db_session,
                contract_id=f"CTR_PAG_{i}",
                claim_id=f"CLM_PAG_{i}",
                risk_score=float(i * 20),
            )

        resp = test_client.get("/api/claims?page=1&per_page=2", headers=auth_header())
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) <= 2
        assert data["per_page"] == 2

    def test_list_claims_risk_filter(self, test_client, db_session):
        seed_test_claim(db_session, contract_id="CTR_RISK_H", claim_id="CLM_RH", risk_score=90.0)
        seed_test_claim(db_session, contract_id="CTR_RISK_L", claim_id="CLM_RL", risk_score=10.0)

        resp = test_client.get("/api/claims?risk_min=70&risk_max=100", headers=auth_header())
        assert resp.status_code == 200
        data = resp.json()
        for item in data["items"]:
            assert item["risk_score"] >= 70

    def test_list_claims_contract_filter(self, test_client, db_session):
        seed_test_claim(db_session, contract_id="CTR_FILTER", claim_id="CLM_F1")
        seed_test_claim(db_session, contract_id="CTR_OTHER", claim_id="CLM_O1")

        resp = test_client.get("/api/claims?contract_id=CTR_FILTER", headers=auth_header())
        assert resp.status_code == 200
        data = resp.json()
        for item in data["items"]:
            assert item["contract_id"] == "CTR_FILTER"

    def test_list_claims_sort_asc(self, test_client, db_session):
        seed_test_claim(db_session, contract_id="CTR_S1", claim_id="CLM_S1", risk_score=90.0)
        seed_test_claim(db_session, contract_id="CTR_S2", claim_id="CLM_S2", risk_score=10.0)

        resp = test_client.get("/api/claims?sort_by=risk_score&sort_dir=asc", headers=auth_header())
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

        resp = test_client.get(f"/api/claims/{claim_id}", headers=auth_header())
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

        resp = test_client.get(f"/api/claims/{claim_id}", headers=auth_header())
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["photos"]) >= 1
        assert data["photos"][0]["storage_key"] == "CTR_PHOTO/CLM_PHOTO/front.jpg"

    def test_get_claim_with_contract_history(self, test_client, db_session):
        seed_test_claim(db_session, contract_id="CTR_HIST", claim_id="CLM_H1", risk_score=30.0)
        claim_id_2 = seed_test_claim(db_session, contract_id="CTR_HIST", claim_id="CLM_H2", risk_score=80.0)

        resp = test_client.get(f"/api/claims/{claim_id_2}", headers=auth_header())
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["contract_history"]) >= 1

    def test_get_claim_not_found(self, test_client):
        resp = test_client.get("/api/claims/99999", headers=auth_header())
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()


class TestDeriveStatus:
    """Tests for _derive_status() helper."""

    def test_pending_when_not_processed(self):
        assert _derive_status(None, None) == "pending"
        assert _derive_status(None, 80.0) == "pending"

    def test_flagged_when_high_risk(self):
        assert _derive_status("2026-03-15", 75.0) == "flagged"
        assert _derive_status("2026-03-15", 51.0) == "flagged"

    def test_processed_when_low_risk(self):
        assert _derive_status("2026-03-15", 50.0) == "processed"
        assert _derive_status("2026-03-15", 10.0) == "processed"

    def test_processed_when_no_risk_score(self):
        assert _derive_status("2026-03-15", None) == "processed"

    def test_flagged_boundary(self):
        """Boundary: risk_score > 50 is flagged, exactly 50 is processed."""
        assert _derive_status("2026-03-15", 50) == "processed"
        assert _derive_status("2026-03-15", 50.01) == "flagged"


class TestListClaimsFieldMapping:
    """Tests for alias fields in GET /api/claims list response."""

    def test_submission_date_alias(self, test_client, db_session):
        seed_test_claim(db_session, contract_id="CTR_SD", claim_id="CLM_SD", risk_score=40.0)

        resp = test_client.get("/api/claims?contract_id=CTR_SD", headers=auth_header())
        assert resp.status_code == 200
        item = resp.json()["items"][0]
        assert "submission_date" in item
        assert item["submission_date"] == item["claim_date"]

    def test_status_field_present(self, test_client, db_session):
        seed_test_claim(db_session, contract_id="CTR_ST", claim_id="CLM_ST", risk_score=80.0)

        resp = test_client.get("/api/claims?contract_id=CTR_ST", headers=auth_header())
        assert resp.status_code == 200
        item = resp.json()["items"][0]
        assert "status" in item
        assert item["status"] in ("pending", "flagged", "processed")

    def test_photo_count_field_present(self, test_client, db_session):
        seed_test_claim(db_session, contract_id="CTR_PC", claim_id="CLM_PC", risk_score=30.0)

        resp = test_client.get("/api/claims?contract_id=CTR_PC", headers=auth_header())
        assert resp.status_code == 200
        item = resp.json()["items"][0]
        assert "photo_count" in item
        assert isinstance(item["photo_count"], int)


class TestGetClaimByIds:
    """Tests for GET /api/claims/{contract_id}/{claim_id}."""

    def test_get_claim_by_ids(self, test_client, db_session):
        seed_test_claim(
            db_session,
            contract_id="CTR_BYID",
            claim_id="CLM_BYID",
            risk_score=65.0,
            red_flags=["GPS mismatch"],
        )

        resp = test_client.get("/api/claims/CTR_BYID/CLM_BYID", headers=auth_header())
        assert resp.status_code == 200
        data = resp.json()
        assert data["contract_id"] == "CTR_BYID"
        assert data["claim_id"] == "CLM_BYID"
        assert data["risk_score"] == 65.0

    def test_get_claim_by_ids_not_found(self, test_client):
        resp = test_client.get("/api/claims/NO_CTR/NO_CLM", headers=auth_header())
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_get_claim_by_ids_has_detail_fields(self, test_client, db_session):
        seed_test_claim(
            db_session,
            contract_id="CTR_DF",
            claim_id="CLM_DF",
            risk_score=55.0,
            gemini_analysis={"recommendation": "review"},
        )

        resp = test_client.get("/api/claims/CTR_DF/CLM_DF", headers=auth_header())
        assert resp.status_code == 200
        data = resp.json()
        # Alias fields present in detail
        assert "submission_date" in data
        assert "status" in data
        assert "photo_count" in data
        # Detail-only fields
        assert "photos" in data
        assert "contract_history" in data
        assert "gemini_analysis" in data

    def test_get_claim_by_ids_with_photos(self, test_client, db_session):
        seed_test_claim(db_session, contract_id="CTR_BIP", claim_id="CLM_BIP")
        seed_test_photo(
            db_session,
            storage_key="CTR_BIP/CLM_BIP/photo_001.jpg",
            contract_id="CTR_BIP",
            claim_id="CLM_BIP",
        )

        resp = test_client.get("/api/claims/CTR_BIP/CLM_BIP", headers=auth_header())
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["photos"]) >= 1
        photo = data["photos"][0]
        assert "url" in photo
        assert photo["url"].startswith("/api/photos/serve/")

    def test_get_claim_by_ids_contract_history(self, test_client, db_session):
        seed_test_claim(db_session, contract_id="CTR_BIH", claim_id="CLM_BIH1", risk_score=20.0)
        seed_test_claim(db_session, contract_id="CTR_BIH", claim_id="CLM_BIH2", risk_score=90.0)

        resp = test_client.get("/api/claims/CTR_BIH/CLM_BIH2", headers=auth_header())
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["contract_history"]) >= 1
        hist = data["contract_history"][0]
        assert "submission_date" in hist
        assert "status" in hist
        assert "photo_count" in hist

    def test_get_claim_by_ids_requires_auth(self, test_client):
        resp = test_client.get("/api/claims/CTR_X/CLM_X")
        assert resp.status_code in (401, 422)
