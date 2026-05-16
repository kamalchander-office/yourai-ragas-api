"""
OpenAI / ChatGPT chat completions.

Keeps the same behaviour as the original main.py and generate_cases.py calls.
"""

from __future__ import annotations

from openai import OpenAI

from llm import config

_client: OpenAI | None = None


def get_client() -> OpenAI:
    global _client
    if not config.OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not set in .env")
    if _client is None:
        _client = OpenAI(api_key=config.OPENAI_API_KEY)
    return _client


def generate(
    *,
    user_text: str,
    system_text: str | None = None,
    temperature: float = 0.2,
    json_mode: bool = False,
) -> str:
    """Single-turn chat completion. Returns assistant text."""
    messages: list[dict[str, str]] = []
    if system_text:
        messages.append({"role": "system", "content": system_text})
    messages.append({"role": "user", "content": user_text})

    kwargs: dict = {
        "model": config.OPENAI_MODEL,
        "messages": messages,
        "temperature": temperature,
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    response = get_client().chat.completions.create(**kwargs)
    return response.choices[0].message.content or ""
