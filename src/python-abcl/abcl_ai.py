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
"""

import os
from typing import Optional


_anthropic_client = None
_gemini_client = None

DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
DEFAULT_ANTHROPIC_MODEL = "claude-opus-4-7"
DEFAULT_MAX_TOKENS = 1024


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
) -> str:
    """Synchronously call the configured AI provider and return its
    response text."""
    provider = _select_provider()
    if provider == "gemini":
        return call_gemini(prompt, system=system, model=model or DEFAULT_GEMINI_MODEL,
                           max_tokens=max_tokens)
    if provider == "anthropic":
        return call_claude(prompt, system=system, model=model or DEFAULT_ANTHROPIC_MODEL,
                           max_tokens=max_tokens)
    raise RuntimeError(f"Unknown ABCL_AI_PROVIDER: {provider!r}")


# ---------------------------------------------------------------------------
# Per-provider callers — public so a caller can pin a provider explicitly.

def call_claude(
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
        kwargs["system"] = system
    response = _anthropic_client.messages.create(**kwargs)
    return "".join(b.text for b in response.content if getattr(b, "type", None) == "text")


def call_gemini(
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
    return response.text or ""
