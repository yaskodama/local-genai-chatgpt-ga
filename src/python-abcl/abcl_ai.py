"""AI provider integration for the Python ABCL/c+ runtime.

`call_ai(prompt, system=...)` is the synchronous primitive that the
interpreter wires up as `ai_call` / `ai_call_with_system`.  It
auto-dispatches to whichever provider has its key in the environment:

    GEMINI_API_KEY   -> google-genai   (default model: gemini-2.5-flash)
    ANTHROPIC_API_KEY -> anthropic SDK (default model: claude-opus-4-7)

When both are set, set `ABCL_AI_PROVIDER=gemini|anthropic` to pick
explicitly.  SDKs are imported lazily so the module is still importable
on a machine with neither installed; the error only surfaces when an
.abcl program actually invokes ai_call().

AI-OS governance knobs (env vars, all optional):

    ABCL_AI_TOKEN_BUDGET=N   total prompt+completion tokens cap; calls
                             past the cap raise BudgetExceeded
    ABCL_AI_MAX_CONCURRENT=N at most N AI calls in flight at once;
                             excess actors block on a semaphore (FIFO)

`get_usage()` returns the live counter; the interpreter exposes it as
the `ai_usage()` builtin.
"""

import itertools
import os
import threading
from typing import Optional


_anthropic_client = None
_gemini_client = None

DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
DEFAULT_ANTHROPIC_MODEL = "claude-opus-4-7"
# Enough headroom for visible output even when the model spends part of
# its budget on internal thinking tokens (gemini-2.5 thinks by default,
# Opus 4.7 thinks adaptively).
DEFAULT_MAX_TOKENS = 4096


# ---------------------------------------------------------------------------
# AI-OS governance: usage counters + budget + concurrency limit

class BudgetExceeded(RuntimeError):
    """Raised when ABCL_AI_TOKEN_BUDGET is set and the running total
    would exceed it.  The call is refused before hitting the network."""


_usage_lock = threading.Lock()
_usage = {"calls": 0, "input_tokens": 0, "output_tokens": 0}

DEFAULT_PRIORITY = 10


class _PriorityGate:
    """Bounded-concurrency gate that admits waiters in priority order.

    Drop-in replacement for a counting semaphore used as
    `with gate.acquire(priority): ...`.  When `available > 0` the
    caller proceeds immediately; when not, it blocks on a private
    Condition and is woken in (priority asc, FIFO) order.

    `priority` is a number — *lower* sorts first, matching Unix nice.
    Ties are broken by enqueue order so equal-priority waiters are
    served FIFO.
    """

    def __init__(self, capacity: int):
        self.capacity = max(1, capacity)
        self.available = self.capacity
        self.cond = threading.Condition()
        self._counter = itertools.count()  # tiebreaker

    def acquire(self, priority: float = DEFAULT_PRIORITY) -> None:
        with self.cond:
            if self.available > 0 and self._is_my_turn(priority):
                self.available -= 1
                return
            ticket = (priority, next(self._counter))
            self._waiting.append(ticket)
            self._waiting.sort()
            try:
                while True:
                    if self.available > 0 and self._waiting[0] == ticket:
                        self._waiting.pop(0)
                        self.available -= 1
                        return
                    self.cond.wait()
            except BaseException:
                # Ensure we don't leave a dead ticket in the queue.
                try: self._waiting.remove(ticket)
                except ValueError: pass
                self.cond.notify_all()
                raise

    def release(self) -> None:
        with self.cond:
            self.available += 1
            self.cond.notify_all()

    # The waiting queue is initialised lazily so the simple no-contention
    # path stays a single-line `if available > 0`.
    @property
    def _waiting(self):
        if not hasattr(self, "_w"):
            self._w = []
        return self._w

    def _is_my_turn(self, priority: float) -> bool:
        return not self._waiting or priority <= self._waiting[0][0]


# Concurrency gate is created lazily so changing the env var
# between runs takes effect.
_concurrency_gate: Optional["_PriorityGate"] = None
_concurrency_inited = False
_concurrency_init_lock = threading.Lock()


def _int_env(name: str, default: int = 0) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _get_budget() -> int:
    return _int_env("ABCL_AI_TOKEN_BUDGET", 0)


def _get_concurrency_gate() -> Optional["_PriorityGate"]:
    global _concurrency_gate, _concurrency_inited
    if _concurrency_inited:
        return _concurrency_gate
    with _concurrency_init_lock:
        if not _concurrency_inited:
            limit = _int_env("ABCL_AI_MAX_CONCURRENT", 0)
            _concurrency_gate = _PriorityGate(limit) if limit > 0 else None
            _concurrency_inited = True
    return _concurrency_gate


def _check_budget() -> None:
    budget = _get_budget()
    if budget <= 0:
        return
    with _usage_lock:
        used = _usage["input_tokens"] + _usage["output_tokens"]
    if used >= budget:
        raise BudgetExceeded(
            f"AI token budget exceeded: used={used} budget={budget}"
        )


def _record_usage(input_tokens: int, output_tokens: int) -> None:
    with _usage_lock:
        _usage["calls"] += 1
        _usage["input_tokens"] += int(input_tokens or 0)
        _usage["output_tokens"] += int(output_tokens or 0)


def get_usage() -> dict:
    """Snapshot of the live counters.  Read-only — callers should not
    mutate the returned dict."""
    with _usage_lock:
        return {
            "calls":         _usage["calls"],
            "input_tokens":  _usage["input_tokens"],
            "output_tokens": _usage["output_tokens"],
            "total_tokens":  _usage["input_tokens"] + _usage["output_tokens"],
        }


def get_remaining() -> int:
    """Tokens still allowed by the budget; -1 if no budget is set."""
    budget = _get_budget()
    if budget <= 0:
        return -1
    used = get_usage()["total_tokens"]
    return max(0, budget - used)


# ---------------------------------------------------------------------------
# Provider selection

def _select_provider() -> str:
    explicit = os.environ.get("ABCL_AI_PROVIDER")
    if explicit:
        return explicit.lower()
    if os.environ.get("GEMINI_API_KEY"):
        return "gemini"
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    raise RuntimeError(
        "No AI provider key set: export GEMINI_API_KEY or ANTHROPIC_API_KEY"
    )


def call_ai(
    prompt: str,
    *,
    system: Optional[str] = None,
    model: Optional[str] = None,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    priority: float = DEFAULT_PRIORITY,
) -> str:
    """Synchronously call the configured AI provider and return its
    response text.  Honours the AI-OS budget + concurrency knobs.

    `priority` is consulted only when ABCL_AI_MAX_CONCURRENT is set
    and the gate is full — lower number = served first."""
    _check_budget()
    gate = _get_concurrency_gate()
    if gate is not None:
        gate.acquire(priority)
    try:
        provider = _select_provider()
        if provider == "gemini":
            return _do_gemini(prompt, system=system,
                              model=model or DEFAULT_GEMINI_MODEL,
                              max_tokens=max_tokens)
        if provider == "anthropic":
            return _do_claude(prompt, system=system,
                              model=model or DEFAULT_ANTHROPIC_MODEL,
                              max_tokens=max_tokens)
        raise RuntimeError(f"Unknown ABCL_AI_PROVIDER: {provider!r}")
    finally:
        if gate is not None:
            gate.release()


# ---------------------------------------------------------------------------
# Per-provider callers — public so callers can pin a provider explicitly.
# These bypass the budget/concurrency wrappers; call_ai is the
# governed entry point.

def call_claude(prompt: str, **kwargs) -> str:
    return _do_claude(prompt, **kwargs)


def call_gemini(prompt: str, **kwargs) -> str:
    return _do_gemini(prompt, **kwargs)


def _do_claude(
    prompt: str,
    *,
    system: Optional[str] = None,
    model: str = DEFAULT_ANTHROPIC_MODEL,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> str:
    global _anthropic_client
    try:
        import anthropic  # type: ignore
    except Exception as e:
        raise RuntimeError(f"anthropic SDK not installed: {e!r}")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY is not set")
    if _anthropic_client is None:
        _anthropic_client = anthropic.Anthropic()
    kwargs = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system is not None:
        # Anthropic prompt caching: prefix match.  See Reviewer.abcl
        # for the specialist-actor pattern.
        kwargs["system"] = [
            {"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}
        ]
    response = _anthropic_client.messages.create(**kwargs)
    usage = getattr(response, "usage", None)
    if usage is not None:
        _record_usage(
            getattr(usage, "input_tokens", 0) or 0,
            getattr(usage, "output_tokens", 0) or 0,
        )
    return "".join(b.text for b in response.content if getattr(b, "type", None) == "text")


def _do_gemini(
    prompt: str,
    *,
    system: Optional[str] = None,
    model: str = DEFAULT_GEMINI_MODEL,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> str:
    global _gemini_client
    try:
        from google import genai  # type: ignore
        from google.genai import types  # type: ignore
    except Exception as e:
        raise RuntimeError(f"google-genai SDK not installed: {e!r}")
    if not os.environ.get("GEMINI_API_KEY"):
        raise RuntimeError("GEMINI_API_KEY is not set")
    if _gemini_client is None:
        _gemini_client = genai.Client()
    config_kwargs = {"max_output_tokens": max_tokens}
    if system is not None:
        config_kwargs["system_instruction"] = system
    config = types.GenerateContentConfig(**config_kwargs)
    response = _gemini_client.models.generate_content(
        model=model,
        contents=prompt,
        config=config,
    )
    meta = getattr(response, "usage_metadata", None)
    if meta is not None:
        _record_usage(
            getattr(meta, "prompt_token_count", 0) or 0,
            getattr(meta, "candidates_token_count", 0) or 0,
        )
    return response.text or ""
