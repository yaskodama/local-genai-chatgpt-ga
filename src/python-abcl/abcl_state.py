"""Per-node persistent state for ABCL/c+ actors.

When ABCL_NODE_STATE_FILE is set, the interpreter (a) loads any
matching actor fields from that JSON file just after spawning each
actor, and (b) writes a snapshot every time a .abcl program calls
the `save_state()` builtin.  The file format is

  {"actors": {"<actor_name>": {"<field>": <value>, ...}}}

Only int / float / string / bool fields are persisted — Actor
references and complex objects are silently skipped on save and not
reloaded on load.  Atomic writes (tmp + rename) so a crash mid-write
doesn't leave a half-snapshot.
"""

import json
import os
import tempfile
import threading
from typing import Optional


_save_lock = threading.Lock()


def state_file_path() -> Optional[str]:
    p = os.environ.get("ABCL_NODE_STATE_FILE", "").strip()
    return p or None


def _read_doc() -> dict:
    p = state_file_path()
    if not p:
        return {}
    try:
        with open(p) as f:
            data = json.load(f)
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def load_snapshot() -> dict:
    actors = _read_doc().get("actors", {})
    return actors if isinstance(actors, dict) else {}


def load_pending() -> dict:
    """Returns {actor_name: [{"method": str, "args": [...]}, ...]}
    of mailbox messages that the previous run shut down with."""
    pending = _read_doc().get("pending", {})
    return pending if isinstance(pending, dict) else {}


def _is_persistable(v) -> bool:
    return isinstance(v, (int, float, bool, str))


def _atomic_write(path: str, doc: dict) -> None:
    dirn = os.path.dirname(os.path.abspath(path)) or "."
    try:
        os.makedirs(dirn, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".state_", dir=dirn)
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(doc, f, indent=2)
            os.replace(tmp, path)
        except Exception:
            try: os.unlink(tmp)
            except OSError: pass
            raise
    except OSError as e:
        print(f"[state] save failed: {e}")


def save_snapshot(actors: list, pending=None) -> None:
    """Write a JSON snapshot to ABCL_NODE_STATE_FILE.  `actors` is a
    list of (name, fields-dict).  `pending`, if provided, is a list
    of (actor_name, [{"method","args"}, ...]) of undelivered
    mailbox messages.  Actors with no persistable state still get an
    empty dict so the file shape stays consistent."""
    p = state_file_path()
    if not p:
        return
    with _save_lock:
        snapshot = {"actors": {}, "pending": {}}
        for name, fields in actors:
            persistable = {k: v for k, v in fields.items() if _is_persistable(v)}
            if persistable:
                snapshot["actors"][name] = persistable
        if pending:
            for name, msgs in pending:
                if msgs:
                    snapshot["pending"][name] = msgs
        _atomic_write(p, snapshot)
