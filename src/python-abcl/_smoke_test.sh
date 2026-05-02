#!/usr/bin/env bash
# Smoke-test every .abcl program under samples/ by running it through
# the Python interpreter with a wall-clock timeout.  A run is PASS if
# (a) no Python traceback appears in the output and (b) a "[parse
# error]" was not reported.
#
# Pass --with-ai to also run samples-ai/ programs that call Claude.
# Those need ANTHROPIC_API_KEY in the environment and cost API tokens
# per run, so they are gated behind the flag.

set -u

cd "$(dirname "$0")"

WITH_AI=0
if [ "${1:-}" = "--with-ai" ]; then WITH_AI=1; fi

PY=${PYTHON:-/usr/bin/python3}
TIMEOUT=${TIMEOUT:-5}
AI_TIMEOUT=${AI_TIMEOUT:-90}
LOGDIR=_smoke_logs
rm -rf "$LOGDIR"
mkdir -p "$LOGDIR"

# Verify lark is importable on the chosen interpreter.
if ! "$PY" -c "import lark" 2>/dev/null; then
  echo "[FATAL] $PY cannot import 'lark'.  Install it with:"
  echo "    $PY -m pip install --user lark"
  exit 2
fi

pass=0; fail=0
declare -a FAILS
for f in samples/*.abcl; do
  [ -e "$f" ] || continue
  name=$(basename "$f" .abcl)
  log="$LOGDIR/${name}.log"
  "$PY" abcl_main.py --timeout "$TIMEOUT" "$f" >"$log" 2>&1
  rc=$?
  if grep -qE 'Traceback|^\[parse error\]|^\[FATAL\]' "$log"; then
    printf '  FAIL  %s\n' "$f"
    grep -E 'Traceback|^\[parse error\]|^\[FATAL\]' "$log" | head -2 | sed 's/^/        /'
    fail=$((fail+1))
    FAILS+=("$f")
  elif [ "$rc" -ne 0 ]; then
    printf '  FAIL  %s  (exit %d)\n' "$f" "$rc"
    fail=$((fail+1))
    FAILS+=("$f")
  else
    # Ensure something actually ran (otherwise empty output may signal
    # an actor that never produced anything).
    bytes=$(wc -c < "$log")
    if [ "$bytes" -le 1 ]; then
      printf '  FAIL  %s  (no output)\n' "$f"
      fail=$((fail+1))
      FAILS+=("$f")
    else
      printf '  PASS  %s\n' "$f"
      pass=$((pass+1))
    fi
  fi
done

ai_pass=0; ai_fail=0; ai_skip=0
if [ "$WITH_AI" = "1" ]; then
  echo
  echo "[AI samples]"
  if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
    echo "  SKIP samples-ai/: ANTHROPIC_API_KEY is not set"
    ai_skip=1
  elif ! "$PY" -c "import anthropic" 2>/dev/null; then
    echo "  SKIP samples-ai/: anthropic SDK not installed ($PY -m pip install --user anthropic)"
    ai_skip=1
  else
    for f in samples-ai/*.abcl; do
      [ -e "$f" ] || continue
      name=$(basename "$f" .abcl)
      log="$LOGDIR/${name}.log"
      "$PY" abcl_main.py --timeout "$AI_TIMEOUT" "$f" >"$log" 2>&1
      rc=$?
      if grep -qE 'Traceback|^\[parse error\]|^\[FATAL\]' "$log" || [ "$rc" -ne 0 ]; then
        printf '  FAIL  %s\n' "$f"
        grep -E 'Traceback|^\[parse error\]|^\[FATAL\]' "$log" | head -2 | sed 's/^/        /'
        ai_fail=$((ai_fail+1))
      else
        printf '  PASS  %s\n' "$f"
        ai_pass=$((ai_pass+1))
      fi
    done
  fi
fi

echo
echo "==== Python smoke summary ===="
echo "total: $((pass+fail))  pass: $pass  fail: $fail"
if [ "$WITH_AI" = "1" ]; then
  if [ "$ai_skip" = "1" ]; then
    echo "ai: SKIPPED"
  else
    echo "ai: total: $((ai_pass+ai_fail))  pass: $ai_pass  fail: $ai_fail"
  fi
fi
total_fail=$((fail + ai_fail))
if [ "$total_fail" -gt 0 ]; then
  echo "---- failed ----"
  for f in "${FAILS[@]}"; do echo "  $f"; done
  exit 1
fi
