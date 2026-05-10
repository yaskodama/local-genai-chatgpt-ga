#!/usr/bin/env bash
# Smoke-test all Level C-2 scheduler samples by checking that each
# expected output line appears in the run log.
set -u
cd "$(dirname "$0")"

run_check() {
  local sample="$1"
  shift
  bash run.sh "samples/$sample" >/dev/null 2>&1
  local log="out/${sample%.abcl}.log"
  for line in "$@"; do
    if ! grep -qx "$line" "$log"; then
      printf "  FAIL  %-32s missing line '%s'\n" "$sample" "$line"
      return 1
    fi
  done
  printf "  PASS  %s\n" "$sample"
  return 0
}

pass=0; fail=0

run_check SampleCounter.abcl           1 2 3                 && pass=$((pass+1)) || fail=$((fail+1))
run_check SamplePingPong.abcl          3 2 1                 && pass=$((pass+1)) || fail=$((fail+1))
run_check SampleSelfSend.abcl          1 2 3 4 5             && pass=$((pass+1)) || fail=$((fail+1))
run_check SampleMethodArgs.abcl        7 36 30               && pass=$((pass+1)) || fail=$((fail+1))
run_check SampleProducerConsumer.abcl  1 3 6 10              && pass=$((pass+1)) || fail=$((fail+1))
run_check SampleWorkerPool.abcl        104 209 325           && pass=$((pass+1)) || fail=$((fail+1))

echo
echo "Level C-2 scheduler samples: $pass pass / $fail fail"
exit "$fail"
