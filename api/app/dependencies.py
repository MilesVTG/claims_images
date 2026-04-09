"""Shared FastAPI dependencies.

Centralises get_current_user so every router can import it without
circular-import issues (auth_service ← dependencies ← routers).
"""

from fastapi import Header, HTTPException
from jose import JWTError

from app.services.auth_service import decode_token

# ---------------------------------------------------------------------------
# In-memory token blacklist (POC — use Redis / DB for production)
# ---------------------------------------------------------------------------
_blacklisted_jtis: set[str] = set()


def blacklist_token(jti: str) -> None:
    """Add a JTI to the blacklist so the token is no longer accepted."""
    _blacklisted_jtis.add(jti)


def is_token_blacklisted(jti: str) -> bool:
    return jti in _blacklisted_jtis


# ---------------------------------------------------------------------------
# Auth dependency
# ---------------------------------------------------------------------------
def get_current_user(
    authorization: str = Header(..., description="Bearer <token>"),
) -> dict:
    """Dependency: extract and validate JWT from Authorization header."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header")
    token = authorization.removeprefix("Bearer ").strip()
    try:
        payload = decode_token(token)
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    # Reject blacklisted tokens (logout invalidation)
    jti = payload.get("jti")
    if jti and is_token_blacklisted(jti):
        raise HTTPException(status_code=401, detail="Token has been revoked")

    return payload
