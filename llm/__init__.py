"""Shared LLM providers (OpenAI, Google Gemini, OpenRouter)."""

from llm.router import chat, chat_json, get_active_model, get_provider

__all__ = ["chat", "chat_json", "get_active_model", "get_provider"]
