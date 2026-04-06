"""JWT authentication service (Section 18C).

Handles password verification with bcrypt and JWT token creation/validation.
"""

from datetime import datetime, timedelta

import bcrypt as _bcrypt
from jose import jwt, JWTError
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings

ALGORITHM = "HS256"


def authenticate(db: Session, username: str, password: str) -> dict | None:
    """Validate credentials and return a JWT token dict, or None on failure."""
    row = db.execute(
        text("SELECT id, username, password_hash, display_name, role FROM users WHERE username = :u AND is_active = true"),
        {"u": username},
    ).fetchone()

    if not row:
        return None

    if not _bcrypt.checkpw(password.encode(), row[2].encode()):
        return None

    token = jwt.encode(
        {
            "sub": row[1],
            "role": row[4],
            "exp": datetime.utcnow() + timedelta(minutes=settings.session_timeout_minutes),
        },
        settings.session_secret,
        algorithm=ALGORITHM,
    )

    return {
        "token": token,
        "expires_in": settings.session_timeout_minutes * 60,
        "user": {
            "id": row[0],
            "username": row[1],
            "display_name": row[3],
            "role": row[4],
        },
    }


def decode_token(token: str) -> dict:
    """Decode and validate a JWT token. Raises JWTError on failure."""
    payload = jwt.decode(token, settings.session_secret, algorithms=[ALGORITHM])
    return {"username": payload["sub"], "role": payload["role"]}


def get_current_user_from_db(db: Session, username: str) -> dict | None:
    """Look up user details by username."""
    row = db.execute(
        text("SELECT id, username, display_name, role, is_active, created_at FROM users WHERE username = :u"),
        {"u": username},
    ).fetchone()

    if not row or not row[4]:
        return None

    return {
        "id": row[0],
        "username": row[1],
        "display_name": row[2],
        "role": row[3],
        "created_at": str(row[5]) if row[5] else None,
    }
