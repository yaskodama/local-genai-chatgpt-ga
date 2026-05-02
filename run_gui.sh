#!/bin/bash
# Native GUI version of the ABCL/c+ integrated environment.
#
# Opens an SDL window with four panes drawn using a built-in 8x8 bitmap
# font:
#   * Output pane            — stdout/stderr from the running interpreter
#   * Source pane            — selected actor's source (pprint)
#   * Actors pane            — current actor table, auto-refreshed
#   * Command input line     — type commands, Enter to submit
#
# Runs entirely in-process: no HTTP, no localhost:8080. Commands are
# processed directly against abcllib.
#
# Keys:
#   Enter          submit command
#   Backspace      erase char
#   ←/→            move cursor
#   ↑/↓            history
#   Tab            cycle selected actor
#   PgUp/PgDn      scroll Output
#   F1             help
#   F2             compile
#   F5             refresh
#   F10 / Esc Esc  quit

cd "$(dirname "$0")"

# Stop any previously running REPL/TUI/GUI so SDL/terminal state is clean.
pgrep -f repl_thread.exe > /dev/null && pkill -f repl_thread.exe
pgrep -f tui_ide.exe     > /dev/null && pkill -f tui_ide.exe
pgrep -f gui_ide.exe     > /dev/null && pkill -f gui_ide.exe
sleep 0.5

# Build first. Fall through on failure to attempt launching last-known-good.
dune build 2>&1 | sed 's/^/[build] /' || true
if [ ! -x "./_build/default/src/gui_ide.exe" ]; then
  echo "[build] gui_ide.exe missing — cannot launch"; exit 1;
fi

echo "[run] launching ABCL/c+ GUI IDE (SDL)"
exec ./_build/default/src/gui_ide.exe
