"""Auth endpoints (Section 14E / 18C).

POST /auth/login  — authenticate and return JWT
POST /auth/logout — client-side token discard (no server blacklist in POC)
GET  /auth/me     — current user info from token
"""

from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
from sqlalchemy.orm import Session
from jose import JWTError

from app.database import get_db
from app.services.auth_service import authenticate, decode_token, get_current_user_from_db

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


def get_current_user(
    authorization: str = Header(..., description="Bearer <token>"),
) -> dict:
    """Dependency: extract and validate JWT from Authorization header."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header")
    token = authorization.removeprefix("Bearer ").strip()
    try:
        return decode_token(token)
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


@router.post("/login")
def login(body: LoginRequest, db: Session = Depends(get_db)):
    """Authenticate user and return JWT token."""
    result = authenticate(db, body.username, body.password)
    if not result:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    return result


@router.post("/logout")
def logout(user: dict = Depends(get_current_user)):
    """Logout — in POC phase this is a no-op; client discards the token."""
    return {"status": "ok", "message": "Token should be discarded by client"}


@router.get("/me")
def me(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return current authenticated user info."""
    user_data = get_current_user_from_db(db, user["username"])
    if not user_data:
        raise HTTPException(status_code=404, detail="User not found")
    return user_data
