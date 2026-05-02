#!/usr/bin/env bash
# Smoke-test every .abcl program under samples/ by running it through
# the Python interpreter with a wall-clock timeout.  A run is PASS if
# (a) no Python traceback appears in the output and (b) a "[parse
# error]" was not reported.

set -u

cd "$(dirname "$0")"

PY=${PYTHON:-/usr/bin/python3}
TIMEOUT=${TIMEOUT:-5}
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

echo
echo "==== Python smoke summary ===="
echo "total: $((pass+fail))  pass: $pass  fail: $fail"
if [ "$fail" -gt 0 ]; then
  echo "---- failed ----"
  for f in "${FAILS[@]}"; do echo "  $f"; done
  exit 1
fi
