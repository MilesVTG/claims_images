"""API integration tests — /api/auth endpoints."""

import pytest
from tests.conftest import (
    auth_header,
    make_auth_token,
    make_expired_token,
    seed_test_user,
)


class TestLoginEndpoint:
    """Tests for POST /api/auth/login."""

    def test_login_success(self, test_client, db_session):
        seed_test_user(db_session, username="miles", role="admin")
        resp = test_client.post(
            "/api/auth/login",
            json={"username": "miles", "password": "testpassword123"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data
        assert data["user"]["username"] == "miles"
        assert data["user"]["role"] == "admin"
        assert "expires_in" in data

    def test_login_wrong_password(self, test_client, db_session):
        seed_test_user(db_session, username="miles")
        resp = test_client.post(
            "/api/auth/login",
            json={"username": "miles", "password": "wrongpassword"},
        )
        assert resp.status_code == 401
        assert "Invalid" in resp.json()["detail"]

    def test_login_nonexistent_user(self, test_client):
        resp = test_client.post(
            "/api/auth/login",
            json={"username": "nobody", "password": "whatever"},
        )
        assert resp.status_code == 401

    def test_login_missing_fields(self, test_client):
        resp = test_client.post("/api/auth/login", json={"username": "miles"})
        assert resp.status_code == 422  # Pydantic validation error

    def test_login_empty_body(self, test_client):
        resp = test_client.post("/api/auth/login", json={})
        assert resp.status_code == 422


class TestLogoutEndpoint:
    """Tests for POST /api/auth/logout."""

    def test_logout_with_valid_token(self, test_client, admin_token):
        resp = test_client.post("/api/auth/logout", headers=auth_header(admin_token))
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_logout_without_token(self, test_client):
        resp = test_client.post("/api/auth/logout")
        assert resp.status_code in (401, 422)

    def test_logout_with_expired_token(self, test_client):
        token = make_expired_token()
        resp = test_client.post("/api/auth/logout", headers=auth_header(token))
        assert resp.status_code == 401


class TestMeEndpoint:
    """Tests for GET /api/auth/me."""

    def test_me_with_valid_token(self, test_client, db_session, admin_token):
        seed_test_user(db_session, username="miles", role="admin")
        resp = test_client.get("/api/auth/me", headers=auth_header(admin_token))
        assert resp.status_code == 200
        data = resp.json()
        assert data["username"] == "miles"
        assert data["role"] == "admin"

    def test_me_without_token(self, test_client):
        resp = test_client.get("/api/auth/me")
        assert resp.status_code in (401, 422)

    def test_me_with_invalid_token(self, test_client):
        resp = test_client.get(
            "/api/auth/me",
            headers={"Authorization": "Bearer invalid.token.here"},
        )
        assert resp.status_code == 401

    def test_me_with_bad_header_format(self, test_client):
        resp = test_client.get(
            "/api/auth/me",
            headers={"Authorization": "NotBearer sometoken"},
        )
        assert resp.status_code == 401
