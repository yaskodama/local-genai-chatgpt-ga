#!/usr/bin/env bash
# docker/cross/run-compose.sh
#
# docker-compose-based driver for the cross-language demo.  Equivalent
# to run-cross.sh but uses `docker compose` orchestration so service
# dependencies (healthchecks, depends_on) are honored.
#
# Usage:
#   bash docker/cross/run-compose.sh build   # build images only
#   bash docker/cross/run-compose.sh up      # start servers + run drivers
#   bash docker/cross/run-compose.sh down    # tear everything down
#   bash docker/cross/run-compose.sh         # build + up

set -u
cd "$(dirname "$0")/../.."

COMPOSE=( docker compose -f docker/cross/docker-compose.yml )

build() {
  "${COMPOSE[@]}" build pyserver ocserver
}

up() {
  echo "[run-compose] starting servers (detached) ..."
  "${COMPOSE[@]}" up -d pyserver ocserver
  echo "[run-compose] waiting for pyserver healthcheck ..."
  for _ in $(seq 1 30); do
    s=$(docker inspect -f '{{.State.Health.Status}}' pyserver 2>/dev/null || echo none)
    [ "$s" = "healthy" ] && break
    sleep 1
  done
  # No healthcheck for ocserver (no curl/python in the runtime image);
  # give the gateway thread a moment to bind.
  sleep 2

  echo
  echo "==================== Python driver ===================="
  "${COMPOSE[@]}" run --rm pydriver

  echo
  echo "==================== OCaml driver  ===================="
  "${COMPOSE[@]}" run --rm ocdriver

  echo
  echo "==================== Server logs (tail) ===================="
  echo "--- pyserver ---"
  "${COMPOSE[@]}" logs --tail 20 pyserver 2>&1 || true
  echo "--- ocserver ---"
  "${COMPOSE[@]}" logs --tail 20 ocserver 2>&1 || true
}

down() {
  "${COMPOSE[@]}" down --remove-orphans
}

cmd="${1:-all}"
case "$cmd" in
  build) build ;;
  up)    up ;;
  down)  down ;;
  all)   build && up ;;
  *)
    echo "usage: $0 [build|up|down]" >&2
    exit 2
    ;;
esac
