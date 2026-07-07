#!/usr/bin/env bash
# Platform-agnostic release seam for the deploy pipeline (ADR 0017).
#
# Two subcommands, run in order by .github/workflows/deploy.yml against one
# target environment:
#
#   migrate  Apply Alembic migrations by running the freshly built image's
#            one-shot `migrate` role against $DATABASE_URL.
#   deploy   Roll the running api + worker services onto $IMAGE.
#
# Both are gated on the environment's secrets being present, so the pipeline
# is a safe no-op until an operator wires a real target. To go live, set the
# environment secrets (DATABASE_URL, and either DEPLOY_WEBHOOK_URL or
# DEPLOY_ENABLED) and replace the marked DEPLOY SEAM below with your host's
# rollout command. See docs/deployment.md.
#
# Expected environment:
#   IMAGE               fully-qualified image ref just built (required)
#   DEPLOY_ENV          "staging" | "production" (informational)
#   DATABASE_URL        target database; migrations skip if empty
#   DEPLOY_WEBHOOK_URL  optional deploy hook the default seam POSTs to
#   DEPLOY_ENABLED      set to force the seam on without a webhook
set -euo pipefail

cmd="${1:?usage: deploy_release.sh <migrate|deploy>}"
env_name="${DEPLOY_ENV:-this environment}"

log() { printf '  %s\n' "$*"; }

case "$cmd" in
  migrate)
    if [ -z "${DATABASE_URL:-}" ]; then
      log "DATABASE_URL not set for ${env_name}"
      log "-> skipping migrations (no target database configured yet)."
      exit 0
    fi
    log "Applying migrations to ${env_name} with ${IMAGE:?IMAGE required}"
    docker run --rm \
      -e DATABASE_URL \
      -e PULSEGRAPH_ENV="${DEPLOY_ENV:-production}" \
      "${IMAGE}" migrate
    ;;

  deploy)
    if [ -z "${DEPLOY_WEBHOOK_URL:-}" ] && [ -z "${DEPLOY_ENABLED:-}" ]; then
      log "No deploy target wired for ${env_name}"
      log "-> would roll api + worker onto ${IMAGE:-<image>}."
      log "   Configure the environment secrets and fill in the DEPLOY SEAM"
      log "   in scripts/deploy_release.sh to go live."
      exit 0
    fi

    # === DEPLOY SEAM =========================================================
    # Replace this block with your platform's rollout command. It must pull
    # ${IMAGE} and restart the api + worker services. Examples:
    #   flyctl deploy --image "${IMAGE}" --app "${FLY_APP}"
    #   railway up --service api --image "${IMAGE}"
    #   ssh "${DEPLOY_HOST}" "cd /srv/pulsegraph && IMAGE_TAG='${IMAGE}' \
    #     docker-compose -f docker-compose.prod.yml pull && \
    #     docker-compose -f docker-compose.prod.yml up -d"
    if [ -n "${DEPLOY_WEBHOOK_URL:-}" ]; then
      log "Notifying deploy webhook for ${env_name} -> ${IMAGE}"
      curl -fsS -X POST "${DEPLOY_WEBHOOK_URL}" \
        -H 'content-type: application/json' \
        -d "{\"environment\":\"${DEPLOY_ENV:-production}\",\"image\":\"${IMAGE:-}\"}"
    else
      log "DEPLOY_ENABLED is set but the deploy seam is not implemented."
      log "Edit scripts/deploy_release.sh to add your rollout command."
      exit 1
    fi
    # =========================================================================
    ;;

  *)
    echo "unknown subcommand: ${cmd} (expected migrate|deploy)" >&2
    exit 2
    ;;
esac
