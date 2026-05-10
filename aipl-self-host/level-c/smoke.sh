#!/usr/bin/env bash
# Smoke-test all Level C samples.

set -u
cd "$(dirname "$0")"

declare -a SAMPLES=(
  "SampleLexer.abcl       token count = 26"
  "SamplePipeline.abcl    13"
  "SampleWhile.abcl       10"
)

pass=0; fail=0
for entry in "${SAMPLES[@]}"; do
  sample=$(echo "$entry" | awk '{print $1}')
  expected=$(echo "$entry" | sed -E 's/^[^[:space:]]+[[:space:]]+//')

  bash run.sh "samples/$sample" >/dev/null 2>&1
  log="out/${sample%.abcl}.log"
  if grep -qF "$expected" "$log"; then
    pass=$((pass+1))
    printf "  PASS  %-30s found '%s'\n" "$sample" "$expected"
  else
    fail=$((fail+1))
    printf "  FAIL  %-30s missing '%s'\n" "$sample" "$expected"
  fi
done

echo
echo "Level C samples: $pass pass / $fail fail"
exit "$fail"
