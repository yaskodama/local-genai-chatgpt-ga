#!/usr/bin/env bash
set -u
cd "$(dirname "$0")"

run_check() {
  local sample="$1"; shift
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
run_check SampleNow.abcl       7  && pass=$((pass+1)) || fail=$((fail+1))

echo
echo "Level C-3 scheduler samples: $pass pass / $fail fail"
exit "$fail"
