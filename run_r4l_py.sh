#!/bin/sh
# Rotate4LinesPy.abcl を Python (tkinter) 上で動かす。
#  - python3 -c 'import tkinter' が成功する Python が必要。
#  - Homebrew Python なら `brew install python-tk@3.14` 等で入る。
set -e
cd "$(dirname "$0")"

dune build src/abcl2c.exe
./_build/default/src/abcl2c.exe abclc/Rotate4LinesPy.abcl \
    --python --max-msgs 0 -o /tmp/r4l_py.py

exec python3 /tmp/r4l_py.py
