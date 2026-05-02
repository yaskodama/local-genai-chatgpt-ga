#!/bin/sh
# Philosophers5Gui.abcl をビルドして起動する。
set -e
cd "$(dirname "$0")"

dune build src/abcl2c.exe
./_build/default/src/abcl2c.exe abclc/Philosophers5Gui.abcl -o /tmp/p5.c --max-msgs 0
cc -O2 -Wall -pthread $(pkg-config --cflags sdl2) \
   -o /tmp/p5 /tmp/p5.c src/abcl_gui_runtime.c \
   $(pkg-config --libs sdl2) -lm
exec /tmp/p5
