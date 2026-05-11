#!/usr/bin/env sh
set -eu

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
PY="$ROOT/.venv-aipl/bin/python"

if [ ! -x "$PY" ]; then
  /opt/homebrew/bin/python3.13 -m venv "$ROOT/.venv-aipl"
fi

exec "$PY" "$ROOT/src/python-aipl/aipl_main.py" "$@"
