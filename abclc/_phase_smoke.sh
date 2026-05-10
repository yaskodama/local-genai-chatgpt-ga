#!/usr/bin/env bash
# Smoke-test the OCaml-side Phase 11-15 samples.
# Drives repl_thread.exe with `load <file>; compile` for each sample,
# kills after a timeout, and inspects the captured output for the
# expected per-phase tag.

set -u
cd "$(dirname "$0")"

REPL=../_build/default/src/repl_thread.exe
TIMEOUT=${TIMEOUT:-6}
LOG=_smoke_logs/_phase
mkdir -p _smoke_logs

declare -a SAMPLES=(
  "Phase11_TypedCounter.abcl"
  "Phase12_EffectsLog.abcl"
  "Phase13_Channels.abcl"
  "Phase14_Linear.abcl"
  "Phase15_Owned.abcl"
)
declare -a EXPECTS=(
  "Phase 11 — typed calc"
  "Phase 12 — effect-segregated"
  "Phase 13 — CSP-style channel"
  "Phase 14 — linear handle"
  "Phase 15 — encapsulated bank account"
)

pass=0; fail=0
for i in "${!SAMPLES[@]}"; do
  abcl="${SAMPLES[$i]}"
  expect="${EXPECTS[$i]}"
  log="${LOG}_${abcl%.abcl}.log"

  printf 'load %s\ncompile\n' "$abcl" > _run.bat
  "$REPL" -f "$PWD/_run.bat" > "$log" 2>&1 &
  pid=$!
  ( sleep "$TIMEOUT" && kill -TERM "$pid" 2>/dev/null ) &
  kpid=$!
  wait "$pid" 2>/dev/null
  kill "$kpid" 2>/dev/null
  wait "$kpid" 2>/dev/null

  if grep -qE '^\[Type error\]|^\[Parse error\]|^\[Compile error\]|^\[Abort\]' "$log"; then
    fail=$((fail+1))
    printf '  FAIL  %s  (compile/type)\n' "$abcl"
    grep -E '^\[Type error\]|^\[Parse error\]|^\[Abort\]' "$log" | head -2 | sed 's/^/        /'
  elif grep -qF "$expect" "$log"; then
    pass=$((pass+1))
    printf '  PASS  %s\n' "$abcl"
  else
    fail=$((fail+1))
    printf '  FAIL  %s  (missing expected output)\n' "$abcl"
    printf '        expected: %s\n' "$expect"
  fi
done

rm -f _run.bat
echo
echo "phase samples: $pass pass / $fail fail"
exit "$fail"
