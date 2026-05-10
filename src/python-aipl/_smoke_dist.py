#!/usr/bin/env python3
"""Distributed 3-node smoke test for AIPL.

Spins up samples-remote/{solver,verifier,coordinator}.abcl as three
local processes against the mock AI provider so the test needs no
network and no API keys.  Verifies the inter-node message chain
produced output on every node and ran via the mock.

Exit code 0 on success; 1 on any check failure.
"""

import os
import pathlib
import signal
import subprocess
import sys
import time

THIS = pathlib.Path(__file__).resolve().parent
LOGDIR = THIS / "_smoke_logs" / "dist"
LOGDIR.mkdir(parents=True, exist_ok=True)


def _spawn(name: str, sample: str, env: dict) -> "subprocess.Popen":
    log = open(LOGDIR / f"{name}.log", "w")
    return subprocess.Popen(
        [sys.executable, "aipl_main.py", sample],
        cwd=THIS,
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
    )


def _terminate(p, name: str) -> None:
    if p.poll() is not None:
        return
    p.send_signal(signal.SIGINT)
    try:
        p.wait(timeout=2)
    except subprocess.TimeoutExpired:
        p.kill()
        try:
            p.wait(timeout=1)
        except subprocess.TimeoutExpired:
            print(f"  WARN  {name} did not exit", flush=True)


def _read(path: pathlib.Path) -> str:
    try:
        return path.read_text(errors="replace")
    except OSError:
        return ""


def main() -> int:
    env = os.environ.copy()
    # Offline provider — no keys required.
    env["ABCL_AI_PROVIDER"] = "mock"

    solver   = _spawn("solver",   "samples-remote/solver.abcl",      env)
    verifier = _spawn("verifier", "samples-remote/verifier.abcl",    env)
    time.sleep(1.5)
    coord    = _spawn("coord",    "samples-remote/coordinator.abcl", env)

    # The coordinator drives one demo question on startup.  Let the
    # whole chain (3 mock calls) settle, then bring everyone down.
    time.sleep(6.0)
    _terminate(coord,    "coord")
    _terminate(verifier, "verifier")
    _terminate(solver,   "solver")

    coord_log    = _read(LOGDIR / "coord.log")
    solver_log   = _read(LOGDIR / "solver.log")
    verifier_log = _read(LOGDIR / "verifier.log")

    fails = 0
    def check(label: str, cond: bool):
        nonlocal fails
        if cond:
            print(f"  PASS  {label}", flush=True)
        else:
            print(f"  FAIL  {label}", flush=True)
            fails += 1

    check("solver started",     "[node] solver up"     in solver_log)
    check("verifier started",   "[node] verifier up"   in verifier_log)
    check("coordinator started", "[node] coordinator up" in coord_log)
    check("solver hit mock",    "[mock]"               in solver_log)
    check("verifier hit mock",  "[mock]"               in verifier_log)
    check("coord got answer",   "=== ANSWER ==="       in coord_log)
    check("coord got critique", "=== CRITIQUE ==="     in coord_log)
    # The mock reply is non-empty, so coord's answer line shouldn't be None
    check("coord answer not None", "=== ANSWER ===\nNone" not in coord_log)

    print(f"==== distributed smoke: pass={8 - fails} fail={fails} ====", flush=True)
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
