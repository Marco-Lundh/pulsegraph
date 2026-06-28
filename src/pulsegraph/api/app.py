"""FastAPI application factory."""

from fastapi import FastAPI

from pulsegraph.api.routers import (
    admin,
    auth,
    meta,
    notifications,
    runs,
    watches,
)


def create_app() -> FastAPI:
    app = FastAPI(
        title="PulseGraph",
        description="Multi-tenant agent-orchestration API",
        version="0.1.0",
    )

    app.include_router(meta.router)
    app.include_router(auth.router)
    app.include_router(watches.router)
    app.include_router(runs.router)
    app.include_router(notifications.router)
    app.include_router(admin.router)

    return app


app = create_app()
