#!/bin/bash
# Launch the OCaml half of the distributed dining philosophers demo.
#
# The OCaml REPL hosts:
#   * 2 philosopher actors (P3, P4)
#   * 3 fork actors (fork2, fork3, fork4)
#   * the web gateway on localhost:8080
#
# After the server starts, open
#   http://localhost:8080/distributed_philosophers.html
# in a browser. The page hosts the other 3 philosophers (P0, P1, P2) and
# forks 0/1, and bridges its remote sends to the OCaml gateway.

cd "$(dirname "$0")"

# Build first so edits pick up. If the build fails we fall through to the
# last-known-good binary so asset/ABCL-source edits still take effect (the
# static file routes pick files off disk at request time).
dune build 2>&1 | sed 's/^/[build] /' || true
if [ ! -x "./_build/default/src/repl_thread.exe" ]; then
  echo "[build] no repl_thread.exe — cannot launch"; exit 1;
fi

# Kill any previous REPL so port 8080 is free.
if pgrep -f repl_thread.exe > /dev/null; then
  echo "[restart] stopping existing repl_thread.exe ..."
  pkill -f repl_thread.exe
  for i in 1 2 3 4 5; do
    sleep 1
    pgrep -f repl_thread.exe > /dev/null || break
  done
  pgrep -f repl_thread.exe > /dev/null && pkill -9 -f repl_thread.exe
  sleep 1
fi

# Inline REPL script: load + compile. The browser page's "Run Dinner"
# button kicks the OCaml half (`send table.start();`) once the WebSocket
# bridge is online, so P3/P4 and the browser philosophers line up at a
# clean starting point.
cat > /tmp/run_distributed_philosophers.cmds <<'EOF'
load src/distributed_philosophers_ocaml.abcl
compile
EOF

echo "[run] launching distributed_philosophers (OCaml half)"
echo "[run] open http://localhost:8080/distributed_philosophers.html"
exec ./_build/default/src/repl_thread.exe -f /tmp/run_distributed_philosophers.cmds
