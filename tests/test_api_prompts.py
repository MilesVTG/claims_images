"""API integration tests — /api/prompts endpoints."""

import pytest
from tests.conftest import seed_test_prompt, auth_header


class TestListPrompts:
    """Tests for GET /api/prompts."""

    def test_list_prompts_empty(self, test_client):
        resp = test_client.get("/api/prompts", headers=auth_header())
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_list_prompts_with_data(self, test_client, db_session):
        seed_test_prompt(db_session, slug="test_list_1", category="analysis")
        seed_test_prompt(db_session, slug="test_list_2", category="system_instruction")

        resp = test_client.get("/api/prompts", headers=auth_header())
        assert resp.status_code == 200
        data = resp.json()
        slugs = [p["slug"] for p in data]
        assert "test_list_1" in slugs

    def test_list_prompts_filter_category(self, test_client, db_session):
        seed_test_prompt(db_session, slug="cat_a", category="analysis")
        seed_test_prompt(db_session, slug="cat_b", category="notification")

        resp = test_client.get("/api/prompts?category=analysis", headers=auth_header())
        assert resp.status_code == 200
        data = resp.json()
        for p in data:
            assert p["category"] == "analysis"

    def test_list_prompts_include_inactive(self, test_client, db_session):
        seed_test_prompt(db_session, slug="active_p")
        resp_active = test_client.get("/api/prompts?active_only=true", headers=auth_header())
        resp_all = test_client.get("/api/prompts?active_only=false", headers=auth_header())
        assert resp_active.status_code == 200
        assert resp_all.status_code == 200


class TestGetPrompt:
    """Tests for GET /api/prompts/{slug}."""

    def test_get_prompt_by_slug(self, test_client, db_session):
        seed_test_prompt(db_session, slug="get_me", name="Get Me Prompt", content="Hello world")

        resp = test_client.get("/api/prompts/get_me", headers=auth_header())
        assert resp.status_code == 200
        data = resp.json()
        assert data["slug"] == "get_me"
        assert data["name"] == "Get Me Prompt"
        assert data["content"] == "Hello world"
        assert "history" in data

    def test_get_prompt_not_found(self, test_client):
        resp = test_client.get("/api/prompts/nonexistent_slug", headers=auth_header())
        assert resp.status_code == 404


class TestCreatePrompt:
    """Tests for POST /api/prompts."""

    def test_create_prompt(self, test_client):
        resp = test_client.post("/api/prompts", json={
            "slug": "new_prompt",
            "name": "New Prompt",
            "category": "analysis",
            "content": "Analyze this claim...",
        }, headers=auth_header())
        assert resp.status_code == 201
        data = resp.json()
        assert data["slug"] == "new_prompt"
        assert data["status"] == "created"
        assert data["version"] == 1

    def test_create_prompt_with_model(self, test_client):
        resp = test_client.post("/api/prompts", json={
            "slug": "model_prompt",
            "name": "Model Prompt",
            "category": "analysis",
            "content": "Content",
            "model": "gemini-2.5-pro",
        }, headers=auth_header())
        assert resp.status_code == 201

    def test_create_prompt_duplicate_slug(self, test_client, db_session):
        seed_test_prompt(db_session, slug="dup_slug")
        resp = test_client.post("/api/prompts", json={
            "slug": "dup_slug",
            "name": "Duplicate",
            "category": "analysis",
            "content": "Content",
        }, headers=auth_header())
        assert resp.status_code == 409

    def test_create_prompt_missing_fields(self, test_client):
        resp = test_client.post("/api/prompts", json={"slug": "only_slug"}, headers=auth_header())
        assert resp.status_code == 422


class TestUpdatePrompt:
    """Tests for PATCH /api/prompts/{slug}."""

    def test_update_prompt_content(self, test_client, db_session):
        seed_test_prompt(db_session, slug="update_me", content="Original content")

        resp = test_client.patch("/api/prompts/update_me", json={
            "content": "Updated content",
            "updated_by": "miles",
        }, headers=auth_header())
        assert resp.status_code == 200
        data = resp.json()
        assert data["version"] == 2
        assert data["status"] == "updated"

        # Verify content was updated
        get_resp = test_client.get("/api/prompts/update_me", headers=auth_header())
        assert get_resp.json()["content"] == "Updated content"

    def test_update_prompt_creates_history(self, test_client, db_session):
        seed_test_prompt(db_session, slug="hist_prompt", content="Version 1")

        test_client.patch("/api/prompts/hist_prompt", json={"content": "Version 2"}, headers=auth_header())

        resp = test_client.get("/api/prompts/hist_prompt", headers=auth_header())
        data = resp.json()
        assert data["version"] == 2
        assert len(data["history"]) >= 1
        assert data["history"][0]["content"] == "Version 1"

    def test_update_prompt_not_found(self, test_client):
        resp = test_client.patch("/api/prompts/nonexistent", json={"content": "New"}, headers=auth_header())
        assert resp.status_code == 404

    def test_update_prompt_deactivate(self, test_client, db_session):
        seed_test_prompt(db_session, slug="deactivate_me")

        resp = test_client.patch("/api/prompts/deactivate_me", json={"is_active": False}, headers=auth_header())
        assert resp.status_code == 200
