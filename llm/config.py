"""Read LLM settings from environment (.env)."""

import os

# openai | gemini | openrouter — single switch for generate_cases, main.py, and default judge
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai").strip().lower()

# OpenAI / ChatGPT
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# Google Gemini (REST API — same as Google AI Studio curl examples)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_API_BASE = os.getenv(
    "GEMINI_API_BASE",
    "https://generativelanguage.googleapis.com/v1beta",
)

# OpenRouter (OpenAI-compatible API — good when Gemini quota is exhausted)
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")
# RAGAs answer_similarity uses embeddings; must route through OpenRouter when judging there.
OPENROUTER_EMBEDDING_MODEL = os.getenv(
    "OPENROUTER_EMBEDDING_MODEL",
    "openai/text-embedding-3-small",
)
OPENROUTER_BASE_URL = os.getenv(
    "OPENROUTER_BASE_URL",
    "https://openrouter.ai/api/v1",
)
# OpenRouter bills against max_tokens; keep low for judge/JSON tasks (default SDK ≈ 16384).
OPENROUTER_MAX_TOKENS = int(os.getenv("OPENROUTER_MAX_TOKENS", "4096"))

# Optional: separate provider for RAGAs + DeepEval judge in run_eval.py (defaults to LLM_PROVIDER)
JUDGE_PROVIDER = os.getenv("JUDGE_PROVIDER", LLM_PROVIDER).strip().lower()
