#!/usr/bin/env bash
set -u
cd "$(dirname "$0")"

SAMPLE="${1:?usage: $0 samples/<File>.abcl}"
NAME=$(basename "$SAMPLE" .abcl)
OUT_LOG="out/${NAME}.log"
TMP="/tmp/_lvB5_${NAME}.abcl"

mkdir -p out
cat typeck.abcl "$SAMPLE" > "$TMP"

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
