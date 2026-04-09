"""Shared prompt loading service.

Provides get_active_prompt() used by gemini_service and email_service to
load system prompts from the database by slug.
"""

import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def get_active_prompt(db: Session, slug: str) -> str:
    """Fetch the active prompt content by slug from the database."""
    result = db.execute(
        text("SELECT content FROM system_prompts WHERE slug = :slug AND is_active = true"),
        {"slug": slug},
    ).fetchone()
    if not result:
        raise ValueError(f"No active prompt found for slug: {slug}")
    return result[0]
