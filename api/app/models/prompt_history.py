"""PromptHistory model — audit trail for prompt changes (Section 13E)."""

from datetime import datetime
from typing import Optional

from sqlalchemy import Integer, Text, String, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class PromptHistory(Base):
    __tablename__ = "prompt_history"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    prompt_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("system_prompts.id"))
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    changed_by: Mapped[Optional[str]] = mapped_column(String(100))
    changed_at: Mapped[datetime] = mapped_column(server_default=func.now())
