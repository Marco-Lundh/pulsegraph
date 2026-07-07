"""per-channel notification rows: add channel to the unique key (ADR 0016)

Revision ID: d4f1a7c93e28
Revises: b7e4c1a9f2d3
Create Date: 2026-07-07 09:30:00.000000

Instant email/webhook delivery now writes its own ``Notification`` row per
channel (status/delivered_at/attempts tracked independently), so the
single-row-per-item unique key ``(user_id, dedup_key)`` must widen to
include ``channel``. The old constraint was created unnamed by the initial
migration, so PostgreSQL auto-named it ``notifications_user_id_dedup_key_key``.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "d4f1a7c93e28"
down_revision: str | None = "b7e4c1a9f2d3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD_NAME = "notifications_user_id_dedup_key_key"
_NEW_NAME = "uq_notifications_user_dedup_channel"


def upgrade() -> None:
    op.drop_constraint(_OLD_NAME, "notifications", type_="unique")
    op.create_unique_constraint(
        _NEW_NAME,
        "notifications",
        ["user_id", "dedup_key", "channel"],
    )


def downgrade() -> None:
    op.drop_constraint(_NEW_NAME, "notifications", type_="unique")
    op.create_unique_constraint(
        _OLD_NAME,
        "notifications",
        ["user_id", "dedup_key"],
    )
