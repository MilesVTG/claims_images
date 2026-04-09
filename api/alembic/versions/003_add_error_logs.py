"""Add error_logs table for structured error tracking.

Revision ID: 003_error_logs
Revises: 002_sql_views
Create Date: 2026-04-09
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003_error_logs"
down_revision: Union[str, None] = "002_sql_views"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "error_logs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("timestamp", sa.DateTime, server_default=sa.func.now(), index=True),
        sa.Column("service", sa.String(50), nullable=False, index=True),
        sa.Column("endpoint", sa.String(500)),
        sa.Column("method", sa.String(10)),
        sa.Column("status_code", sa.Integer),
        sa.Column("error_type", sa.String(200)),
        sa.Column("message", sa.Text),
        sa.Column("traceback", sa.Text),
        sa.Column("request_id", sa.String(100), index=True),
        sa.Column("pipeline_stage", sa.String(100)),
    )


def downgrade() -> None:
    op.drop_table("error_logs")
