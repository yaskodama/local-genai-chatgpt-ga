#!/bin/sh
# Philosophers5Py.abcl を Python (tkinter) 上で動かす。
set -e
cd "$(dirname "$0")"

dune build src/abcl2c.exe
./_build/default/src/abcl2c.exe abclc/Philosophers5Py.abcl \
    --python --max-msgs 0 -o /tmp/p5_py.py

exec python3 /tmp/p5_py.py
