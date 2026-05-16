"""Router model selection for each provider."""

import pytest


def test_get_active_model_openrouter(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-test")
    monkeypatch.setenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")

    import importlib

    import llm.config as cfg
    import llm.openrouter_client as orc
    import llm.router as router

    importlib.reload(cfg)
    importlib.reload(orc)
    importlib.reload(router)

    assert router.get_active_model() == "openai/gpt-4o-mini"
    assert router.get_provider() == "openrouter"


def test_get_active_model_gemini_unchanged(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "AIza-real-key-placeholder-not-used")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-2.5-flash")

    import importlib

    import llm.config as cfg
    import llm.gemini_client as gc
    import llm.router as router

    importlib.reload(cfg)
    importlib.reload(gc)
    importlib.reload(router)

    assert router.get_active_model() == "gemini-2.5-flash"


def test_is_openrouter_placeholder():
    from llm.env_validate import is_openrouter_placeholder

    assert is_openrouter_placeholder("") is True
    assert is_openrouter_placeholder("YOUR_OPENROUTER_API_KEY") is True
    assert is_openrouter_placeholder("sk-or-v1-abc123def456") is False
