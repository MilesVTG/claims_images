"""ErrorLog model — structured error tracking for API and Worker services."""

from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ErrorLog(Base):
    __tablename__ = "error_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(server_default=func.now(), index=True)
    service: Mapped[str] = mapped_column(String(50), index=True)  # "api" or "worker"
    endpoint: Mapped[Optional[str]] = mapped_column(String(500))
    method: Mapped[Optional[str]] = mapped_column(String(10))
    status_code: Mapped[Optional[int]] = mapped_column(Integer)
    error_type: Mapped[Optional[str]] = mapped_column(String(200))
    message: Mapped[Optional[str]] = mapped_column(Text)
    traceback: Mapped[Optional[str]] = mapped_column(Text)
    request_id: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    pipeline_stage: Mapped[Optional[str]] = mapped_column(String(100))
