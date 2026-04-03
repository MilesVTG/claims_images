"""SystemPrompt model — prompt management (Section 13A)."""

from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, Boolean, Integer, Index, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class SystemPrompt(Base):
    __tablename__ = "system_prompts"
    __table_args__ = (
        Index("idx_prompts_slug", "slug", postgresql_where=text("is_active = true")),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(String(50), server_default="gemini-2.5-flash")
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true")
    version: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_by: Mapped[Optional[str]] = mapped_column(String(100))
