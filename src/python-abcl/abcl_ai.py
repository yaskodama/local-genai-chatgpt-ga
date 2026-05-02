"""Anthropic Claude integration for the Python ABCL/c+ runtime.

Exposes a tiny synchronous surface that the interpreter wires up as
`ai_call(prompt)` and `ai_call_with_system(system, prompt)` builtins.
Each call is one round-trip to `messages.create`; the worker thread of
the calling actor blocks until the response arrives, which is fine
because every other actor keeps running on its own thread.

Default model is claude-opus-4-7.  Override per-call by reaching for
`call_claude(...)` directly with `model=`.
"""

import os
from typing import Optional

# Lazy-import the SDK so the module is still importable when anthropic
# isn't installed — the interpreter will surface a clear error only when
# someone actually invokes ai_call().
_client = None
_anthropic_import_error: Optional[Exception] = None
try:
    import anthropic  # type: ignore
except Exception as e:  # pragma: no cover - import failure path
    _anthropic_import_error = e


DEFAULT_MODEL = "claude-opus-4-7"
DEFAULT_MAX_TOKENS = 1024


def _get_client():
    global _client
    if _anthropic_import_error is not None:
        raise RuntimeError(
            "anthropic SDK is not installed: "
            f"{_anthropic_import_error!r}.  Install with `pip install anthropic`."
        )
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set.  Export it before running an AI sample."
        )
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


def call_claude(
    prompt: str,
    *,
    system: Optional[str] = None,
    model: str = DEFAULT_MODEL,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> str:
    """One synchronous round-trip to Claude.  Returns the concatenated
    text from any text blocks in the response."""
    client = _get_client()
    kwargs = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system is not None:
        kwargs["system"] = system
    response = client.messages.create(**kwargs)
    return "".join(b.text for b in response.content if getattr(b, "type", None) == "text")
