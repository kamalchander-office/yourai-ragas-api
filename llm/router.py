"""
Route chat requests based on LLM_PROVIDER in llm.config (single switch).

- openai     → OPENAI_API_KEY + OPENAI_MODEL
- gemini     → GEMINI_API_KEY + GEMINI_MODEL (unchanged REST path)
- openrouter → OPENROUTER_API_KEY + OPENROUTER_MODEL (OpenAI-compatible API)
"""

from __future__ import annotations

from llm import config
from llm import gemini_client, openai_client, openrouter_client


def get_provider() -> str:
    return config.LLM_PROVIDER


def get_active_model() -> str:
    if config.LLM_PROVIDER == "gemini":
        return config.GEMINI_MODEL
    if config.LLM_PROVIDER == "openrouter":
        return config.OPENROUTER_MODEL
    return config.OPENAI_MODEL


def _validate_provider() -> None:
    if config.LLM_PROVIDER not in ("openai", "gemini", "openrouter"):
        raise RuntimeError(
            f"LLM_PROVIDER must be 'openai', 'gemini', or 'openrouter', got {config.LLM_PROVIDER!r}"
        )


def chat(
    user_text: str,
    *,
    system_text: str | None = None,
    temperature: float = 0.2,
) -> str:
    _validate_provider()
    if config.LLM_PROVIDER == "gemini":
        return gemini_client.generate(
            user_text=user_text,
            system_text=system_text,
            temperature=temperature,
        )
    if config.LLM_PROVIDER == "openrouter":
        return openrouter_client.generate(
            user_text=user_text,
            system_text=system_text,
            temperature=temperature,
        )
    return openai_client.generate(
        user_text=user_text,
        system_text=system_text,
        temperature=temperature,
    )


def chat_json(
    user_text: str,
    *,
    system_text: str | None = None,
    temperature: float = 0.8,
) -> str:
    """Like chat(), but asks the model to return JSON (for generate_cases.py)."""
    _validate_provider()
    if config.LLM_PROVIDER == "gemini":
        return gemini_client.generate(
            user_text=user_text,
            system_text=system_text,
            temperature=temperature,
            json_mode=True,
        )
    if config.LLM_PROVIDER == "openrouter":
        return openrouter_client.generate(
            user_text=user_text,
            system_text=system_text,
            temperature=temperature,
            json_mode=True,
        )
    return openai_client.generate(
        user_text=user_text,
        system_text=system_text,
        temperature=temperature,
        json_mode=True,
    )
