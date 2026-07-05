"""add user consented_at column (GDPR consent at signup, ADR 0018)

Revision ID: b7e4c1a9f2d3
Revises: 05fd3d69bbaa
Create Date: 2026-07-05 21:40:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b7e4c1a9f2d3"
down_revision: str | None = "05fd3d69bbaa"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "consented_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "consented_at")
