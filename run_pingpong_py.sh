#!/bin/sh
# PingPong.abcl を Python アクターランタイムで動かす。
set -e
cd "$(dirname "$0")"

dune build src/abcl2c.exe
./_build/default/src/abcl2c.exe abclc/PingPong.abcl \
    --python --max-msgs 12 -o /tmp/pingpong.py

exec python3 /tmp/pingpong.py
