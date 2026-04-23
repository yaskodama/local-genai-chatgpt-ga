#!/bin/bash
cd "$(dirname "$0")"
exec ./_build/default/src/repl_thread.exe -f abclc/run_bounded_buffer.bat
