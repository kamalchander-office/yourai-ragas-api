"""YourAI Chat API errors."""

from __future__ import annotations


class YourAIChatError(Exception):
    """Base error for YourAI chat integration."""


class YourAIAuthError(YourAIChatError):
    """401/403 — invalid client credentials or org/user access."""


class YourAINetworkError(YourAIChatError):
    """Connection, timeout, or transport failure."""


class YourAIResponseError(YourAIChatError):
    """Non-success HTTP status or malformed JSON body."""
