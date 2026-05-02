#!/bin/bash
# Launch the OCaml ABCL/c+ REPL with the integrated web IDE enabled.
#
# The IDE provides four panes in the browser:
#   * Command input (REPL commands or ABCL source)
#   * Output
#   * Current actors list
#   * Source code / AST display
#
# After start-up, open:
#   http://localhost:8080/ide

cd "$(dirname "$0")"

# Port is defined in src/ide_boot.abcl (web_listen(...)). Edit that file if
# you want a different port.
PORT=8080

# Build first so source edits pick up. On a build failure we still attempt to
# launch the last known-good binary so asset-only edits (ide.html/ide.js)
# still take effect — the static file routes read files off disk on request.
dune build 2>&1 | sed 's/^/[build] /' || true
if [ ! -x "./_build/default/src/repl_thread.exe" ]; then
  echo "[build] no repl_thread.exe — cannot launch"; exit 1;
fi

# Stop any previously running REPL so the port is free.
if pgrep -f repl_thread.exe > /dev/null; then
  echo "[restart] stopping existing repl_thread.exe ..."
  pkill -f repl_thread.exe
  for _ in 1 2 3 4 5; do
    sleep 1
    pgrep -f repl_thread.exe > /dev/null || break
  done
  pgrep -f repl_thread.exe > /dev/null && pkill -9 -f repl_thread.exe
  sleep 1
fi

# REPL-level script: src/ide_boot.bat contains `load ide_boot.abcl` +
# `compile`, and the REPL's `script` command now chdirs into the .bat's
# directory while it runs — so those relative paths resolve from src/.
echo "[run] launching ABCL/c+ IDE"
echo "[run] open http://localhost:${PORT}/ide  (port is fixed in src/ide_boot.abcl)"
exec ./_build/default/src/repl_thread.exe -f src/ide_boot.bat
