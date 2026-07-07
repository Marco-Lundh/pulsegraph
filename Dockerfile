# syntax=docker/dockerfile:1
#
# Production image for PulseGraph (ADR 0017). A single image serves every
# runtime role — API, worker, or a one-shot migration — chosen by the first
# argument to the entrypoint (see docker/entrypoint.sh). Build once, deploy
# the identical digest to every environment and every role.

# --- Builder: resolve locked dependencies into a self-contained venv --------
# Both stages start from the same python:3.12-slim base and uv is told never
# to download its own interpreter (UV_PYTHON_DOWNLOADS=0). That keeps the
# venv's interpreter path identical across stages, so the copied /app/.venv
# still works in the runtime image.
FROM python:3.12-slim-bookworm AS builder

COPY --from=ghcr.io/astral-sh/uv:0.10 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app

# Install third-party dependencies first, from the lockfile only, so this
# layer stays cached until pyproject.toml / uv.lock actually change. Dev
# extras are excluded — production carries no test/lint tooling.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-editable

# Then install the project itself against the copied source.
COPY src ./src
COPY README.md ./
RUN uv sync --frozen --no-editable

# --- Runtime: slim image carrying just the venv and the deploy surface ------
FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

# Run as an unprivileged user (ADR 0009 hardening); never as root.
RUN groupadd --system --gid 1001 pulsegraph \
    && useradd --system --uid 1001 --gid pulsegraph pulsegraph

WORKDIR /app

# The resolved environment from the builder …
COPY --from=builder --chown=pulsegraph:pulsegraph /app/.venv /app/.venv
# … plus everything Alembic needs to run migrations at deploy time. The
# migrations tree lives outside the wheel, so it is copied explicitly.
COPY --chown=pulsegraph:pulsegraph migrations ./migrations
COPY --chown=pulsegraph:pulsegraph alembic.ini ./alembic.ini
COPY --chown=pulsegraph:pulsegraph docker/entrypoint.sh \
    /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

USER pulsegraph

EXPOSE 8000

# No image-level HEALTHCHECK: this image runs three roles and only `api`
# serves HTTP. Health probes are defined per role by the orchestrator
# (see docker-compose.prod.yml and docs/deployment.md).
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["api"]
