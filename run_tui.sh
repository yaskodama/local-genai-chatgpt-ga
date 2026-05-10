#!/bin/bash
# Native OCaml terminal IDE for AIPL.
#
# Starts repl_thread.exe in the background (with the web gateway so the
# TUI can drive it over HTTP) and then launches tui_ide.exe in the
# foreground. The TUI paints a multi-pane terminal UI:
#
#   * top-left:     Output (log, replies, REPL output)
#   * bottom-left:  Source code of the selected actor
#   * right:        Current actors (refreshed every 2 s)
#   * bottom bar:   Command input line
#
# Keys:
#   Enter       submit command
#   Backspace   delete char
#   ←/→         move cursor
#   ↑/↓         history
#   PgUp/PgDn   scroll output pane
#   Ctrl-D      quit

cd "$(dirname "$0")"

PORT=8080
LOG="/tmp/abcl_tui_repl.log"

# Build first. Fall through on failure if an old binary is still usable.
dune build 2>&1 | sed 's/^/[build] /' || true
if [ ! -x "./_build/default/src/repl_thread.exe" ] \
   || [ ! -x "./_build/default/src/tui_ide.exe" ]; then
  echo "[build] binaries missing — cannot launch"; exit 1;
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

# Start REPL server in background. stdin is /dev/null so the REPL's
# read_line exits cleanly, but the web gateway thread keeps running.
echo "[run] starting repl_thread.exe (log: $LOG)"
./_build/default/src/repl_thread.exe -f src/ide_boot.bat \
  < /dev/null > "$LOG" 2>&1 &
REPL_PID=$!

# Ensure we clean the REPL up when the TUI exits.
cleanup() {
  if kill -0 "$REPL_PID" 2>/dev/null; then
    kill "$REPL_PID" 2>/dev/null
  fi
}
trap cleanup EXIT

# Wait for the web gateway to accept connections.
ready=0
for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20; do
  if curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:${PORT}/api/actors" \
       2>/dev/null | grep -q "^200$"; then
    ready=1; break
  fi
  sleep 0.25
done
if [ "$ready" != "1" ]; then
  echo "[run] gave up waiting for REPL to come up; see $LOG"
  exit 1
fi

echo "[run] launching tui_ide.exe"
./_build/default/src/tui_ide.exe -p "$PORT"
