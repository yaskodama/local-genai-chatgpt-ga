"""AI provider integration for the Python AIPL runtime.

`call_ai(prompt, system=...)` is the synchronous primitive that the
interpreter wires up as `ai_call` / `ai_call_with_system`.  It
auto-dispatches to whichever provider has its key in the environment:

    GEMINI_API_KEY    -> google-genai (default model: gemini-2.5-flash)
    ANTHROPIC_API_KEY -> anthropic    (default model: claude-opus-4-7)
    OPENAI_API_KEY    -> openai       (default model: gpt-4o-mini)

When more than one is set, set `ABCL_AI_PROVIDER=gemini|anthropic|openai`
to pick explicitly.  SDKs are imported lazily so the module is still
importable on a machine with none installed; the error only surfaces
when an .abcl program actually invokes ai_call().

AI-OS governance knobs (env vars, all optional):

    ABCL_AI_TOKEN_BUDGET=N   total prompt+completion tokens cap; calls
                             past the cap raise BudgetExceeded
    ABCL_AI_MAX_CONCURRENT=N at most N AI calls in flight at once;
                             excess actors block on a semaphore (FIFO)

`get_usage()` returns the live counter; the interpreter exposes it as
the `ai_usage()` builtin.
"""

import itertools
import json
import os
import random
import tempfile
import threading
import time
from typing import List, Optional


_anthropic_client = None
_gemini_client = None
_openai_client = None

DEFAULT_GEMINI_MODEL    = "gemini-2.5-flash"
DEFAULT_ANTHROPIC_MODEL = "claude-opus-4-7"
DEFAULT_OPENAI_MODEL    = "gpt-4o-mini"
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
_usage = {"calls": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}


def _aipl_env(name: str, default: str = "") -> str:
    """Read an env var, accepting both AIPL_* (new) and ABCL_* (legacy)
    spellings. AIPL_* wins when both are set. Pass the AIPL_-prefixed name."""
    aipl_value = os.environ.get(name, "").strip()
    if aipl_value:
        return aipl_value
    if name.startswith("AIPL_"):
        legacy = "ABCL_" + name[len("AIPL_"):]
        return os.environ.get(legacy, default).strip() or default
    return os.environ.get(name, default).strip() or default


def _usage_file_path() -> Optional[str]:
    p = _aipl_env("AIPL_AI_USAGE_FILE", "")
    return p or None


def _load_persistent_usage() -> None:
    """Load cumulative counters from ABCL_AI_USAGE_FILE if set.  Called
    once on first ai_ai_call import; if the file is missing or
    malformed we just start from zero."""
    path = _usage_file_path()
    if not path:
        return
    try:
        with open(path) as f:
            data = json.load(f)
    except FileNotFoundError:
        return
    except (OSError, json.JSONDecodeError):
        # Don't blow up startup over a corrupt file — start fresh.
        return
    for k in ("calls", "input_tokens", "output_tokens"):
        v = data.get(k, 0)
        if isinstance(v, int):
            _usage[k] = v
    cost = data.get("cost_usd", 0.0)
    if isinstance(cost, (int, float)):
        _usage["cost_usd"] = float(cost)


def _save_persistent_usage_locked() -> None:
    """Atomic JSON write.  Caller must hold _usage_lock so the snapshot
    is consistent."""
    path = _usage_file_path()
    if not path:
        return
    snapshot = {
        "calls":         _usage["calls"],
        "input_tokens":  _usage["input_tokens"],
        "output_tokens": _usage["output_tokens"],
        "cost_usd":      _usage["cost_usd"],
    }
    dirn = os.path.dirname(os.path.abspath(path)) or "."
    try:
        os.makedirs(dirn, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".usage_", dir=dirn)
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(snapshot, f)
            os.replace(tmp, path)
        except Exception:
            try: os.unlink(tmp)
            except OSError: pass
            raise
    except OSError:
        # Persistence is best-effort; don't fail the API call.
        pass


_load_persistent_usage()


# Per-million-token pricing in USD, sourced from each provider's
# pricing page (cached 2026-04).  Lookup falls back to (0, 0) for
# unrecognised models — the call still runs, it just isn't priced.
PRICING_USD_PER_M_TOKENS = {
    # Anthropic
    "claude-opus-4-7":   (5.00, 25.00),
    "claude-opus-4-6":   (5.00, 25.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-haiku-4-5":  (1.00,  5.00),
    # Gemini
    "gemini-2.5-pro":         (1.25, 10.00),
    "gemini-2.5-flash":       (0.075, 0.30),
    "gemini-2.5-flash-lite":  (0.10,  0.40),
    # OpenAI (cached 2026-04)
    "gpt-4o":                 (2.50, 10.00),
    "gpt-4o-mini":            (0.15,  0.60),
    "gpt-4-turbo":            (10.00, 30.00),
    "o1-mini":                (1.10,  4.40),
    "o3-mini":                (1.10,  4.40),
}


def _price_for(model: str) -> tuple:
    return PRICING_USD_PER_M_TOKENS.get(model, (0.0, 0.0))


def _cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    in_p, out_p = _price_for(model)
    return (input_tokens / 1_000_000.0) * in_p + (output_tokens / 1_000_000.0) * out_p

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
    raw = _aipl_env(name, "")
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _get_budget() -> int:
    return _int_env("AIPL_AI_TOKEN_BUDGET", 0)


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


def _record_usage(model: str, input_tokens: int, output_tokens: int) -> None:
    with _usage_lock:
        _usage["calls"]         += 1
        _usage["input_tokens"]  += int(input_tokens or 0)
        _usage["output_tokens"] += int(output_tokens or 0)
        _usage["cost_usd"]      += _cost_usd(model, input_tokens or 0,
                                             output_tokens or 0)
        _save_persistent_usage_locked()
    # Best-effort fan-out to dashboard subscribers; never block the
    # caller if the broker isn't loaded.
    try:
        from aipl_events import publish
        publish("ai_call",
                model=model,
                input_tokens=int(input_tokens or 0),
                output_tokens=int(output_tokens or 0))
    except Exception:
        pass


def get_usage() -> dict:
    """Snapshot of the live counters.  Read-only — callers should not
    mutate the returned dict."""
    with _usage_lock:
        return {
            "calls":         _usage["calls"],
            "input_tokens":  _usage["input_tokens"],
            "output_tokens": _usage["output_tokens"],
            "total_tokens":  _usage["input_tokens"] + _usage["output_tokens"],
            "cost_usd":      _usage["cost_usd"],
        }


def get_cost_usd() -> float:
    with _usage_lock:
        return _usage["cost_usd"]


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
    explicit = _aipl_env("AIPL_AI_PROVIDER", "")
    if explicit:
        return explicit.lower()
    if os.environ.get("GEMINI_API_KEY"):
        return "gemini"
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"
    raise RuntimeError(
        "No AI provider key set: export GEMINI_API_KEY, ANTHROPIC_API_KEY, "
        "or OPENAI_API_KEY (or ABCL_AI_PROVIDER=mock for offline tests)"
    )


def _normalize_images(images) -> list:
    """Accept a heterogeneous image list and return uniform [{'mime_type', 'data_b64'}].
    Each input element may be:
      - bytes / bytearray             -> mime guessed by sniff (PNG/JPEG/...)
      - list/tuple of int (0..255)    -> same; raw bytes
      - dict with 'mime_type' + 'data_b64' (already normalised)
      - dict with 'path' / 'pil' (an _AiplImage from the interpreter)"""
    import base64
    if not images:
        return []
    out = []
    for item in images:
        mime = None
        raw = None
        if isinstance(item, (bytes, bytearray)):
            raw = bytes(item)
        elif isinstance(item, (list, tuple)) and all(isinstance(x, int) for x in item):
            raw = bytes(item)
        elif isinstance(item, dict):
            if "mime_type" in item and "data_b64" in item:
                out.append({"mime_type": item["mime_type"], "data_b64": item["data_b64"]})
                continue
            if "_pil_bytes" in item:
                raw = item["_pil_bytes"]
                mime = item.get("mime_type", "image/png")
            elif "path" in item:
                with open(item["path"], "rb") as f:
                    raw = f.read()
                mime = item.get("mime_type")
        if raw is None:
            continue
        if mime is None:
            mime = _sniff_mime(raw)
        out.append({"mime_type": mime, "data_b64": base64.b64encode(raw).decode("ascii")})
    return out


def _sniff_mime(buf: bytes) -> str:
    if buf.startswith(b"\x89PNG\r\n\x1a\n"): return "image/png"
    if buf[:3] == b"\xff\xd8\xff":           return "image/jpeg"
    if buf[:6] in (b"GIF87a", b"GIF89a"):    return "image/gif"
    if buf[:4] == b"RIFF" and buf[8:12] == b"WEBP": return "image/webp"
    return "application/octet-stream"


def _do_mock(
    prompt: str,
    *,
    system: Optional[str] = None,
    model: str = "mock",
    max_tokens: int = DEFAULT_MAX_TOKENS,
    images: Optional[list] = None,
) -> str:
    """Offline test provider — no network, no key required.  Echoes a
    short canned reply and ticks the usage counters with a rough
    token estimate so the dashboard still has data to render."""
    head = (prompt or "")[:60].replace("\n", " ")
    sys_tag = "" if system is None else f" sys=({system[:20]}...)"
    img_tag = ""
    norm = _normalize_images(images or [])
    if norm:
        kinds = ", ".join(i["mime_type"] for i in norm)
        img_tag = f" img=({kinds})"
    response = f"[mock] reply{sys_tag}{img_tag} for: {head}"
    # Rough 4-chars-per-token approximation.
    _record_usage(model, max(1, len(prompt) // 4), max(1, len(response) // 4))
    return response


def _fallback_models() -> List[str]:
    raw = _aipl_env("AIPL_AI_FALLBACK_MODELS", "")
    if not raw:
        return []
    return [m.strip() for m in raw.split(",") if m.strip()]


def _is_retryable(exc: BaseException) -> bool:
    """Crude error classifier: retry on rate limit / overload / transient
    server errors.  Anthropic and google-genai both raise SDK-typed
    exceptions whose class names follow these patterns; matching by
    name keeps abcl_ai independent of either SDK."""
    name = type(exc).__name__
    if name in {
        "RateLimitError", "APIStatusError", "InternalServerError",
        "OverloadedError", "APIConnectionError", "APITimeoutError",
        "ResourceExhausted", "ServerError", "ServiceUnavailable",
        "DeadlineExceeded", "Unavailable",
    }:
        return True
    msg = str(exc).lower()
    return any(s in msg for s in (
        " 429", "rate limit", "rate_limit",
        " 500", " 502", " 503", " 504",
        "overloaded", "unavailable", "deadline", "timeout",
    ))


def _resolve_provider(p) -> Optional[str]:
    """Map AIPL-side provider id (int 1..3 / string 'gemini'|'anthropic'|
    'claude'|'openai'|'mock'|'auto') to the canonical lowercase name. None
    or 0/'auto' means 'auto-select' (use the env var / API-key heuristic)."""
    if p is None or p == 0:
        return None
    if isinstance(p, int):
        return {1: "gemini", 2: "anthropic", 3: "openai"}.get(p)
    if isinstance(p, str):
        s = p.strip().lower()
        if s in ("auto", ""):
            return None
        if s in ("claude", "claudecode", "claude-code"):
            return "anthropic"
        if s in ("gpt", "chatgpt"):
            return "openai"
        if s in ("gemini", "anthropic", "openai", "mock"):
            return s
    return None


def call_ai(
    prompt: str,
    *,
    system: Optional[str] = None,
    model: Optional[str] = None,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    priority: float = DEFAULT_PRIORITY,
    provider_override: Optional[str] = None,
    images: Optional[list] = None,
) -> str:
    """Synchronously call the configured AI provider and return its
    response text.  Honours the AI-OS budget + concurrency + fallback
    knobs.

    `priority` is consulted only when ABCL_AI_MAX_CONCURRENT is set
    and the gate is full — lower number = served first.

    On a retryable failure (rate-limit / 5xx / transient network),
    `call_ai` walks ABCL_AI_FALLBACK_MODELS in order with exponential
    backoff before giving up.  When the env var is empty, behaviour
    is identical to a single-shot call."""
    _check_budget()
    gate = _get_concurrency_gate()
    if gate is not None:
        gate.acquire(priority)
    try:
        # Env-mock wins to keep tests / demos token-free even when callers
        # ask for a specific provider via provider_override.
        forced_env = (_aipl_env("AIPL_AI_PROVIDER", "") or "").lower()
        if forced_env == "mock":
            provider = "mock"
        elif provider_override:
            provider = provider_override
        else:
            provider = _select_provider()
        primary = model or {
            "gemini":    DEFAULT_GEMINI_MODEL,
            "anthropic": DEFAULT_ANTHROPIC_MODEL,
            "openai":    DEFAULT_OPENAI_MODEL,
            "mock":      "mock",
        }.get(provider, DEFAULT_GEMINI_MODEL)
        models = [primary] + [m for m in _fallback_models() if m != primary]

        last_exc: Optional[BaseException] = None
        for i, m in enumerate(models):
            try:
                if provider == "gemini":
                    return _do_gemini(prompt, system=system, model=m, max_tokens=max_tokens, images=images)
                if provider == "anthropic":
                    return _do_claude(prompt, system=system, model=m, max_tokens=max_tokens, images=images)
                if provider == "openai":
                    return _do_openai(prompt, system=system, model=m, max_tokens=max_tokens, images=images)
                if provider == "mock":
                    return _do_mock(prompt, system=system, model=m, max_tokens=max_tokens, images=images)
                raise RuntimeError(f"Unknown ABCL_AI_PROVIDER: {provider!r}")
            except BaseException as e:
                last_exc = e
                if i == len(models) - 1 or not _is_retryable(e):
                    raise
                # Exponential backoff with jitter: 0.5s, 1s, 2s, 4s, ...
                delay = (0.5 * (2 ** i)) + random.uniform(0, 0.25)
                print(f"[ai_fallback] {m} failed ({type(e).__name__}); "
                      f"retrying with {models[i+1]} after {delay:.2f}s")
                time.sleep(delay)
        # Should be unreachable
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("call_ai: no models tried")
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


def call_openai(prompt: str, **kwargs) -> str:
    return _do_openai(prompt, **kwargs)


# ---------------------------------------------------------------------------
# Multi-turn chat.  `messages` follows the OpenAI shape:
#   [{"role": "user" | "assistant", "content": "..."} , ...]
# Each provider's SDK reshapes as needed (Gemini swaps "assistant" ->
# "model" and wraps in {parts: [{text}]}).

def chat_ai(messages: list, *, system: Optional[str] = None,
            model: Optional[str] = None,
            max_tokens: int = DEFAULT_MAX_TOKENS) -> str:
    _check_budget()
    gate = _get_concurrency_gate()
    if gate is not None:
        gate.acquire()
    try:
        provider = _select_provider()
        chosen = model or {
            "gemini":    DEFAULT_GEMINI_MODEL,
            "anthropic": DEFAULT_ANTHROPIC_MODEL,
            "openai":    DEFAULT_OPENAI_MODEL,
            "mock":      "mock",
        }.get(provider, DEFAULT_GEMINI_MODEL)
        if provider == "gemini":
            return _chat_gemini(messages, system, chosen, max_tokens)
        if provider == "anthropic":
            return _chat_claude(messages, system, chosen, max_tokens)
        if provider == "openai":
            return _chat_openai(messages, system, chosen, max_tokens)
        if provider == "mock":
            last_user = next((m.get("content", "")
                              for m in reversed(messages)
                              if m.get("role") == "user"), "")
            tag = "" if system is None else f" [sys={system[:18]}…]"
            reply = f"[mock]{tag} ({len(messages)} turns) — re: {last_user[:60]}"
            _record_usage(chosen, max(1, sum(len(m.get('content', '')) for m in messages) // 4),
                          max(1, len(reply) // 4))
            return reply
        raise RuntimeError(f"Unknown ABCL_AI_PROVIDER: {provider!r}")
    finally:
        if gate is not None:
            gate.release()


def _chat_gemini(messages, system, model, max_tokens):
    global _gemini_client
    from google import genai  # type: ignore
    from google.genai import types  # type: ignore
    if _gemini_client is None:
        _gemini_client = genai.Client()
    contents = []
    for m in messages:
        role = "user" if m.get("role") == "user" else "model"
        contents.append({"role": role,
                         "parts": [{"text": m.get("content", "")}]})
    cfg_kwargs = {"max_output_tokens": max_tokens}
    if system is not None:
        cfg_kwargs["system_instruction"] = system
    response = _gemini_client.models.generate_content(
        model=model, contents=contents,
        config=types.GenerateContentConfig(**cfg_kwargs),
    )
    meta = getattr(response, "usage_metadata", None)
    if meta is not None:
        _record_usage(model,
                      getattr(meta, "prompt_token_count", 0) or 0,
                      getattr(meta, "candidates_token_count", 0) or 0)
    return response.text or ""


def _chat_claude(messages, system, model, max_tokens):
    global _anthropic_client
    import anthropic  # type: ignore
    if _anthropic_client is None:
        _anthropic_client = anthropic.Anthropic()
    kwargs = {"model": model, "max_tokens": max_tokens, "messages": messages}
    if system is not None:
        kwargs["system"] = [{"type": "text", "text": system,
                             "cache_control": {"type": "ephemeral"}}]
    response = _anthropic_client.messages.create(**kwargs)
    usage = getattr(response, "usage", None)
    if usage is not None:
        _record_usage(model,
                      getattr(usage, "input_tokens", 0) or 0,
                      getattr(usage, "output_tokens", 0) or 0)
    return "".join(b.text for b in response.content
                   if getattr(b, "type", None) == "text")


def _chat_openai(messages, system, model, max_tokens):
    global _openai_client
    import openai  # type: ignore
    if _openai_client is None:
        _openai_client = openai.OpenAI()
    msgs = []
    if system is not None:
        msgs.append({"role": "system", "content": system})
    msgs.extend(messages)
    response = _openai_client.chat.completions.create(
        model=model, max_completion_tokens=max_tokens, messages=msgs,
    )
    usage = getattr(response, "usage", None)
    if usage is not None:
        _record_usage(model,
                      getattr(usage, "prompt_tokens", 0) or 0,
                      getattr(usage, "completion_tokens", 0) or 0)
    choice = response.choices[0] if response.choices else None
    if choice is None:
        return ""
    msg = getattr(choice, "message", None)
    return (getattr(msg, "content", None) or "") if msg is not None else ""


# ---------------------------------------------------------------------------
# Streaming.  Each provider's SDK exposes a different streaming API;
# we yield plain strings here so the interpreter can feed them
# chunk-by-chunk into the calling actor.

def stream_ai(
    prompt: str,
    *,
    system: Optional[str] = None,
    model: Optional[str] = None,
    max_tokens: int = DEFAULT_MAX_TOKENS,
):
    """Generator yielding response text chunks from the active
    provider.  Token counters are not updated for streaming calls
    (yet) — the chunk yields finish before the SDK exposes usage."""
    provider = _select_provider()
    if provider == "gemini":
        yield from _stream_gemini(prompt, system,
                                  model or DEFAULT_GEMINI_MODEL, max_tokens)
    elif provider == "anthropic":
        yield from _stream_claude(prompt, system,
                                  model or DEFAULT_ANTHROPIC_MODEL, max_tokens)
    elif provider == "openai":
        yield from _stream_openai(prompt, system,
                                  model or DEFAULT_OPENAI_MODEL, max_tokens)
    elif provider == "mock":
        yield "[mock] streaming "
        for word in (prompt or "").split()[:8]:
            yield word + " "
    else:
        raise RuntimeError(f"Unknown ABCL_AI_PROVIDER: {provider!r}")


def _stream_gemini(prompt, system, model, max_tokens):
    global _gemini_client
    from google import genai  # type: ignore
    from google.genai import types  # type: ignore
    if _gemini_client is None:
        _gemini_client = genai.Client()
    config_kwargs = {"max_output_tokens": max_tokens}
    if system is not None:
        config_kwargs["system_instruction"] = system
    config = types.GenerateContentConfig(**config_kwargs)
    stream = _gemini_client.models.generate_content_stream(
        model=model, contents=prompt, config=config,
    )
    for chunk in stream:
        text = getattr(chunk, "text", None) or ""
        if text:
            yield text


def _stream_claude(prompt, system, model, max_tokens):
    global _anthropic_client
    import anthropic  # type: ignore
    if _anthropic_client is None:
        _anthropic_client = anthropic.Anthropic()
    kwargs = {
        "model": model, "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system is not None:
        kwargs["system"] = [
            {"type": "text", "text": system,
             "cache_control": {"type": "ephemeral"}},
        ]
    with _anthropic_client.messages.stream(**kwargs) as stream:
        for text in stream.text_stream:
            if text:
                yield text


def _stream_openai(prompt, system, model, max_tokens):
    global _openai_client
    import openai  # type: ignore
    if _openai_client is None:
        _openai_client = openai.OpenAI()
    messages = []
    if system is not None:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    stream = _openai_client.chat.completions.create(
        model=model, max_completion_tokens=max_tokens,
        messages=messages, stream=True,
    )
    for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        text = getattr(delta, "content", None) or ""
        if text:
            yield text


def _do_claude(
    prompt: str,
    *,
    system: Optional[str] = None,
    model: str = DEFAULT_ANTHROPIC_MODEL,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    images: Optional[list] = None,
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
    norm_images = _normalize_images(images or [])
    if norm_images:
        content_blocks = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": img["mime_type"],
                    "data": img["data_b64"],
                },
            }
            for img in norm_images
        ]
        content_blocks.append({"type": "text", "text": prompt})
        user_content = content_blocks
    else:
        user_content = prompt
    kwargs = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": user_content}],
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
            model,
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
    images: Optional[list] = None,
) -> str:
    import base64
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
    norm_images = _normalize_images(images or [])
    if norm_images:
        parts = []
        for img in norm_images:
            parts.append(types.Part.from_bytes(
                data=base64.b64decode(img["data_b64"]),
                mime_type=img["mime_type"],
            ))
        parts.append(prompt)
        contents = parts
    else:
        contents = prompt
    response = _gemini_client.models.generate_content(
        model=model,
        contents=contents,
        config=config,
    )
    meta = getattr(response, "usage_metadata", None)
    if meta is not None:
        _record_usage(
            model,
            getattr(meta, "prompt_token_count", 0) or 0,
            getattr(meta, "candidates_token_count", 0) or 0,
        )
    return response.text or ""


def _do_openai(
    prompt: str,
    *,
    system: Optional[str] = None,
    model: str = DEFAULT_OPENAI_MODEL,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    images: Optional[list] = None,
) -> str:
    global _openai_client
    try:
        import openai  # type: ignore
    except Exception as e:
        raise RuntimeError(f"openai SDK not installed: {e!r}")
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not set")
    if _openai_client is None:
        _openai_client = openai.OpenAI()

    messages = []
    if system is not None:
        messages.append({"role": "system", "content": system})
    norm_images = _normalize_images(images or [])
    if norm_images:
        user_parts = []
        for img in norm_images:
            user_parts.append({
                "type": "image_url",
                "image_url": {"url": f"data:{img['mime_type']};base64,{img['data_b64']}"},
            })
        user_parts.append({"type": "text", "text": prompt})
        messages.append({"role": "user", "content": user_parts})
    else:
        messages.append({"role": "user", "content": prompt})

    # Some newer OpenAI models (o1*, o3*) require max_completion_tokens
    # rather than max_tokens; the Chat Completions endpoint accepts the
    # newer name across the board, so use it unconditionally.
    response = _openai_client.chat.completions.create(
        model=model,
        max_completion_tokens=max_tokens,
        messages=messages,
    )
    usage = getattr(response, "usage", None)
    if usage is not None:
        _record_usage(
            model,
            getattr(usage, "prompt_tokens", 0) or 0,
            getattr(usage, "completion_tokens", 0) or 0,
        )
    choice = response.choices[0] if response.choices else None
    if choice is None:
        return ""
    msg = getattr(choice, "message", None)
    return (getattr(msg, "content", None) or "") if msg is not None else ""
