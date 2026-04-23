#!/bin/bash
cd "$(dirname "$0")"
exec ./_build/default/src/repl_thread.exe -f abclc/run_rotate4.bat
