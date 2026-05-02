#!/bin/sh
# BoundedBufferPy.abcl を Python (tkinter) 上で動かす。
set -e
cd "$(dirname "$0")"

dune build src/abcl2c.exe
./_build/default/src/abcl2c.exe abclc/BoundedBufferPy.abcl \
    --python --max-msgs 0 -o /tmp/bb_py.py

exec python3 /tmp/bb_py.py
