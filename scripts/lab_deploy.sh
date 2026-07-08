#!/usr/bin/env bash
# Offline deploy lab for PulseGraph (ADR 0017 experimentation).
#
# Exercises the real deploy mechanics — build -> push to a registry ->
# migrate -> roll api+worker onto the image -> rollback -> schema downgrade —
# entirely offline, using the local Docker registry on :5000 as a stand-in
# for GHCR. No cloud and no secrets beyond a locally generated JWT key.
#
# Usage:
#   scripts/lab_deploy.sh build [tag]      build the image + push to localhost:5000
#   scripts/lab_deploy.sh deploy [tag]     pull tag, migrate, roll api+worker onto it
#   scripts/lab_deploy.sh seed             load demo + admin users, watches, runs
#   scripts/lab_deploy.sh rollback         redeploy the previously deployed tag
#   scripts/lab_deploy.sh downgrade <rev>  roll the SCHEMA back (alembic downgrade)
#   scripts/lab_deploy.sh status           show the lab stack + tags + registry
#   scripts/lab_deploy.sh logs [service]   follow logs
#   scripts/lab_deploy.sh down [--wipe]    stop the lab (--wipe also drops the volume)
#
# `build` then `deploy` model one release; run them again with a new tag to
# roll forward, then `rollback` to go back. See docs/deployment.md.
set -euo pipefail

cd "$(dirname "$0")/.."

REGISTRY="localhost:5000"
IMAGE_REPO="${REGISTRY}/pulsegraph"
PROJECT="pulsegraph_lab"
ENV_FILE=".env.lab"
STATE_FILE=".lab-state"
COMPOSE=(docker-compose -p "$PROJECT" --env-file "$ENV_FILE"
         -f docker-compose.prod.yml -f docker-compose.lab.yml)

info()  { printf '\033[34m==>\033[0m %s\n' "$*"; }
ok()    { printf '\033[32m✓\033[0m %s\n' "$*"; }
die()   { printf '\033[31merror:\033[0m %s\n' "$*" >&2; exit 1; }

ensure_registry() {
  docker ps --format '{{.Ports}}' | grep -q '5000->5000' || die \
    "no local registry on :5000. Start one with:
       docker run -d -p 5000:5000 --restart always --name registry registry:2"
}

ensure_env() {
  [ -f "$ENV_FILE" ] && return
  info "Generating $ENV_FILE (gitignored) with a strong, stable JWT key…"
  python -c "import secrets; \
print('PULSEGRAPH_ENV=staging'); \
print('POSTGRES_PASSWORD='+secrets.token_hex(16)); \
print('JWT_SECRET_KEY='+secrets.token_urlsafe(48)); \
print('API_PORT=8100')" > "$ENV_FILE"
}

default_tag() { git rev-parse --short HEAD 2>/dev/null || echo manual; }
get_port() {
  local p
  p="$(grep -E '^API_PORT=' "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2)"
  echo "${p:-8100}"
}
save_state() { printf 'LAB_CURRENT=%s\nLAB_PREVIOUS=%s\n' "$1" "$2" >"$STATE_FILE"; }
load_state() {
  # Parse, don't source: a hand-edited state file must not run as code.
  LAB_CURRENT=""; LAB_PREVIOUS=""
  if [ -f "$STATE_FILE" ]; then
    LAB_CURRENT="$(sed -n 's/^LAB_CURRENT=//p' "$STATE_FILE" | head -1)"
    LAB_PREVIOUS="$(sed -n 's/^LAB_PREVIOUS=//p' "$STATE_FILE" | head -1)"
  fi
  return 0
}

# Every compose invocation interpolates the lab override's ${LAB_TAG:?...},
# not just `up`. Commands that don't deploy a specific tag (status/logs/down)
# still need *a* value; the tag is irrelevant there since containers match on
# project name. Deploy/seed/downgrade export the real tag themselves.
export_placeholder_tag() {
  load_state
  export LAB_TAG="${LAB_CURRENT:-latest}"
}

wait_healthy() {
  local port i
  port="$(get_port)"
  info "Waiting for the API to become healthy on :${port}…"
  for i in $(seq 1 30); do
    if curl -fsS "http://localhost:${port}/health" >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done
  die "API did not become healthy in time — check: scripts/lab_deploy.sh logs api"
}

cmd_build() {
  ensure_registry
  local tag="${1:-$(default_tag)}"
  info "Building ${IMAGE_REPO}:${tag}…"
  docker build -t "${IMAGE_REPO}:${tag}" .
  info "Pushing to ${REGISTRY}…"
  docker push "${IMAGE_REPO}:${tag}"
  ok "Pushed ${IMAGE_REPO}:${tag}. Deploy it: scripts/lab_deploy.sh deploy ${tag}"
}

cmd_deploy() {
  ensure_registry; ensure_env
  local tag="${1:-$(default_tag)}"
  info "Pulling ${IMAGE_REPO}:${tag} from the registry…"
  docker pull "${IMAGE_REPO}:${tag}" >/dev/null 2>&1 || die \
    "tag '${tag}' is not in the registry — build it first: scripts/lab_deploy.sh build ${tag}"
  load_state
  local prev="${LAB_CURRENT:-}"
  export LAB_TAG="$tag"
  info "Rolling the lab stack onto ${tag} (migrate → api + worker)…"
  "${COMPOSE[@]}" up -d --no-build
  save_state "$tag" "$prev"
  wait_healthy
  ok "Deployed ${tag} on http://localhost:$(get_port)/health  (previous: ${prev:-none})"
}

cmd_seed() {
  ensure_env; load_state
  export LAB_TAG="${LAB_CURRENT:-$(default_tag)}"
  info "Seeding demo + admin users, watches, and a week of runs…"
  # Runs the seed module inside the lab network (reaches db:5432); the image
  # entrypoint execs any non-role command verbatim. Idempotent.
  "${COMPOSE[@]}" run --rm migrate python -m pulsegraph.seed
  ok "Seeded. Logins — user: demo@pulsegraph.dev / demo1234 · admin: admin@pulsegraph.dev / admin1234"
}

cmd_rollback() {
  load_state
  [ -n "${LAB_PREVIOUS:-}" ] || die "no previous deploy recorded to roll back to."
  info "Rolling back to ${LAB_PREVIOUS} (current is ${LAB_CURRENT})…"
  cmd_deploy "$LAB_PREVIOUS"
}

cmd_downgrade() {
  local rev="${1:?usage: lab_deploy.sh downgrade <revision>  (e.g. -1 or a revision id)}"
  ensure_env; load_state
  export LAB_TAG="${LAB_CURRENT:-$(default_tag)}"
  info "Rolling the SCHEMA back: alembic downgrade ${rev}…"
  "${COMPOSE[@]}" run --rm migrate alembic downgrade "$rev"
  ok "Schema downgraded to ${rev}. (App image unchanged — use 'rollback' for that.)"
}

cmd_status() {
  export_placeholder_tag
  info "Lab tags:"
  printf '    current : %s\n    previous: %s\n' \
    "${LAB_CURRENT:-none}" "${LAB_PREVIOUS:-none}"
  info "Running containers:"
  "${COMPOSE[@]}" ps 2>/dev/null || true
  info "Registry catalog (${REGISTRY}):"
  curl -fsS "http://${REGISTRY}/v2/_catalog" 2>/dev/null && echo \
    || echo "    (registry unreachable)"
  info "API health:"
  curl -fsS "http://localhost:$(get_port)/health" 2>/dev/null && echo \
    || echo "    (api not responding)"
}

cmd_logs() {
  export_placeholder_tag
  if [ "$#" -gt 0 ]; then "${COMPOSE[@]}" logs -f "$1"; else "${COMPOSE[@]}" logs -f; fi
}

cmd_down() {
  export_placeholder_tag
  if [ "${1:-}" = "--wipe" ]; then
    info "Tearing down the lab stack AND its volume…"
    "${COMPOSE[@]}" down -v
    rm -f "$STATE_FILE"
  else
    info "Stopping the lab stack (volume kept; use --wipe to drop it)…"
    "${COMPOSE[@]}" down
  fi
}

usage() { grep '^#' "$0" | sed '1d;s/^# \{0,1\}//'; }

case "${1:-help}" in
  build)     shift; cmd_build "$@" ;;
  deploy)    shift; cmd_deploy "$@" ;;
  seed)      cmd_seed ;;
  rollback)  shift; cmd_rollback ;;
  downgrade) shift; cmd_downgrade "$@" ;;
  status)    cmd_status ;;
  logs)      shift; cmd_logs "$@" ;;
  down)      shift; cmd_down "$@" ;;
  help | -h | --help) usage ;;
  *) die "unknown command: ${1}  (try: scripts/lab_deploy.sh help)" ;;
esac
