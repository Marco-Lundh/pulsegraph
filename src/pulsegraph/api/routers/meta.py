"""Liveness and readiness endpoints (ADR 0020)."""

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from pulsegraph.api.deps import get_db
from pulsegraph.api.health import (
    check_database,
    check_ollama,
    check_redis,
    summarize,
)
from pulsegraph.config import get_settings
from pulsegraph.redis_client import make_redis

router = APIRouter(tags=["meta"])


@router.get("/health")
def health() -> dict:
    """Liveness: the process is up and serving (no dependency checks)."""
    return {"status": "ok"}


@router.get("/health/ready")
def readiness(
    response: Response,
    db: Session = Depends(get_db),
) -> dict:
    """Readiness: probe every critical dependency (ADR 0020).

    Returns 503 when any check fails, so a load balancer stops routing
    to an instance that cannot actually serve requests.
    """
    settings = get_settings()
    results = [
        check_database(db),
        check_redis(make_redis(settings.redis_url)),
        check_ollama(settings.ollama_base_url),
    ]
    summary = summarize(results)
    if summary["status"] != "ok":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return summary
