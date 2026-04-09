"""Auth endpoints (Section 14E / 18C).

POST /auth/login  — authenticate and return JWT
POST /auth/logout — blacklist JWT so it cannot be reused
GET  /auth/me     — current user info from token
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user, blacklist_token
from app.services.auth_service import authenticate, get_current_user_from_db

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(body: LoginRequest, db: Session = Depends(get_db)):
    """Authenticate user and return JWT token."""
    result = authenticate(db, body.username, body.password)
    if not result:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    return result


@router.post("/logout")
def logout(user: dict = Depends(get_current_user)):
    """Logout — blacklist the token's JTI so it cannot be reused."""
    jti = user.get("jti")
    if jti:
        blacklist_token(jti)
    return {"status": "ok", "message": "Token revoked"}


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
