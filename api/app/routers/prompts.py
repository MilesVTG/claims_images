"""Prompt CRUD endpoints (Section 13C).

GET    /prompts           — list all prompts (filterable by category)
GET    /prompts/{slug}    — get single prompt by slug
POST   /prompts           — create new prompt
PATCH  /prompts/{slug}    — update prompt content (auto-increments version, logs history)
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user

router = APIRouter(prefix="/prompts", tags=["prompts"])


class PromptCreate(BaseModel):
    slug: str
    name: str
    category: str
    content: str
    model: str = "gemini-2.5-flash"


class PromptUpdate(BaseModel):
    name: Optional[str] = None
    content: Optional[str] = None
    model: Optional[str] = None
    is_active: Optional[bool] = None
    updated_by: Optional[str] = None


@router.get("")
def list_prompts(
    category: Optional[str] = None,
    active_only: bool = Query(True),
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    """List all prompts, optionally filtered by category."""
    conditions = []
    params: dict = {}

    if active_only:
        conditions.append("is_active = true")
    if category:
        conditions.append("category = :category")
        params["category"] = category

    where = "WHERE " + " AND ".join(conditions) if conditions else ""

    rows = db.execute(
        text(f"""
            SELECT id, slug, name, category, content, model, is_active, version,
                   created_at, updated_at, updated_by
            FROM system_prompts
            {where}
            ORDER BY category, slug
        """),
        params,
    ).fetchall()

    return [
        {
            "id": r[0],
            "slug": r[1],
            "name": r[2],
            "category": r[3],
            "content": r[4],
            "model": r[5],
            "is_active": r[6],
            "version": r[7],
            "created_at": str(r[8]) if r[8] else None,
            "updated_at": str(r[9]) if r[9] else None,
            "updated_by": r[10],
        }
        for r in rows
    ]


@router.get("/{slug}")
def get_prompt(slug: str, db: Session = Depends(get_db), _user: dict = Depends(get_current_user)):
    """Get a single prompt by slug."""
    row = db.execute(
        text("""
            SELECT id, slug, name, category, content, model, is_active, version,
                   created_at, updated_at, updated_by
            FROM system_prompts
            WHERE slug = :slug
        """),
        {"slug": slug},
    ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Prompt not found")

    # Fetch version history
    history = db.execute(
        text("""
            SELECT id, version, content, changed_by, changed_at
            FROM prompt_history
            WHERE prompt_id = :pid
            ORDER BY version DESC
        """),
        {"pid": row[0]},
    ).fetchall()

    return {
        "id": row[0],
        "slug": row[1],
        "name": row[2],
        "category": row[3],
        "content": row[4],
        "model": row[5],
        "is_active": row[6],
        "version": row[7],
        "created_at": str(row[8]) if row[8] else None,
        "updated_at": str(row[9]) if row[9] else None,
        "updated_by": row[10],
        "history": [
            {
                "id": h[0],
                "version": h[1],
                "content": h[2],
                "changed_by": h[3],
                "changed_at": str(h[4]) if h[4] else None,
            }
            for h in history
        ],
    }


@router.post("", status_code=201)
def create_prompt(body: PromptCreate, db: Session = Depends(get_db), _user: dict = Depends(get_current_user)):
    """Create a new prompt."""
    # Check for duplicate slug
    existing = db.execute(
        text("SELECT id FROM system_prompts WHERE slug = :slug"),
        {"slug": body.slug},
    ).fetchone()

    if existing:
        raise HTTPException(status_code=409, detail="Prompt with this slug already exists")

    result = db.execute(
        text("""
            INSERT INTO system_prompts (slug, name, category, content, model)
            VALUES (:slug, :name, :category, :content, :model)
            RETURNING id, version
        """),
        {
            "slug": body.slug,
            "name": body.name,
            "category": body.category,
            "content": body.content,
            "model": body.model,
        },
    )
    row = result.fetchone()
    db.commit()

    return {
        "id": row[0],
        "slug": body.slug,
        "version": row[1],
        "status": "created",
    }


@router.patch("/{slug}")
def update_prompt(slug: str, body: PromptUpdate, db: Session = Depends(get_db), _user: dict = Depends(get_current_user)):
    """Update a prompt. Auto-increments version and logs to prompt_history."""
    # Fetch current prompt
    current = db.execute(
        text("SELECT id, version, content FROM system_prompts WHERE slug = :slug"),
        {"slug": slug},
    ).fetchone()

    if not current:
        raise HTTPException(status_code=404, detail="Prompt not found")

    prompt_id = current[0]
    old_version = current[1]
    old_content = current[2]
    new_version = old_version + 1

    # Build SET clause dynamically from provided fields
    set_parts = ["version = :new_version", "updated_at = NOW()"]
    params: dict = {"slug": slug, "new_version": new_version}

    if body.content is not None:
        set_parts.append("content = :content")
        params["content"] = body.content
    if body.name is not None:
        set_parts.append("name = :name")
        params["name"] = body.name
    if body.model is not None:
        set_parts.append("model = :model")
        params["model"] = body.model
    if body.is_active is not None:
        set_parts.append("is_active = :is_active")
        params["is_active"] = body.is_active
    if body.updated_by is not None:
        set_parts.append("updated_by = :updated_by")
        params["updated_by"] = body.updated_by

    set_clause = ", ".join(set_parts)

    db.execute(
        text(f"UPDATE system_prompts SET {set_clause} WHERE slug = :slug"),
        params,
    )

    # Log old content to prompt_history for audit trail
    db.execute(
        text("""
            INSERT INTO prompt_history (prompt_id, version, content, changed_by)
            VALUES (:pid, :version, :content, :changed_by)
        """),
        {
            "pid": prompt_id,
            "version": old_version,
            "content": old_content,
            "changed_by": body.updated_by,
        },
    )

    db.commit()

    return {
        "slug": slug,
        "version": new_version,
        "status": "updated",
    }
