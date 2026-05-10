#!/usr/bin/env bash
# Wrapper: drive the OCaml REPL with `load <abcl>; compile` and keep
# the process alive so that web_listen()'s background thread can serve
# requests.  Without `keep-alive`, the script-execution path returns
# and the REPL would `exit Thread.Exit` on EOF.
set -u

ABCL="${1:-/app/samples-remote/ocaml_server.abcl}"

# Place the REPL drive script in the same directory as the .abcl so
# that the REPL's `cwd ->` chdir lands where the source lives, and a
# bare `load <basename>` resolves correctly.
SCRIPT_DIR=$(dirname "$ABCL")
SCRIPT_NAME=$(basename "$ABCL")
SCRIPT="$SCRIPT_DIR/_aipl_run.bat"
printf 'load %s\ncompile\n' "$SCRIPT_NAME" > "$SCRIPT"

# Keep-alive policy:
#   AIPL_KEEPALIVE=1 (default for servers) — pipe an infinite no-op
#     stream into the REPL so the gateway thread keeps serving until
#     the container is killed.  In `docker run -d` mode Docker
#     attaches /dev/null to stdin which the REPL otherwise treats
#     as EOF and exits.
#   AIPL_KEEPALIVE=0 (drivers) — let the REPL hit EOF after the
#     script finishes so the container exits cleanly.
KEEPALIVE="${AIPL_KEEPALIVE:-1}"

if [ "$KEEPALIVE" = "0" ]; then
  # Driver mode: actor threads in the OCaml runtime are infinite
  # message-pump loops, so the process won't exit on its own once
  # the script's main work is done.  Tail the runtime output, fire
  # SIGTERM at the REPL when we see the marker that the script
  # finished and the driver actor printed "=== done ===".
  TMP_LOG=$(mktemp)
  aipl-ocaml -f "$SCRIPT" < /dev/null > "$TMP_LOG" 2>&1 &
  REPL_PID=$!

  (
    while kill -0 "$REPL_PID" 2>/dev/null; do
      if grep -q "=== done ===" "$TMP_LOG" 2>/dev/null; then
        sleep 1   # let any final stdout flush
        kill -TERM "$REPL_PID" 2>/dev/null
        break
      fi
      sleep 0.3
    done
  ) &

  wait "$REPL_PID" 2>/dev/null
  cat "$TMP_LOG"
  exit 0
else
  exec sh -c "while true; do sleep 60; done | aipl-ocaml -f \"$SCRIPT\""
fi
