#!/usr/bin/env bash
set -u
cd "$(dirname "$0")"

declare -a SAMPLES=(
  "SampleOwnedClean.abcl        0"
  "SamplePrivateRead.abcl       1"
  "SampleExternalWrite.abcl     2"
  "SampleSelfConsistency.abcl   2"
)

pass=0; fail=0
for entry in "${SAMPLES[@]}"; do
  set -- $entry
  sample="$1"; expected="$2"
  bash run.sh "samples/$sample" >/dev/null 2>&1
  log="out/${sample%.abcl}.log"
  actual=$(grep -E '^issues=' "$log" | sed 's/issues=//')
  if [ "$actual" = "$expected" ]; then
    pass=$((pass+1))
    printf "  PASS  %-32s issues=%s\n" "$sample" "$actual"
  else
    fail=$((fail+1))
    printf "  FAIL  %-32s expected=%s actual=%s\n" "$sample" "$expected" "$actual"
  fi
done

echo
echo "Level B-5 owned samples: $pass pass / $fail fail"
exit "$fail"
