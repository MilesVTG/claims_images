"""Unit tests for config, dependencies, and auth_service internals.

Covers:
- Settings defaults and CORS parsing
- Token blacklist (add / check)
- get_current_user dependency (valid, missing header, expired, blacklisted)
- auth_service.authenticate() (valid, wrong password, user not found)
- auth_service.decode_token() (valid, expired, invalid)

Does NOT duplicate integration tests in test_api_auth.py (endpoint-level).
"""

import os
import uuid
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from jose import jwt, JWTError

from tests.conftest import (
    make_auth_token,
    make_expired_token,
    seed_test_user,
    TEST_SECRET,
    TEST_ALGORITHM,
)


# =========================================================================
# 1. Config / Settings
# =========================================================================

class TestSettingsDefaults:
    """Verify default values on a fresh Settings instance."""

    def test_default_database_url_is_none(self):
        """Default is None; conftest sets DATABASE_URL so we clear it."""
        from app.config import Settings
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("DATABASE_URL", None)
            s = Settings(session_secret="x")
            assert s.database_url is None

    def test_default_gcs_bucket(self):
        from app.config import Settings
        s = Settings(session_secret="x")
        assert s.gcs_bucket == "claims-photos"

    def test_default_gemini_model(self):
        from app.config import Settings
        s = Settings(session_secret="x")
        assert s.gemini_model == "gemini-2.5-flash"

    def test_default_session_timeout(self):
        from app.config import Settings
        s = Settings(session_secret="x")
        assert s.session_timeout_minutes == 60

    def test_default_debug_false(self):
        from app.config import Settings
        s = Settings(session_secret="x")
        assert s.debug is False

    def test_default_environment(self):
        from app.config import Settings
        s = Settings(session_secret="x")
        assert s.environment == "development"

    def test_default_cors_origins_string(self):
        from app.config import Settings
        s = Settings(session_secret="x")
        assert "localhost:3000" in s.cors_origins
        assert "localhost:5173" in s.cors_origins


class TestCORSParsing:
    """Verify the CORS splitting logic used in main.py."""

    def test_cors_split_default(self):
        """Default cors_origins splits into three origins."""
        from app.config import Settings
        s = Settings(session_secret="x")
        origins = [o.strip() for o in s.cors_origins.split(",") if o.strip()]
        assert origins == [
            "http://localhost:3000",
            "http://localhost:5173",
            "http://localhost:8080",
        ]

    def test_cors_split_single_origin(self):
        from app.config import Settings
        s = Settings(session_secret="x", cors_origins="https://example.com")
        origins = [o.strip() for o in s.cors_origins.split(",") if o.strip()]
        assert origins == ["https://example.com"]

    def test_cors_split_trailing_comma(self):
        from app.config import Settings
        s = Settings(session_secret="x", cors_origins="http://a.com, http://b.com,")
        origins = [o.strip() for o in s.cors_origins.split(",") if o.strip()]
        assert origins == ["http://a.com", "http://b.com"]

    def test_cors_split_empty_string(self):
        from app.config import Settings
        s = Settings(session_secret="x", cors_origins="")
        origins = [o.strip() for o in s.cors_origins.split(",") if o.strip()]
        assert origins == []

    def test_cors_split_whitespace_around_commas(self):
        from app.config import Settings
        s = Settings(session_secret="x", cors_origins=" http://a.com , http://b.com ")
        origins = [o.strip() for o in s.cors_origins.split(",") if o.strip()]
        assert origins == ["http://a.com", "http://b.com"]


class TestSettingsFromEnv:
    """Settings loads values from environment variables."""

    def test_override_via_env(self):
        from app.config import Settings
        with patch.dict(os.environ, {"GCS_BUCKET": "my-bucket", "DEBUG": "true"}):
            s = Settings(session_secret="x")
            assert s.gcs_bucket == "my-bucket"
            assert s.debug is True

    def test_extra_env_vars_ignored(self):
        """extra='ignore' means unknown env vars don't blow up."""
        from app.config import Settings
        with patch.dict(os.environ, {"TOTALLY_UNKNOWN_VAR": "whatever"}):
            s = Settings(session_secret="x")
            assert not hasattr(s, "totally_unknown_var")


# =========================================================================
# 2. Dependencies — token blacklist
# =========================================================================

class TestTokenBlacklist:
    """Tests for blacklist_token / is_token_blacklisted."""

    def test_fresh_jti_not_blacklisted(self):
        from app.dependencies import is_token_blacklisted
        assert is_token_blacklisted(str(uuid.uuid4())) is False

    def test_blacklist_then_check(self):
        from app.dependencies import blacklist_token, is_token_blacklisted
        jti = str(uuid.uuid4())
        blacklist_token(jti)
        assert is_token_blacklisted(jti) is True

    def test_blacklist_idempotent(self):
        from app.dependencies import blacklist_token, is_token_blacklisted
        jti = str(uuid.uuid4())
        blacklist_token(jti)
        blacklist_token(jti)  # second call should not raise
        assert is_token_blacklisted(jti) is True

    def test_different_jti_not_affected(self):
        from app.dependencies import blacklist_token, is_token_blacklisted
        jti_a = str(uuid.uuid4())
        jti_b = str(uuid.uuid4())
        blacklist_token(jti_a)
        assert is_token_blacklisted(jti_b) is False


# =========================================================================
# 3. Dependencies — get_current_user
# =========================================================================

class TestGetCurrentUser:
    """Unit tests for the get_current_user dependency function."""

    def test_valid_token_returns_user_dict(self):
        from app.dependencies import get_current_user
        token = make_auth_token(username="alice", role="reviewer")
        result = get_current_user(authorization=f"Bearer {token}")
        assert result["username"] == "alice"
        assert result["role"] == "reviewer"

    def test_missing_bearer_prefix_raises_401(self):
        from app.dependencies import get_current_user
        with pytest.raises(HTTPException) as exc_info:
            get_current_user(authorization="Token abc123")
        assert exc_info.value.status_code == 401
        assert "Invalid authorization header" in exc_info.value.detail

    def test_expired_token_raises_401(self):
        from app.dependencies import get_current_user
        token = make_expired_token(username="bob")
        with pytest.raises(HTTPException) as exc_info:
            get_current_user(authorization=f"Bearer {token}")
        assert exc_info.value.status_code == 401

    def test_garbage_token_raises_401(self):
        from app.dependencies import get_current_user
        with pytest.raises(HTTPException) as exc_info:
            get_current_user(authorization="Bearer not.a.jwt")
        assert exc_info.value.status_code == 401

    def test_blacklisted_token_raises_401(self):
        from app.dependencies import get_current_user, blacklist_token
        jti = str(uuid.uuid4())
        payload = {
            "sub": "charlie",
            "role": "admin",
            "jti": jti,
            "exp": datetime.utcnow() + timedelta(hours=1),
        }
        token = jwt.encode(payload, TEST_SECRET, algorithm=TEST_ALGORITHM)
        blacklist_token(jti)
        with pytest.raises(HTTPException) as exc_info:
            get_current_user(authorization=f"Bearer {token}")
        assert exc_info.value.status_code == 401
        assert "revoked" in exc_info.value.detail

    def test_token_without_jti_still_works(self):
        """Tokens without jti (e.g. from conftest helpers) should be accepted."""
        from app.dependencies import get_current_user
        payload = {
            "sub": "dave",
            "role": "reviewer",
            "exp": datetime.utcnow() + timedelta(hours=1),
        }
        token = jwt.encode(payload, TEST_SECRET, algorithm=TEST_ALGORITHM)
        result = get_current_user(authorization=f"Bearer {token}")
        assert result["username"] == "dave"
        assert result["jti"] is None


# =========================================================================
# 4. auth_service — authenticate()
# =========================================================================

class TestAuthServiceAuthenticate:
    """Unit tests for auth_service.authenticate() called directly."""

    def test_valid_credentials_return_token_dict(self, db_session):
        from app.services.auth_service import authenticate
        seed_test_user(db_session, username="miles", role="admin")
        result = authenticate(db_session, "miles", "testpassword123")
        assert result is not None
        assert "token" in result
        assert result["user"]["username"] == "miles"
        assert result["user"]["role"] == "admin"
        assert result["expires_in"] == 3600  # 60 min * 60 sec

    def test_valid_credentials_token_has_jti(self, db_session):
        from app.services.auth_service import authenticate, decode_token
        seed_test_user(db_session, username="miles", role="admin")
        result = authenticate(db_session, "miles", "testpassword123")
        decoded = decode_token(result["token"])
        assert decoded["jti"] is not None
        # JTI should be a valid UUID
        uuid.UUID(decoded["jti"])

    def test_wrong_password_returns_none(self, db_session):
        from app.services.auth_service import authenticate
        seed_test_user(db_session, username="miles")
        result = authenticate(db_session, "miles", "wrong-password")
        assert result is None

    def test_nonexistent_user_returns_none(self, db_session):
        from app.services.auth_service import authenticate
        result = authenticate(db_session, "ghost", "any-password")
        assert result is None


# =========================================================================
# 5. auth_service — decode_token()
# =========================================================================

class TestAuthServiceDecodeToken:
    """Unit tests for auth_service.decode_token()."""

    def test_decode_valid_token(self):
        from app.services.auth_service import decode_token
        token = make_auth_token(username="alice", role="reviewer")
        payload = decode_token(token)
        assert payload["username"] == "alice"
        assert payload["role"] == "reviewer"

    def test_decode_expired_token_raises(self):
        from app.services.auth_service import decode_token
        token = make_expired_token(username="bob")
        with pytest.raises(JWTError):
            decode_token(token)

    def test_decode_invalid_token_raises(self):
        from app.services.auth_service import decode_token
        with pytest.raises(JWTError):
            decode_token("this-is-not-a-jwt")

    def test_decode_wrong_secret_raises(self):
        from app.services.auth_service import decode_token
        payload = {
            "sub": "eve",
            "role": "admin",
            "exp": datetime.utcnow() + timedelta(hours=1),
        }
        token = jwt.encode(payload, "wrong-secret", algorithm=TEST_ALGORITHM)
        with pytest.raises(JWTError):
            decode_token(token)

    def test_decode_returns_jti_when_present(self):
        from app.services.auth_service import decode_token
        jti = str(uuid.uuid4())
        payload = {
            "sub": "frank",
            "role": "reviewer",
            "jti": jti,
            "exp": datetime.utcnow() + timedelta(hours=1),
        }
        token = jwt.encode(payload, TEST_SECRET, algorithm=TEST_ALGORITHM)
        result = decode_token(token)
        assert result["jti"] == jti

    def test_decode_returns_none_jti_when_absent(self):
        from app.services.auth_service import decode_token
        token = make_auth_token(username="gina", role="admin")
        result = decode_token(token)
        assert result["jti"] is None


# =========================================================================
# 6. auth_service — get_current_user_from_db()
# =========================================================================

class TestGetCurrentUserFromDB:
    """Unit tests for auth_service.get_current_user_from_db()."""

    def test_returns_user_dict(self, db_session):
        from app.services.auth_service import get_current_user_from_db
        seed_test_user(db_session, username="miles", role="admin")
        result = get_current_user_from_db(db_session, "miles")
        assert result is not None
        assert result["username"] == "miles"
        assert result["role"] == "admin"
        assert "id" in result

    def test_nonexistent_user_returns_none(self, db_session):
        from app.services.auth_service import get_current_user_from_db
        result = get_current_user_from_db(db_session, "ghost")
        assert result is None

    def test_inactive_user_returns_none(self, db_session):
        from app.services.auth_service import get_current_user_from_db
        from sqlalchemy import text
        seed_test_user(db_session, username="inactive_user", role="reviewer")
        db_session.execute(
            text("UPDATE users SET is_active = 0 WHERE username = :u"),
            {"u": "inactive_user"},
        )
        db_session.commit()
        result = get_current_user_from_db(db_session, "inactive_user")
        assert result is None
