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


def load_snapshot() -> dict:
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
    actors = data.get("actors", {})
    return actors if isinstance(actors, dict) else {}


def _is_persistable(v) -> bool:
    return isinstance(v, (int, float, bool, str))


def save_snapshot(actors: list) -> None:
    """Write a JSON snapshot of every (name, fields) actor in the
    list.  `actors` is a list of (name:str, fields:dict)."""
    p = state_file_path()
    if not p:
        return
    with _save_lock:
        snapshot = {"actors": {}}
        for name, fields in actors:
            persistable = {k: v for k, v in fields.items() if _is_persistable(v)}
            if persistable:
                snapshot["actors"][name] = persistable
        dirn = os.path.dirname(os.path.abspath(p)) or "."
        try:
            os.makedirs(dirn, exist_ok=True)
            fd, tmp = tempfile.mkstemp(prefix=".state_", dir=dirn)
            try:
                with os.fdopen(fd, "w") as f:
                    json.dump(snapshot, f, indent=2)
                os.replace(tmp, p)
            except Exception:
                try: os.unlink(tmp)
                except OSError: pass
                raise
        except OSError as e:
            print(f"[state] save failed: {e}")
