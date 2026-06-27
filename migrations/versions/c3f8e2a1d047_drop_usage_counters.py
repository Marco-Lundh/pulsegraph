"""drop usage_counters table (rate limiting moved to Redis, ADR 0022)

Revision ID: c3f8e2a1d047
Revises: 1d6c2762d036
Create Date: 2026-06-25 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c3f8e2a1d047"
down_revision: str | None = "1d6c2762d036"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_table("usage_counters")


def downgrade() -> None:
    op.create_table(
        "usage_counters",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column(
            "window_start",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "run_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", "window_start"),
    )
