"""add notification attempts column (digest retry cap, ADR 0016)

Revision ID: 05fd3d69bbaa
Revises: c3f8e2a1d047
Create Date: 2026-07-05 07:55:45.969073
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "05fd3d69bbaa"
down_revision: str | None = "c3f8e2a1d047"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "notifications",
        sa.Column(
            "attempts",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )


def downgrade() -> None:
    op.drop_column("notifications", "attempts")
