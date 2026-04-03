"""Claim model — core claims table (Section 7A)."""

from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import String, Text, Date, Float, UniqueConstraint, Index, func, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Claim(Base):
    __tablename__ = "claims"
    __table_args__ = (
        UniqueConstraint("contract_id", "claim_id", name="uq_claims_contract_claim"),
        Index("idx_claims_contract", "contract_id", text("claim_date DESC")),
        Index("idx_claims_risk", "risk_score", postgresql_where=text("risk_score > 50")),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    contract_id: Mapped[str] = mapped_column(String(100), nullable=False)
    claim_id: Mapped[str] = mapped_column(String(100), nullable=False)
    claim_date: Mapped[Optional[date]] = mapped_column(Date)
    reported_loss_date: Mapped[Optional[date]] = mapped_column(Date)
    service_drive_location: Mapped[Optional[str]] = mapped_column(Text)
    service_drive_coords: Mapped[Optional[str]] = mapped_column(String(50))
    photo_uris: Mapped[Optional[list[str]]] = mapped_column(ARRAY(Text))
    extracted_metadata: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB)
    reverse_image_results: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB)
    gemini_analysis: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB)
    risk_score: Mapped[Optional[float]] = mapped_column(Float)
    red_flags: Mapped[Optional[list[str]]] = mapped_column(ARRAY(Text))
    processed_at: Mapped[datetime] = mapped_column(server_default=func.now())
