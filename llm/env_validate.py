"""Detect placeholder API keys in .env (OpenAI, Gemini, OpenRouter)."""

_OPENAI_PLACEHOLDER_PREFIXES = (
    "sk-replace",
    "sk-your-openai",
    "sk-your-own",
)
_GEMINI_PLACEHOLDER_MARKERS = (
    "YOUR_GEMINI",
    "your-gemini-api-key",
)
_OPENROUTER_PLACEHOLDER_MARKERS = (
    "YOUR_OPENROUTER",
    "your-openrouter-api-key",
    "sk-or-v1-replace",
)


def is_openai_placeholder(key: str) -> bool:
    if not key or not key.strip():
        return True
    k = key.strip()
    return any(k.startswith(p) for p in _OPENAI_PLACEHOLDER_PREFIXES)


def is_gemini_placeholder(key: str) -> bool:
    if not key or not key.strip():
        return True
    k = key.strip()
    return any(m in k for m in _GEMINI_PLACEHOLDER_MARKERS)


def is_openrouter_placeholder(key: str) -> bool:
    if not key or not key.strip():
        return True
    k = key.strip()
    return any(m in k for m in _OPENROUTER_PLACEHOLDER_MARKERS)
