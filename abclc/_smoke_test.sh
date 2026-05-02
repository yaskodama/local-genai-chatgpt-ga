#!/usr/bin/env bash
# Smoke-test all .abcl samples under abclc/ via the REPL.
#
# For each sample we drive `repl_thread.exe -f` with a one-shot
# script that loads the file and compiles it.  The REPL never
# self-terminates after `compile` so we kill the process after
# TIMEOUT seconds and inspect the captured output.

set -u

cd "$(dirname "$0")"

REPL=../_build/default/src/repl_thread.exe
ABCL2C=../_build/default/src/abcl2c.exe
TIMEOUT=${TIMEOUT:-5}
LOGDIR=_smoke_logs
rm -rf "$LOGDIR"
mkdir -p "$LOGDIR"

pass=0; fail=0; total=0
declare -a FAILS

# Gui/Py/Xinu variants are designed to be cross-compiled via abcl2c,
# not executed in the REPL.  Route them through abcl2c instead.
classify() {
  case "$1" in
    *Gui.abcl)  echo gui  ;;
    *Py.abcl)   echo py   ;;
    *Xinu.abcl) echo xinu ;;
    *)          echo repl ;;
  esac
}

run_repl() {
  local abcl="$1"
  local name="${abcl%.abcl}"
  # script must live in cwd (abclc/) so REPL's chdir doesn't move away
  # from the directory holding the .abcl file
  local script="./_smoke.bat"
  local log="$LOGDIR/${name}.log"
  printf 'load %s\ncompile\n' "$abcl" > "$script"

  "$REPL" -f "$script" >"$log" 2>&1 &
  local pid=$!
  ( sleep "$TIMEOUT" && kill -TERM "$pid" 2>/dev/null ) &
  local kpid=$!
  wait "$pid" 2>/dev/null
  kill "$kpid" 2>/dev/null
  wait "$kpid" 2>/dev/null

  if grep -qE '^\[Error\]|^\[Parse error\]|^\[Type error\]|^\[Compile error\]|^Fatal error|Failure\(' "$log"; then
    return 1
  fi
  grep -q '\[Compiled\]' "$log"
}

run_abcl2c() {
  local abcl="$1"
  local mode="$2"
  local name="${abcl%.abcl}"
  local log="$LOGDIR/${name}.log"
  case "$mode" in
    gui)  "$ABCL2C" "$abcl" -o "$LOGDIR/${name}.c"  --max-msgs 0          >"$log" 2>&1 ;;
    py)   "$ABCL2C" "$abcl" -o "$LOGDIR/${name}.py" --python --max-msgs 0 >"$log" 2>&1 ;;
    xinu) "$ABCL2C" "$abcl" -o "$LOGDIR/${name}.c"  --xinu   --max-msgs 0 >"$log" 2>&1 ;;
  esac
}

run_one() {
  local abcl="$1"
  total=$((total+1))
  local kind
  kind=$(classify "$abcl")
  if [ "$kind" = "repl" ]; then
    if run_repl "$abcl"; then
      pass=$((pass+1)); printf '  PASS  %s  (repl)\n' "$abcl"
    else
      fail=$((fail+1)); FAILS+=("$abcl"); printf '  FAIL  %s  (repl)\n' "$abcl"
    fi
  else
    if run_abcl2c "$abcl" "$kind"; then
      pass=$((pass+1)); printf '  PASS  %s  (abcl2c --%s)\n' "$abcl" "$kind"
    else
      fail=$((fail+1)); FAILS+=("$abcl"); printf '  FAIL  %s  (abcl2c --%s)\n' "$abcl" "$kind"
    fi
  fi
}

for f in *.abcl; do
  [ -e "$f" ] || continue
  run_one "$f"
done
rm -f ./_smoke.bat

echo
echo "==== summary ===="
echo "total: $total  pass: $pass  fail: $fail"
if [ "$fail" -gt 0 ]; then
  echo "---- failed samples ----"
  for f in "${FAILS[@]}"; do echo "  $f"; done
fi
