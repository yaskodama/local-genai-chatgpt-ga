#!/usr/bin/env bash
# Run all Level B-2 samples and verify each emits the expected
# number of issues.  Returns 0 if every sample matches.

set -u
cd "$(dirname "$0")"

declare -a SAMPLES=(
  "SampleEffectClean.abcl       0"
  "SampleEffectMissing.abcl     2"
  "SampleEffectIndirect.abcl    1"
  "SampleSelfConsistency.abcl   1"
)

pass=0; fail=0
for entry in "${SAMPLES[@]}"; do
  set -- $entry
  sample="$1"
  expected_issues="$2"

  bash run.sh "samples/$sample" >/dev/null 2>&1
  log="out/${sample%.abcl}.log"
  actual=$(grep -E '^issues=' "$log" | sed 's/issues=//')
  if [ "$actual" = "$expected_issues" ]; then
    pass=$((pass+1))
    printf "  PASS  %-32s issues=%s\n" "$sample" "$actual"
  else
    fail=$((fail+1))
    printf "  FAIL  %-32s expected=%s actual=%s\n" "$sample" "$expected_issues" "$actual"
  fi
done

echo
echo "Level B-2 effects samples: $pass pass / $fail fail"
exit "$fail"
