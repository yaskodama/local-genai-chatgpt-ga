#!/bin/sh
# Rotate4LinesGui.abcl をビルドして起動する。
set -e
cd "$(dirname "$0")"

dune build src/abcl2c.exe
./_build/default/src/abcl2c.exe abclc/Rotate4LinesGui.abcl -o /tmp/r4l.c --max-msgs 0
cc -O2 -Wall -pthread $(pkg-config --cflags sdl2) \
   -o /tmp/r4l /tmp/r4l.c src/abcl_gui_runtime.c \
   $(pkg-config --libs sdl2) -lm
exec /tmp/r4l
