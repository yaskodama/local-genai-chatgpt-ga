#!/bin/sh
# DisasterReturnGui.abcl をビルドして起動する。
set -e
cd "$(dirname "$0")"

dune build src/abcl2c.exe
./_build/default/src/abcl2c.exe abclc/DisasterReturnGui.abcl -o /tmp/dr.c --max-msgs 0
cc -O2 -Wall -pthread $(pkg-config --cflags sdl2) \
   -o /tmp/dr /tmp/dr.c src/abcl_gui_runtime.c \
   $(pkg-config --libs sdl2) -lm
exec /tmp/dr
