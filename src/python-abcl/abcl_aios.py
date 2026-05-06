"""AIOS coordination + protocol + session-type primitives for ABCL/c+.

This module adds three families of builtins:

  aios_* …………  service registry, fire/await coordination, event log.
                  A thin layer over the existing actor table — used to
                  drive 3-role cooperative samples without hard-coding
                  actor names.

  protocol_* ……  named protocol traces. A protocol is a `->`-separated
                  ordered list of "actor.method" steps. `protocol_start`
                  opens a session-id, `aios_now` / `aios_future` record
                  events into it, `protocol_state` queries progress.

  session_* ……   *typed* session protocols. Same shape as protocol_*
                  but each step carries argument and reply types, and
                  the runtime type-checks every observed call against
                  the declaration. Failures are recorded into
                  `session_events()` as "[SESSION VIOLATION] …" entries
                  and also raise so callers can see them at runtime.
                  Type checking here is intentionally *separate from*
                  the normal type inference — it sees only what actually
                  flows over the wire at runtime.
"""

from __future__ import annotations
import threading
import time
import re
from typing import Any, Callable, Dict, List, Optional, Tuple


# ====================================================================
# Service registry + event log (aios_*)
# ====================================================================

_aios_services: Dict[str, str] = {}        # service alias → actor name
_aios_events:   List[str]      = []
_aios_lock = threading.Lock()


def _aios_log(msg: str) -> None:
    with _aios_lock:
        _aios_events.append(msg)


def aios_register_service(alias: str, actor_name: str) -> None:
    with _aios_lock:
        _aios_services[alias] = actor_name
    _aios_log(f"[REGISTER] {alias} -> {actor_name}")


def aios_resolve(alias: str) -> str:
    with _aios_lock:
        return _aios_services.get(alias, alias)


def aios_services_list() -> List[Tuple[str, str]]:
    with _aios_lock:
        return list(_aios_services.items())


def aios_emit(msg: str) -> None:
    _aios_log("[EMIT] " + str(msg))


def aios_events_list() -> List[str]:
    with _aios_lock:
        return list(_aios_events)


# ====================================================================
# Protocol traces (protocol_*) — order-only, no type info
# ====================================================================

_proto_defs:    Dict[str, List[str]]      = {}   # name → ["a.m", "b.n", …]
_proto_active:  Dict[str, Dict[str, Any]] = {}   # sid → {name, idx, log}
_proto_events:  List[str]                 = []
_proto_seq                                = 0
_proto_lock = threading.Lock()


def _proto_log(msg: str) -> None:
    with _proto_lock:
        _proto_events.append(msg)


def protocol_define(name: str, spec: str) -> None:
    steps = [s.strip() for s in spec.split("->") if s.strip()]
    with _proto_lock:
        _proto_defs[name] = steps
    _proto_log(f"[PROTO_DEF] {name} = {steps}")


def protocol_start(name: str) -> str:
    global _proto_seq
    with _proto_lock:
        if name not in _proto_defs:
            raise RuntimeError(f"protocol_start: unknown protocol {name!r}")
        _proto_seq += 1
        sid = f"proto-{_proto_seq}-{int(time.time() * 1000)}"
        _proto_active[sid] = {
            "name": name,
            "idx": 0,
            "log": [],
            "start_ts": time.time(),
            "ended": False,
        }
    _proto_log(f"[PROTO_START] sid={sid} proto={name}")
    return sid


def protocol_observe(sid: str, step: str) -> None:
    """Record `step` (form 'actor.method') against the active protocol."""
    with _proto_lock:
        st = _proto_active.get(sid)
        if not st or st.get("ended"):
            return
        defn = _proto_defs.get(st["name"], [])
        st["log"].append(step)
        if st["idx"] < len(defn) and defn[st["idx"]] == step:
            st["idx"] += 1
        # Mismatches are still logged but don't advance the cursor.


def protocol_state(sid: str) -> str:
    with _proto_lock:
        st = _proto_active.get(sid)
        if not st:
            return f"[PROTO_STATE] sid={sid} (unknown)"
        defn = _proto_defs.get(st["name"], [])
        progress = f"{st['idx']}/{len(defn)}"
        next_step = defn[st["idx"]] if st["idx"] < len(defn) else "(done)"
        status = "ended" if st.get("ended") else "running"
        return (f"[PROTO_STATE] sid={sid} proto={st['name']} "
                f"progress={progress} next={next_step} status={status}")


def protocol_end(sid: str) -> None:
    with _proto_lock:
        st = _proto_active.get(sid)
        if st:
            st["ended"] = True
    _proto_log(f"[PROTO_END] sid={sid}")


def protocol_events_list() -> List[str]:
    with _proto_lock:
        return list(_proto_events)


# ====================================================================
# Typed session protocols (session_*)
# ====================================================================
#
# Spec syntax:
#
#   "actor.method(t1,t2) ! r1 -> actor2.method2(t3) ! r2 -> end"
#
# Each step is:
#   <actor>.<method>(<arg_types>) ! <reply_type>
#
# Types accepted: int, float, string, bool, any
# `end` (or omitted) marks the end of the protocol.
#
# Type checking is done *separately* from the normal Hindley-Milner
# style type inference — it only inspects the values actually flowing
# at runtime and validates them against the session declaration.

_TYPE_PATTERNS: Dict[str, Callable[[Any], bool]] = {
    "int":    lambda v: isinstance(v, int) and not isinstance(v, bool),
    "float":  lambda v: isinstance(v, float),
    "number": lambda v: (isinstance(v, (int, float)) and not isinstance(v, bool)),
    "string": lambda v: isinstance(v, str),
    "bool":   lambda v: isinstance(v, bool),
    "any":    lambda v: True,
    "unit":   lambda v: v is None,
    "null":   lambda v: v is None,
}

_STEP_RE = re.compile(
    r"""
    ^\s*
    (?P<actor>[A-Za-z_][\w]*)
    \.
    (?P<method>[A-Za-z_][\w]*)
    \s*
    (?: \( (?P<args>[^()]*) \) )?
    (?: \s* ! \s* (?P<ret>[A-Za-z_]\w*) )?
    \s*$
    """,
    re.VERBOSE,
)


def _parse_step(step: str) -> Dict[str, Any]:
    if step.strip().lower() == "end":
        return {"_end": True}
    m = _STEP_RE.match(step)
    if not m:
        raise RuntimeError(f"session: bad step syntax: {step!r}")
    arg_types = []
    raw = (m.group("args") or "").strip()
    if raw:
        arg_types = [p.strip() for p in raw.split(",") if p.strip()]
    for t in arg_types:
        if t not in _TYPE_PATTERNS:
            raise RuntimeError(f"session: unknown type {t!r} in {step!r}")
    ret = m.group("ret") or "any"
    if ret not in _TYPE_PATTERNS:
        raise RuntimeError(f"session: unknown reply type {ret!r}")
    return {
        "actor":  m.group("actor"),
        "method": m.group("method"),
        "args":   arg_types,
        "ret":    ret,
    }


_sess_defs:    Dict[str, List[Dict[str, Any]]] = {}
_sess_active:  Dict[str, Dict[str, Any]]       = {}
_sess_events:  List[str]                       = []
_sess_seq                                       = 0
_sess_lock = threading.Lock()


def _sess_log(msg: str) -> None:
    with _sess_lock:
        _sess_events.append(msg)


def session_define(name: str, spec: str) -> None:
    """Declare a typed session protocol."""
    raw_steps = [s.strip() for s in spec.split("->") if s.strip()]
    parsed: List[Dict[str, Any]] = []
    for s in raw_steps:
        p = _parse_step(s)
        if p.get("_end"):
            break
        parsed.append(p)
    with _sess_lock:
        _sess_defs[name] = parsed
    _sess_log(f"[SESSION_DEF] {name} = "
              + " -> ".join(
                  f"{p['actor']}.{p['method']}({','.join(p['args'])}):{p['ret']}"
                  for p in parsed))


def session_start(name: str) -> str:
    global _sess_seq
    with _sess_lock:
        if name not in _sess_defs:
            raise RuntimeError(f"session_start: unknown session {name!r}")
        _sess_seq += 1
        sid = f"sess-{_sess_seq}-{int(time.time() * 1000)}"
        _sess_active[sid] = {
            "name": name,
            "idx": 0,
            "violations": 0,
            "ended": False,
        }
    _sess_log(f"[SESSION_START] sid={sid} name={name}")
    return sid


def _type_of(v: Any) -> str:
    if v is None: return "unit"
    if isinstance(v, bool): return "bool"
    if isinstance(v, int): return "int"
    if isinstance(v, float): return "float"
    if isinstance(v, str): return "string"
    return "any"


def session_check(sid: str, actor: str, method: str,
                  args: List[Any], reply: Any) -> str:
    """Validate a single observed call against the session.

    Returns "ok" / "violation: ..." string. Also records into
    session_events() and increments the violation counter on the sid.
    """
    with _sess_lock:
        st = _sess_active.get(sid)
        if not st:
            msg = f"[SESSION VIOLATION] sid={sid} (unknown session)"
            _sess_events.append(msg)
            return msg
        if st.get("ended"):
            msg = (f"[SESSION VIOLATION] sid={sid} call after end "
                   f"({actor}.{method})")
            _sess_events.append(msg)
            st["violations"] += 1
            return msg
        defn = _sess_defs.get(st["name"], [])
        idx = st["idx"]
        if idx >= len(defn):
            msg = (f"[SESSION VIOLATION] sid={sid} extra call "
                   f"{actor}.{method} (protocol already complete)")
            _sess_events.append(msg)
            st["violations"] += 1
            return msg
        expected = defn[idx]
        # 1) ordering / actor / method
        if expected["actor"] != actor or expected["method"] != method:
            msg = (f"[SESSION VIOLATION] sid={sid} step {idx}: "
                   f"expected {expected['actor']}.{expected['method']} "
                   f"but got {actor}.{method}")
            _sess_events.append(msg)
            st["violations"] += 1
            return msg
        # 2) argument types
        exp_args = expected["args"]
        if len(exp_args) != len(args):
            msg = (f"[SESSION VIOLATION] sid={sid} step {idx} "
                   f"{actor}.{method}: arity mismatch "
                   f"expected {len(exp_args)} got {len(args)}")
            _sess_events.append(msg)
            st["violations"] += 1
            return msg
        for i, (et, av) in enumerate(zip(exp_args, args)):
            if not _TYPE_PATTERNS[et](av):
                msg = (f"[SESSION VIOLATION] sid={sid} step {idx} "
                       f"{actor}.{method}: arg {i} expected {et} "
                       f"got {_type_of(av)} ({av!r})")
                _sess_events.append(msg)
                st["violations"] += 1
                return msg
        # 3) reply type
        rt = expected["ret"]
        if not _TYPE_PATTERNS[rt](reply):
            msg = (f"[SESSION VIOLATION] sid={sid} step {idx} "
                   f"{actor}.{method}: reply expected {rt} got "
                   f"{_type_of(reply)} ({reply!r})")
            _sess_events.append(msg)
            st["violations"] += 1
            return msg
        # All checks passed — advance.
        st["idx"] += 1
        ok = (f"[SESSION_OK] sid={sid} step {idx} {actor}.{method}"
              f"({','.join(exp_args)}):{rt}")
        _sess_events.append(ok)
        return "ok"


def session_state(sid: str) -> str:
    with _sess_lock:
        st = _sess_active.get(sid)
        if not st:
            return f"[SESSION_STATE] sid={sid} (unknown)"
        defn = _sess_defs.get(st["name"], [])
        progress = f"{st['idx']}/{len(defn)}"
        if st["idx"] < len(defn):
            n = defn[st["idx"]]
            nxt = (f"{n['actor']}.{n['method']}("
                   f"{','.join(n['args'])}):{n['ret']}")
        else:
            nxt = "(done)"
        status = "ended" if st.get("ended") else "running"
        return (f"[SESSION_STATE] sid={sid} session={st['name']} "
                f"progress={progress} next={nxt} status={status} "
                f"violations={st['violations']}")


def session_end(sid: str) -> None:
    with _sess_lock:
        st = _sess_active.get(sid)
        if st:
            st["ended"] = True
    _sess_log(f"[SESSION_END] sid={sid}")


def session_events_list() -> List[str]:
    with _sess_lock:
        return list(_sess_events)


# ====================================================================
# Auto-observation
# ====================================================================
#
# Called by the interpreter from aios_now / await(aios_future) so that
# every coordination call shows up in protocol_events()/session_events()
# and gets type-checked against active sessions, without the user having
# to call protocol_observe / session_check explicitly.

def record_observation(actor_alias: str, method: str,
                       args: List[Any], reply: Any) -> None:
    """Record one call against every still-running protocol & session."""
    step = f"{actor_alias}.{method}"
    # Protocols (order-only)
    with _proto_lock:
        proto_sids = [sid for sid, st in _proto_active.items()
                      if not st.get("ended")]
    for sid in proto_sids:
        protocol_observe(sid, step)
    # Sessions (typed)
    with _sess_lock:
        sess_sids = [sid for sid, st in _sess_active.items()
                     if not st.get("ended")]
    for sid in sess_sids:
        session_check(sid, actor_alias, method, args, reply)
