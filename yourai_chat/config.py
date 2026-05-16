"""YourAI Chat API configuration from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class YourAIConfig:
    base_url: str
    client_id: str
    client_secret: str
    org_id: str
    user_id: str
    default_conversation_id: str
    default_retrieval_mode: str
    timeout_seconds: float
    max_retries: int
    retry_backoff_seconds: float

    @property
    def chat_url(self) -> str:
        base = self.base_url.rstrip("/")
        return f"{base}/api/v1/chat/respond"


def load_config() -> YourAIConfig:
    """Load YourAI credentials and settings from environment (.env)."""
    missing = [
        key
        for key, val in {
            "YOURAI_BASE_URL": os.getenv("YOURAI_BASE_URL"),
            "YOURAI_CLIENT_ID": os.getenv("YOURAI_CLIENT_ID"),
            "YOURAI_CLIENT_SECRET": os.getenv("YOURAI_CLIENT_SECRET"),
            "YOURAI_ORG_ID": os.getenv("YOURAI_ORG_ID"),
            "YOURAI_USER_ID": os.getenv("YOURAI_USER_ID"),
        }.items()
        if not val
    ]
    if missing:
        raise RuntimeError(
            f"Missing required environment variables: {', '.join(missing)}"
        )

    client_id = os.environ["YOURAI_CLIENT_ID"]
    client_secret = os.environ["YOURAI_CLIENT_SECRET"]
    if client_id.startswith("YOUR_") or client_secret.startswith("YOUR_"):
        raise RuntimeError(
            "YOURAI_CLIENT_ID / YOURAI_CLIENT_SECRET are still placeholders in .env. "
            "Use dev-client-id and dev-client-secret (see .env.example / API brief)."
        )

    return YourAIConfig(
        base_url=os.environ["YOURAI_BASE_URL"],
        client_id=os.environ["YOURAI_CLIENT_ID"],
        client_secret=os.environ["YOURAI_CLIENT_SECRET"],
        org_id=os.environ["YOURAI_ORG_ID"],
        user_id=os.environ["YOURAI_USER_ID"],
        default_conversation_id=os.getenv("YOURAI_CONVERSATION_ID", "").strip(),
        default_retrieval_mode=os.getenv("DEFAULT_RETRIEVAL_MODE", "hybrid"),
        timeout_seconds=float(os.getenv("YOURAI_TIMEOUT_SECONDS", "60")),
        max_retries=int(os.getenv("YOURAI_MAX_RETRIES", "3")),
        retry_backoff_seconds=float(os.getenv("YOURAI_RETRY_BACKOFF_SECONDS", "1.0")),
    )
