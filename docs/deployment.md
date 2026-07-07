# Deployment & release runbook (ADR 0017)

How PulseGraph is packaged, released, migrated, and rolled back. The tooling
is **platform-agnostic**: one container image, a production-like Compose
stack you can run locally, and a CD workflow whose actual host rollout is a
single well-marked seam you fill in for your platform (Fly.io, Railway,
a VM running Compose, Kubernetes, …).

Everything is a **safe no-op until configured** — the pipeline runs green
out of the box and only touches a real environment once that environment's
secrets are set. This mirrors the project's local-first posture (ADR 0009).

## Topology

A managed platform runs three roles from the **same image** plus two managed
datastores; the local model runs on the project's own hardware:

| Component        | Role / image command | Notes |
|------------------|----------------------|-------|
| API              | `api`                | FastAPI under uvicorn, serves HTTP |
| Worker pool      | `worker`             | arq scheduler + cron jobs (ADR 0015) |
| Migrations       | `migrate`            | one-shot `alembic upgrade head` on deploy |
| PostgreSQL       | managed + `pgvector` | provider-hosted; connection via `DATABASE_URL` |
| Redis            | managed              | queue + rate limits + caches; `REDIS_URL` |
| Ollama           | own hardware (ADR 0002) | reached over a secured channel; `OLLAMA_BASE_URL` |

## The image

`Dockerfile` is a multi-stage build (uv resolves locked deps into a venv;
the runtime stage is a slim non-root image). A single image serves every
role — the first argument to `docker/entrypoint.sh` selects it:

```
docker run --rm <image> api       # uvicorn (default; CMD)
docker run --rm <image> worker    # arq worker pool
docker run --rm <image> migrate   # alembic upgrade head, then exit
docker run --rm <image> migrate <rev>   # upgrade to a specific revision
docker run --rm <image> alembic downgrade -1   # any ad-hoc command
```

Build once, deploy the identical digest to every environment and role.

## Environments

At least **staging** and **production**, configured as GitHub
[Environments](https://docs.github.com/actions/deployment/targeting-different-environments).
Each holds its own secrets and (for production) protection rules.

Per-environment secrets:

| Secret               | Purpose |
|----------------------|---------|
| `DATABASE_URL`       | target Postgres; migrations skip if unset |
| `DEPLOY_WEBHOOK_URL` | optional hook the default deploy seam POSTs to |
| `DEPLOY_ENABLED`     | set to force the seam on without a webhook |

The application itself also needs, at runtime on the host (via the platform's
secret manager, ADR 0009): `PULSEGRAPH_ENV` (`staging`/`production`),
a strong `JWT_SECRET_KEY` (≥32 bytes — the API and worker refuse to start
otherwise), `DATABASE_URL`, `REDIS_URL`, and optionally `OLLAMA_BASE_URL`,
`USE_CLOUD_MODEL`/`ANTHROPIC_API_KEY`, and the notification/observability
settings from `.env.example`.

## Pipeline

```
CI (ci.yml)            Deploy (deploy.yml)
lint ─ test ─ eval     build image ─ push GHCR ─ migrate ─ deploy
   └─ build            (staging auto after green CI; production on demand)
```

- **CI** (`.github/workflows/ci.yml`) is the quality gate: ruff, pytest, the
  ADR 0012 offline-eval gate, `uv build`, the e2e smoke test, and the
  dashboard lint/typecheck/build.
- **Deploy** (`.github/workflows/deploy.yml`) chains **after a green CI run
  on `master`** and:
  1. builds the image and pushes it to GHCR, tagged `sha-<commit>` + `latest`
     (uses the built-in `GITHUB_TOKEN` — no external secret needed);
  2. **deploy-staging** — runs migrations then the deploy seam against the
     `staging` environment (automatic);
  3. **deploy-production** — same, against `production`, reached **only** by a
     manual `workflow_dispatch` with `environment: production`. The
     production Environment's required-reviewers rule is the human promotion
     gate, so staging is validated before users see a release.

Both migrate and deploy steps call `scripts/deploy_release.sh`, which no-ops
with a clear log line when the environment's secrets are absent.

### Going live (wiring the deploy seam)

1. Create the `staging` and `production` GitHub Environments; add required
   reviewers to `production`.
2. Set each environment's secrets (table above).
3. Provision the host to run the `api` and `worker` roles from the image and
   inject the runtime secrets.
4. Replace the **`DEPLOY SEAM`** block in `scripts/deploy_release.sh` with
   your platform's rollout command (examples are inlined there):
   `flyctl deploy --image "$IMAGE"`, `railway up`, `kubectl set image …`, or
   `ssh $HOST 'docker-compose -f docker-compose.prod.yml pull && up -d'`.

## Migrations & rollback

Migrations are **Alembic**, applied automatically on every deploy by the
`migrate` role (`alembic upgrade head`) before api/worker roll onto the new
image. Current head: `d4f1a7c93e28`.

**Forward** (what deploy does):

```
docker run --rm -e DATABASE_URL <image> migrate         # = alembic upgrade head
```

**Rollback.** If a release is bad, roll the app back to the previous image
digest first (redeploy the prior `sha-…` tag), then, only if the new
migration is incompatible, step the schema down with the **same image tag
that introduced it** so the down-revision matches:

```
docker run --rm -e DATABASE_URL <previous-image> alembic downgrade -1
# or to a named revision:
docker run --rm -e DATABASE_URL <previous-image> alembic downgrade b7e4c1a9f2d3
```

Migrations are written to be reversible (each revision has a `downgrade()`;
up/down are verified against real Postgres before merge). Prefer
expand/contract changes so a schema step and an app step never have to be
atomic: deploy the additive migration, deploy the app that uses it, and only
drop the old column in a later release — that keeps rollback safe.

> The LangGraph checkpoint tables are created by the saver's own `setup()`
> (ADR 0001), not Alembic, so they are outside this rollback path.

## Production-like stack locally

`docker-compose.prod.yml` runs all three roles plus db + redis exactly as a
platform would — the closest reproduction of production you can stand up
locally, and what this runbook is verified against:

```
cp .env.prod.example .env.prod         # set POSTGRES_PASSWORD + a strong JWT_SECRET_KEY
docker-compose --env-file .env.prod -f docker-compose.prod.yml up --build
```

`migrate` runs to completion first; `api` and `worker` start only once it has
exited 0 and the datastores are healthy. The API is published on
`API_PORT` (default 8000).

## Health probes

- **Liveness:** `GET /health` → `200 {"status":"ok"}` (never touches
  datastores). Used by the Compose api healthcheck and suitable for a
  platform liveness probe.
- **Readiness:** `GET /health/ready` probes DB, Redis, and Ollama; returns
  `503` + `{"status":"degraded", …}` if any is down. Point the platform's
  **readiness** probe here so a node with an unreachable Ollama is pulled
  from rotation. (Locally, without Ollama, `/health/ready` is expected to
  report `degraded` while `database` and `redis` read `ok`.)
