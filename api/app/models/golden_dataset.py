"""GoldenDataset model — baseline heuristics for regression testing (Section 19D)."""

from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, Float, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class GoldenDataset(Base):
    __tablename__ = "golden_dataset"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    expected_risk_min: Mapped[float] = mapped_column(Float, nullable=False)
    expected_risk_max: Mapped[float] = mapped_column(Float, nullable=False)
    expected_flags: Mapped[Optional[list[str]]] = mapped_column(ARRAY(Text))
    must_not_flags: Mapped[Optional[list[str]]] = mapped_column(ARRAY(Text))
    expected_tire_brand: Mapped[Optional[str]] = mapped_column(String(100))
    expected_color: Mapped[Optional[str]] = mapped_column(String(100))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
