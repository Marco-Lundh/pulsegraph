#!/usr/bin/env python
"""End-to-end smoke test against the real Docker stack (ADR 0019).

Brings up Postgres + Redis via ``docker compose``, applies migrations,
runs one watch through the real pipeline runner against the live
database and Redis, and verifies the run was persisted and the expected
Redis keys (fetch cache, rate-limit counter) were written.

It uses fixture records for the source so it needs no network or Ollama,
while still exercising the real DB and Redis integration end to end.

    docker compose up -d        # or docker-compose; or let this run it
    uv run python scripts/smoke_e2e.py
"""

import datetime
import subprocess
import sys
import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from pulsegraph.config import get_settings
from pulsegraph.db.models import PipelineRun, User, Watch
from pulsegraph.domain.enums import RunStatus, SourceKind, UserRole
from pulsegraph.pipeline.agents import PipelineDeps
from pulsegraph.pipeline.local import (
    DictSourceRegistry,
    HashingEmbedder,
    InMemorySink,
    KeywordModelClient,
    StaticSourcePlugin,
)
from pulsegraph.redis_client import make_redis
from pulsegraph.worker.tasks import run_watch_core

_RECORDS = [
    {"id": "1", "title": "Senior Python Engineer", "body": "x" * 700},
    {"id": "2", "title": "Rust Systems Engineer", "body": "y" * 700},
]


def _run(cmd: list[str]) -> None:
    print(f"$ {' '.join(cmd)}")
    subprocess.run(cmd, check=True)


def _compose_cmd() -> list[str]:
    """Return the available Docker Compose command.

    Prefers the ``docker compose`` plugin and falls back to the
    standalone ``docker-compose`` binary, so the smoke test runs on a
    host with either one installed.
    """
    for cmd in (["docker", "compose"], ["docker-compose"]):
        try:
            subprocess.run([*cmd, "version"], check=True, capture_output=True)
            return cmd
        except (subprocess.CalledProcessError, FileNotFoundError):
            continue
    raise RuntimeError(
        "neither 'docker compose' nor 'docker-compose' is available"
    )


def _seed_watch(db: Session) -> Watch:
    now = datetime.datetime.now(datetime.UTC)
    user = User(
        id=uuid.uuid4(),
        email=f"smoke-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x",
        role=UserRole.USER,
    )
    watch = Watch(
        id=uuid.uuid4(),
        user_id=user.id,
        source=SourceKind.JOBTECH,
        prompt="python",
        config={},
        is_active=True,
        schedule_interval=datetime.timedelta(hours=1),
        next_run_at=now,
    )
    db.add(user)
    db.add(watch)
    db.commit()
    return watch


def run_smoke(*, manage_compose: bool = True) -> None:
    """Run the full smoke check, raising AssertionError on any failure."""
    settings = get_settings()

    if manage_compose:
        _run([*_compose_cmd(), "up", "-d", "--wait"])
    _run(["uv", "run", "alembic", "upgrade", "head"])

    engine = create_engine(settings.database_url)
    redis = make_redis(settings.redis_url)

    registry = DictSourceRegistry()
    registry.register(StaticSourcePlugin(SourceKind.JOBTECH, _RECORDS))
    deps = PipelineDeps(
        registry=registry,
        embedder=HashingEmbedder(),
        model=KeywordModelClient(keywords=("python",)),
        sink=InMemorySink(),
        cloud_available=False,
        redis_client=redis,
    )

    with Session(engine) as db:
        watch = _seed_watch(db)
        result = run_watch_core(db, watch, deps, redis)
        print(f"pipeline result: {result}")

        assert "run_id" in result, result
        assert result["items"] == 2, result

        runs = (
            db.query(PipelineRun)
            .filter(PipelineRun.watch_id == watch.id)
            .all()
        )
        assert len(runs) == 1, runs
        assert runs[0].status is RunStatus.SUCCEEDED, runs[0].status
        print(f"persisted run {runs[0].id} -> {runs[0].status.value}")

    fetch_keys = redis.keys("fetch:*")
    rate_keys = redis.keys(f"ratelimit:{watch.user_id}:*")
    assert fetch_keys, "expected a fetch-cache key in Redis"
    assert rate_keys, "expected a rate-limit key in Redis"
    print(f"redis fetch keys: {fetch_keys}")
    print(f"redis rate-limit keys: {rate_keys}")

    print("\nE2E smoke test PASSED")


def main() -> int:
    try:
        run_smoke()
    except (AssertionError, subprocess.CalledProcessError) as exc:
        print(f"\nE2E smoke test FAILED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
