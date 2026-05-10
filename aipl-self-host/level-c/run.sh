#!/usr/bin/env bash
# Drive a Level C sample through the AIPL parser+eval pipeline.
# Usage:  bash run.sh samples/<File>.abcl
set -u
cd "$(dirname "$0")"

SAMPLE="${1:?usage: $0 samples/<File>.abcl}"
NAME=$(basename "$SAMPLE" .abcl)
OUT_LOG="out/${NAME}.log"
TMP="/tmp/_lvC_${NAME}.abcl"

mkdir -p out

# Concat lexer + parser (when present) + sample.
PIECES=(lexer.abcl)
[ -f parser.abcl ] && PIECES+=(parser.abcl)
[ -f eval.abcl ]   && PIECES+=(eval.abcl)

cat "${PIECES[@]}" "$SAMPLE" > "$TMP"

PYTHONRECURSIONLIMIT_HACK="
import sys; sys.setrecursionlimit(20000)
import runpy
sys.argv = ['aipl_main.py', '$TMP', '--timeout', '10']
sys.path.insert(0, '../../src/python-aipl')
runpy.run_path('../../src/python-aipl/aipl_main.py', run_name='__main__')
"
AIPL_AI_PROVIDER=mock /usr/bin/python3 -c "$PYTHONRECURSIONLIMIT_HACK" > "$OUT_LOG" 2>&1

echo "=== $NAME — output ($OUT_LOG) ==="
cat "$OUT_LOG"
