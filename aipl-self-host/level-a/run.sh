#!/usr/bin/env bash
# run.sh — drive a Level A sample through the metacircular evaluator.
#
# Usage:
#   bash run.sh samples/SampleArith.abcl
# Concats metacircular.abcl + the sample into a tmpfile and runs it
# through the Python AIPL interpreter, capturing stdout to out/.

set -u
cd "$(dirname "$0")"

SAMPLE="${1:?usage: $0 samples/<File>.abcl}"
NAME=$(basename "$SAMPLE" .abcl)
OUT_LOG="out/${NAME}.log"
TMP="/tmp/_lvA_${NAME}.abcl"

mkdir -p out

cat metacircular.abcl "$SAMPLE" > "$TMP"

# The metacircular evaluator stacks AIPL eval_* frames on top of the
# host Python frames; each AIPL function call uses ~10 Python frames,
# so even modest recursion (fib(5)) needs a higher recursion limit.
PYTHONRECURSIONLIMIT_HACK="
import sys; sys.setrecursionlimit(20000)
import runpy
sys.argv = ['aipl_main.py', '$TMP', '--timeout', '8']
sys.path.insert(0, '../../src/python-aipl')
runpy.run_path('../../src/python-aipl/aipl_main.py', run_name='__main__')
"
AIPL_AI_PROVIDER=mock /usr/bin/python3 -c "$PYTHONRECURSIONLIMIT_HACK" > "$OUT_LOG" 2>&1

echo "=== $NAME — output ($OUT_LOG) ==="
cat "$OUT_LOG"
