"""Seed the local database with demo data.

Usage:
    uv run python src/pulsegraph/seed.py
"""

import datetime
import random
import uuid

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from pulsegraph.api.auth import hash_password
from pulsegraph.config import get_settings
from pulsegraph.db.models import PipelineRun, User, Watch
from pulsegraph.domain.enums import RunStatus, SourceKind, UserRole

_WATCHES = [
    {
        "source": SourceKind.JOBTECH,
        "prompt": "Python developer remote Stockholm",
        "hours": 1,
    },
    {
        "source": SourceKind.JOBTECH,
        "prompt": "Senior data engineer machine learning",
        "hours": 2,
    },
    {
        "source": SourceKind.JOBTECH,
        "prompt": "Backend engineer Rust or Go",
        "hours": 3,
        "active": False,
    },
    {
        "source": SourceKind.RIKSDAGEN,
        "prompt": "EU AI Act regulations parliament motions",
        "hours": 6,
    },
    {
        "source": SourceKind.RIKSDAGEN,
        "prompt": "Climate and energy policy 2025",
        "hours": 12,
        "active": False,
    },
    {
        "source": SourceKind.ENTSOE,
        "prompt": "Wind power capacity SE3 bidding zone",
        "hours": 4,
    },
]

# Runs per day: index 0 = 6 days ago, index 6 = today.
_RUNS_PER_DAY = [4, 7, 5, 9, 3, 8, 6]
_STATUS_POOL = [RunStatus.SUCCEEDED] * 9 + [RunStatus.FAILED]


def _timestamp(days_ago: int) -> datetime.datetime:
    base = datetime.datetime.now(datetime.UTC).replace(
        hour=random.randint(7, 22),
        minute=random.randint(0, 59),
        second=random.randint(0, 59),
        microsecond=0,
    )
    return base - datetime.timedelta(days=days_ago)


def seed() -> None:
    settings = get_settings()
    engine = create_engine(settings.database_url)

    with Session(engine) as session:
        exists = session.execute(
            text("SELECT 1 FROM users WHERE email = 'demo@pulsegraph.dev'")
        ).first()
        if exists:
            print("Already seeded — skipping.")
            return

        demo = User(
            id=uuid.uuid4(),
            email="demo@pulsegraph.dev",
            password_hash=hash_password("demo1234"),
            role=UserRole.USER,
        )
        admin = User(
            id=uuid.uuid4(),
            email="admin@pulsegraph.dev",
            password_hash=hash_password("admin1234"),
            role=UserRole.ADMIN,
        )
        session.add_all([demo, admin])
        session.flush()

        watches = []
        for spec in _WATCHES:
            hours = spec["hours"]
            w = Watch(
                id=uuid.uuid4(),
                user_id=demo.id,
                source=spec["source"],
                prompt=spec["prompt"],
                is_active=spec.get("active", True),
                schedule_interval=datetime.timedelta(hours=hours),
                last_run_at=_timestamp(0),
                next_run_at=datetime.datetime.now(datetime.UTC)
                + datetime.timedelta(hours=hours),
                config={},
            )
            watches.append(w)
        session.add_all(watches)
        session.flush()

        runs = []
        for days_ago, count in enumerate(reversed(_RUNS_PER_DAY)):
            for _ in range(count):
                watch = random.choice(watches)
                status = random.choice(_STATUS_POOL)
                started = _timestamp(days_ago)
                finished = started + datetime.timedelta(
                    seconds=random.randint(4, 90)
                )
                runs.append(
                    PipelineRun(
                        id=uuid.uuid4(),
                        watch_id=watch.id,
                        status=status,
                        started_at=started,
                        finished_at=finished,
                        error=(
                            "Schema validation failed: unexpected field"
                            if status == RunStatus.FAILED
                            else None
                        ),
                    )
                )
        session.add_all(runs)
        session.commit()

    print(
        f"Seeded: demo@pulsegraph.dev (demo1234), "
        f"admin@pulsegraph.dev (admin1234), "
        f"{len(watches)} watches, {len(runs)} pipeline runs."
    )


if __name__ == "__main__":
    seed()
