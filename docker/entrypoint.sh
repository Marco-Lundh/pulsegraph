#!/bin/sh
# Container entrypoint for PulseGraph (ADR 0017).
#
# One image serves every runtime role; the first argument selects it:
#   api      -> the FastAPI app under uvicorn (default)
#   worker   -> the arq scheduler/worker pool (ADR 0015)
#   migrate  -> apply Alembic migrations, then exit (one-shot, run on deploy).
#              An optional target revision follows, e.g. `migrate head`
#              (default) or `migrate <rev>` to upgrade to a specific revision.
# `migrate` only ever upgrades. Anything else is exec'd verbatim, so ad-hoc
# commands still work — including rollback, e.g.
#   docker run <image> alembic downgrade -1
set -eu

role="${1:-api}"
if [ "$#" -gt 0 ]; then
  shift
fi

case "$role" in
  api)
    set -- uvicorn pulsegraph.api.app:app \
      --host 0.0.0.0 --port "${PORT:-8000}"
    # Only trust forwarded headers when the operator has named the proxy
    # ranges; trusting everything would let clients spoof X-Forwarded-For
    # and defeat the per-IP auth rate limit (ADR 0021).
    if [ -n "${FORWARDED_ALLOW_IPS:-}" ]; then
      set -- "$@" --proxy-headers \
        --forwarded-allow-ips "${FORWARDED_ALLOW_IPS}"
    fi
    exec "$@"
    ;;
  worker)
    exec arq pulsegraph.worker.arq_settings.WorkerSettings
    ;;
  migrate)
    exec alembic upgrade "${1:-head}"
    ;;
  *)
    exec "$role" "$@"
    ;;
esac
