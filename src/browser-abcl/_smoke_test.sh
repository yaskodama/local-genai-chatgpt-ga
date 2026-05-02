#!/usr/bin/env bash
# Smoke-test the browser-abcl JS implementation.
#
# Phase 1 (always): node --check on every .js source file
# Phase 2 (always): drive the jison-generated parser on every .abcl
#                   sample, wired with ast.js the same way the demo
#                   HTML pages do
# Phase 3 (when --dynamic): start a local http.server, open every demo
#                   HTML in headless system Chrome via puppeteer-core,
#                   wait WAIT seconds and report any console / page
#                   errors plus a head of the live #log
#
# Phase 3 is gated because it needs:
#   - /Applications/Google Chrome.app
#   - puppeteer-core (auto-installed under /tmp/abcl_pptr_test/)
#   - python3 to serve files

set -u

cd "$(dirname "$0")"

DYNAMIC=0
if [ "${1:-}" = "--dynamic" ]; then DYNAMIC=1; fi

LOGDIR=_smoke_logs
rm -rf "$LOGDIR"
mkdir -p "$LOGDIR"

# ---- Phase 1: JS syntax ----
echo "[Phase 1] node --check"
js_pass=0; js_fail=0
js_files=(src/ast.js src/interpreter.js src/main.js src/main01.js src/parser/parser.js src/runtime.js src/ui/console_browser.js)
for f in "${js_files[@]}"; do
  [ -f "$f" ] || continue
  if node --check "$f" 2>"$LOGDIR/$(basename "$f").err"; then
    printf '  PASS  %s\n' "$f"; js_pass=$((js_pass+1))
  else
    printf '  FAIL  %s\n' "$f"; js_fail=$((js_fail+1))
    head -3 "$LOGDIR/$(basename "$f").err" | sed 's/^/        /'
  fi
done

# ---- Phase 2: parser+ast on .abcl samples ----
echo "[Phase 2] parser.js + ast.js on .abcl samples"
parse_runner=$(mktemp /tmp/abcl_parse.XXXXXX.mjs)
cat > "$parse_runner" <<'NODE'
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const baseDir = process.argv[2];
const files = process.argv.slice(3);
const ast = await import(resolve(baseDir, 'src/ast.js'));
const require = createRequire(import.meta.url);
const parser = require(resolve(baseDir, 'src/parser/parser.js')).parser;
parser.yy = ast;

let fail = 0;
for (const f of files) {
  try {
    const src = readFileSync(resolve(baseDir, f), 'utf8');
    parser.parse(src);
    process.stdout.write(`  PASS  ${f}\n`);
  } catch (e) {
    process.stdout.write(`  FAIL  ${f}\n        ${String(e.message || e).split('\n')[0]}\n`);
    fail++;
  }
}
process.exit(fail === 0 ? 0 : 1);
NODE

abcl_files=(bounded_buffer.abcl philosophers.abcl rotate4lines.abcl drone_simulator.abcl)
parse_pass=0; parse_fail=0
parse_out=$(node "$parse_runner" "$(pwd)" "${abcl_files[@]}" 2>&1)
echo "$parse_out"
parse_pass=$(echo "$parse_out" | grep -c '^  PASS' || true)
parse_fail=$(echo "$parse_out" | grep -c '^  FAIL' || true)
rm -f "$parse_runner"

# ---- Phase 3: dynamic puppeteer-core run ----
dyn_pass=0; dyn_fail=0; dyn_skip=0
if [ "$DYNAMIC" = "1" ]; then
  CHROME='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
  PPTR_DIR=/tmp/abcl_pptr_test
  if [ ! -x "$CHROME" ]; then
    echo "[Phase 3] SKIP: Chrome not found at $CHROME"
    dyn_skip=1
  else
    if [ ! -d "$PPTR_DIR/node_modules/puppeteer-core" ]; then
      echo "[Phase 3] installing puppeteer-core into $PPTR_DIR"
      mkdir -p "$PPTR_DIR"
      ( cd "$PPTR_DIR" && npm init -y >/dev/null 2>&1 && npm install puppeteer-core >/dev/null 2>&1 )
    fi
    echo "[Phase 3] headless Chrome via puppeteer-core"
    PORT=8765
    python3 -m http.server "$PORT" >"$LOGDIR/server.log" 2>&1 &
    SERVER_PID=$!
    sleep 1
    # ESM resolves bare imports against the *script's* directory, not
    # cwd, so copy the runner into $PPTR_DIR (which has
    # node_modules/puppeteer-core) and execute it there.
    dyn_log="$LOGDIR/pptr.log"
    cp ./_smoke_pptr.mjs "$PPTR_DIR/_smoke_pptr.mjs"
    ( cd "$PPTR_DIR" && \
      ABCL_CHROME="$CHROME" \
      ABCL_BASE="http://localhost:$PORT" \
      node ./_smoke_pptr.mjs ) >"$dyn_log" 2>&1
    rc=$?
    cat "$dyn_log"
    dyn_pass=$(grep -c '^  PASS' "$dyn_log" 2>/dev/null); dyn_pass=${dyn_pass:-0}
    dyn_fail=$(grep -c '^  FAIL' "$dyn_log" 2>/dev/null); dyn_fail=${dyn_fail:-0}
    if [ "$rc" -ne 0 ] && [ "$dyn_fail" -eq 0 ]; then dyn_fail=1; fi
    kill "$SERVER_PID" 2>/dev/null
    wait "$SERVER_PID" 2>/dev/null
  fi
fi

# ---- Summary ----
echo
echo "==== JS smoke summary ===="
printf '  syntax: pass=%d fail=%d\n' "$js_pass" "$js_fail"
printf '  parse : pass=%d fail=%d\n' "$parse_pass" "$parse_fail"
if [ "$DYNAMIC" = "1" ]; then
  if [ "$dyn_skip" = "1" ]; then
    echo "  dynamic: SKIPPED"
  else
    grep -cE '^  PASS|^  FAIL' /dev/null >/dev/null # noop
    printf '  dynamic: pass=%d fail=%d\n' "$dyn_pass" "$dyn_fail"
  fi
fi

total_fail=$((js_fail + parse_fail + dyn_fail))
exit $total_fail
