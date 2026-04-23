#!/bin/bash
# Restart the ABCL/c+ REPL with the viz_philosophers demo loaded.
# Kills any currently running instance so port 8080 is free.
cd "$(dirname "$0")"

if pgrep -f repl_thread.exe > /dev/null; then
  echo "[restart] stopping existing repl_thread.exe ..."
  pkill -f repl_thread.exe
  # Wait up to ~5 seconds for the process to exit and the port to be released
  for i in 1 2 3 4 5; do
    sleep 1
    pgrep -f repl_thread.exe > /dev/null || break
  done
  if pgrep -f repl_thread.exe > /dev/null; then
    echo "[restart] still running — sending SIGKILL"
    pkill -9 -f repl_thread.exe
    sleep 1
  fi
fi

echo "[restart] launching viz_philosophers ..."
exec ./_build/default/src/repl_thread.exe -f abclc/run_viz_philosophers.bat
