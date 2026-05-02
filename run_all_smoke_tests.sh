#!/usr/bin/env bash
# Run every smoke test in the project and report a single summary.
#
#   1. abclc/_smoke_test.sh   -> OCaml REPL + abcl2c (+ cc/SDL2 for Gui variants)
#   2. src/browser-abcl/_smoke_test.sh [--dynamic]
#                             -> JS syntax + parser
#                                (and headless Chrome run when --dynamic)
#
# Pass --dynamic to enable the headless-browser phase.  Without it,
# JS Phase 3 is skipped and the script needs neither Chrome nor
# puppeteer-core.

set -u

cd "$(dirname "$0")"

DYNAMIC_FLAG=""
if [ "${1:-}" = "--dynamic" ]; then DYNAMIC_FLAG="--dynamic"; fi

# Make sure the OCaml binaries exist.
if [ ! -x _build/default/src/repl_thread.exe ] || [ ! -x _build/default/src/abcl2c.exe ]; then
  echo "[build] dune build"
  dune build || { echo "[FATAL] dune build failed"; exit 1; }
fi

echo "============================================================"
echo " 1/2  ABCL samples (abclc/_smoke_test.sh)"
echo "============================================================"
abclc_out=$(./abclc/_smoke_test.sh 2>&1)
echo "$abclc_out"
abclc_summary=$(echo "$abclc_out" | grep '^==== summary ====' -A 1 | tail -1)

echo
echo "============================================================"
echo " 2/2  browser-abcl JS (src/browser-abcl/_smoke_test.sh ${DYNAMIC_FLAG})"
echo "============================================================"
js_out=$(./src/browser-abcl/_smoke_test.sh $DYNAMIC_FLAG 2>&1)
echo "$js_out"
js_summary=$(echo "$js_out" | sed -n '/^==== JS smoke summary ====/,$p' | tail -n +2)

echo
echo "============================================================"
echo " Overall summary"
echo "============================================================"
echo "ABCL: ${abclc_summary}"
echo "JS:"
echo "$js_summary" | sed 's/^/   /'

# Exit non-zero if any phase had failures.
abclc_fail=$(echo "$abclc_summary" | sed -nE 's/.*fail: ([0-9]+).*/\1/p')
js_total_fail=$(echo "$js_out" | sed -nE 's/.*fail=([0-9]+).*/\1/p' | awk '{s+=$1} END {print s+0}')
total=$(( ${abclc_fail:-0} + ${js_total_fail:-0} ))
if [ "$total" -ne 0 ]; then
  echo
  echo "FAILED: $total test(s)"
  exit 1
fi
echo
echo "All smoke tests passed."
