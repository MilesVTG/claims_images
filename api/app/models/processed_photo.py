"""ProcessedPhoto model — idempotency tracking (Section 7B)."""

from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ProcessedPhoto(Base):
    __tablename__ = "processed_photos"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    storage_key: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    contract_id: Mapped[Optional[str]] = mapped_column(String(100))
    claim_id: Mapped[Optional[str]] = mapped_column(String(100))
    processed_at: Mapped[datetime] = mapped_column(server_default=func.now())
    status: Mapped[str] = mapped_column(String(20), server_default="completed")
