"""
OpenRouter — OpenAI-compatible chat completions (shared SDK, different base URL).

Uses OPENROUTER_API_KEY and OPENROUTER_MODEL from llm.config.
Default model openai/gpt-4o-mini: low cost, reliable for eval / JSON tasks.
"""

from __future__ import annotations

from openai import OpenAI

from llm import config

_client: OpenAI | None = None


def get_client() -> OpenAI:
    global _client
    if not config.OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY is not set in .env")
    if _client is None:
        _client = OpenAI(
            api_key=config.OPENROUTER_API_KEY,
            base_url=config.OPENROUTER_BASE_URL.rstrip("/"),
        )
    return _client


def generate(
    *,
    user_text: str,
    system_text: str | None = None,
    temperature: float = 0.2,
    json_mode: bool = False,
) -> str:
    """Single-turn chat completion via OpenRouter. Returns assistant text."""
    messages: list[dict[str, str]] = []
    if system_text:
        messages.append({"role": "system", "content": system_text})
    messages.append({"role": "user", "content": user_text})

    kwargs: dict = {
        "model": config.OPENROUTER_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": config.OPENROUTER_MAX_TOKENS,
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    response = get_client().chat.completions.create(**kwargs)
    return response.choices[0].message.content or ""
