"""Initial schema: claims, processed_photos, users, system_prompts, golden_dataset

Revision ID: 001_initial
Revises: None
Create Date: 2026-03-31
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, ARRAY

# revision identifiers, used by Alembic.
revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- users ---
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("username", sa.String(100), unique=True, nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(255)),
        sa.Column("role", sa.String(50), server_default="reviewer"),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )

    # --- claims ---
    op.create_table(
        "claims",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("contract_id", sa.String(100), nullable=False),
        sa.Column("claim_id", sa.String(100), nullable=False),
        sa.Column("claim_date", sa.Date),
        sa.Column("reported_loss_date", sa.Date),
        sa.Column("service_drive_location", sa.Text),
        sa.Column("service_drive_coords", sa.String(50)),
        sa.Column("photo_uris", ARRAY(sa.Text)),
        sa.Column("extracted_metadata", JSONB),
        sa.Column("reverse_image_results", JSONB),
        sa.Column("gemini_analysis", JSONB),
        sa.Column("risk_score", sa.Float),
        sa.Column("red_flags", ARRAY(sa.Text)),
        sa.Column("processed_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.UniqueConstraint("contract_id", "claim_id", name="uq_claims_contract_claim"),
    )
    op.create_index(
        "idx_claims_contract", "claims", ["contract_id", sa.text("claim_date DESC")]
    )
    op.create_index(
        "idx_claims_risk", "claims", ["risk_score"],
        postgresql_where=sa.text("risk_score > 50"),
    )

    # --- processed_photos ---
    op.create_table(
        "processed_photos",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("storage_key", sa.Text, unique=True, nullable=False),
        sa.Column("contract_id", sa.String(100)),
        sa.Column("claim_id", sa.String(100)),
        sa.Column("processed_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("status", sa.String(20), server_default="completed"),
    )

    # --- system_prompts ---
    op.create_table(
        "system_prompts",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("slug", sa.String(100), unique=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("model", sa.String(50), server_default="gemini-2.5-flash"),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("true")),
        sa.Column("version", sa.Integer, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_by", sa.String(100)),
    )
    op.create_index(
        "idx_prompts_slug", "system_prompts", ["slug"],
        postgresql_where=sa.text("is_active = true"),
    )

    # --- prompt_history ---
    op.create_table(
        "prompt_history",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("prompt_id", sa.Integer, sa.ForeignKey("system_prompts.id")),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("changed_by", sa.String(100)),
        sa.Column("changed_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )

    # --- golden_dataset ---
    op.create_table(
        "golden_dataset",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("storage_key", sa.Text, nullable=False),
        sa.Column("expected_risk_min", sa.Float, nullable=False),
        sa.Column("expected_risk_max", sa.Float, nullable=False),
        sa.Column("expected_flags", ARRAY(sa.Text)),
        sa.Column("must_not_flags", ARRAY(sa.Text)),
        sa.Column("expected_tire_brand", sa.String(100)),
        sa.Column("expected_color", sa.String(100)),
        sa.Column("notes", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )


def downgrade() -> None:
    op.drop_table("golden_dataset")
    op.drop_table("prompt_history")
    op.drop_table("system_prompts")
    op.drop_table("processed_photos")
    op.drop_table("claims")
    op.drop_table("users")
