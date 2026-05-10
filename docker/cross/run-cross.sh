#!/usr/bin/env bash
# docker/cross/run-cross.sh
#
# Spins up the cross-language remote-actor demo without docker compose.
# Builds two images (Python and OCaml AIPL), creates a docker network,
# starts the Python server and OCaml server in the background, and
# then runs each driver in turn against both servers.
#
# Usage:
#   bash docker/cross/run-cross.sh build      # build images only
#   bash docker/cross/run-cross.sh up         # start servers + run drivers
#   bash docker/cross/run-cross.sh down       # tear everything down
#   bash docker/cross/run-cross.sh            # build + up

set -u
cd "$(dirname "$0")/../.."

NET=aipl-net
PY_IMG=aipl-python:cross
OC_IMG=aipl-ocaml:cross
PY_SRV=pyserver
OC_SRV=ocserver

ensure_net() {
  if ! docker network inspect "$NET" >/dev/null 2>&1; then
    docker network create "$NET" >/dev/null
    echo "[run-cross] created docker network $NET"
  fi
}

remove_if_running() {
  local name="$1"
  if docker ps -a --format '{{.Names}}' | grep -qx "$name"; then
    docker rm -f "$name" >/dev/null
  fi
}

build() {
  echo "[run-cross] building $PY_IMG ..."
  docker build -f docker/cross/Dockerfile.python -t "$PY_IMG" .
  echo "[run-cross] building $OC_IMG (this may take several minutes the first time) ..."
  docker build -f docker/cross/Dockerfile.ocaml -t "$OC_IMG" .
}

up() {
  ensure_net
  remove_if_running "$PY_SRV"
  remove_if_running "$OC_SRV"

  echo "[run-cross] starting $PY_SRV ..."
  docker run -d --rm --name "$PY_SRV" --network "$NET" \
    "$PY_IMG" /app/samples-remote/python_server.abcl >/dev/null
  echo "[run-cross] starting $OC_SRV ..."
  docker run -d --rm --name "$OC_SRV" --network "$NET" \
    "$OC_IMG" /app/samples-remote/ocaml_server.abcl >/dev/null

  # Give the gateways a moment to bind their listeners.
  echo "[run-cross] waiting 4s for both gateways to come up ..."
  sleep 4

  echo
  echo "==================== Python driver ===================="
  docker run --rm --network "$NET" \
    "$PY_IMG" /app/samples-remote/python_driver.abcl

  echo
  echo "==================== OCaml driver  ===================="
  docker run --rm --network "$NET" \
    "$OC_IMG" /app/samples-remote/ocaml_driver.abcl

  echo
  echo "==================== Server logs (tail) ===================="
  echo "--- $PY_SRV ---"
  docker logs --tail 30 "$PY_SRV" 2>&1 || true
  echo "--- $OC_SRV ---"
  docker logs --tail 30 "$OC_SRV" 2>&1 || true
}

down() {
  remove_if_running "$PY_SRV"
  remove_if_running "$OC_SRV"
  if docker network inspect "$NET" >/dev/null 2>&1; then
    docker network rm "$NET" >/dev/null && echo "[run-cross] removed network $NET"
  fi
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
