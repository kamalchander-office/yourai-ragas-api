"""
HTTP client for YourAI Chat API.

POST {YOURAI_BASE_URL}/api/v1/chat/respond
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

import requests
from requests import Response

from yourai_chat.config import YourAIConfig, load_config
from yourai_chat.exceptions import (
    YourAIAuthError,
    YourAINetworkError,
    YourAIResponseError,
)

log = logging.getLogger(__name__)

_RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}


class YourAIChatClient:
    """Reusable YourAI chat API client with retries and structured logging."""

    def __init__(self, config: YourAIConfig | None = None) -> None:
        self.config = config or load_config()
        self._session = requests.Session()

    def _headers(self) -> dict[str, str]:
        return {
            "accept": "application/json",
            "Content-Type": "application/json",
            "X-Client-ID": self.config.client_id,
            "X-Client-Secret": self.config.client_secret,
            "X-Org-ID": self.config.org_id,
            "X-User-ID": self.config.user_id,
        }

    def resolve_conversation_id(self, conversation_id: str | None = None) -> str:
        """One thread per eval run (.env); per-case override optional."""
        return (
            conversation_id
            or self.config.default_conversation_id
            or str(uuid.uuid4())
        )

    def build_payload(
        self,
        *,
        message: str,
        intent_id: str | None = None,
        conversation_id: str | None = None,
        message_id: str | None = None,
        retrieval_mode: str | None = None,
    ) -> dict[str, Any]:
        return {
            "org_id": self.config.org_id,
            "user_id": self.config.user_id,
            "conversation_id": self.resolve_conversation_id(conversation_id),
            "message_id": message_id or str(uuid.uuid4()),
            "message": message,
            "intent_id": intent_id or "",
            "retrieval_mode": retrieval_mode or self.config.default_retrieval_mode,
        }

    def respond(
        self,
        *,
        message: str,
        intent_id: str | None = None,
        conversation_id: str | None = None,
        message_id: str | None = None,
        retrieval_mode: str | None = None,
    ) -> tuple[dict[str, Any], int, float, dict[str, str]]:
        """
        Send one chat message.

        Returns (response_json, http_status, latency_ms, request_meta).
        request_meta includes conversation_id and message_id sent to the API.
        """
        payload = self.build_payload(
            message=message,
            intent_id=intent_id,
            conversation_id=conversation_id,
            message_id=message_id,
            retrieval_mode=retrieval_mode,
        )

        log.info(
            "YourAI request conversation_id=%s message_id=%s intent_id=%s retrieval_mode=%s",
            payload["conversation_id"],
            payload["message_id"],
            payload.get("intent_id"),
            payload.get("retrieval_mode"),
        )

        last_error: Exception | None = None
        for attempt in range(1, self.config.max_retries + 1):
            started = time.perf_counter()
            try:
                response = self._session.post(
                    self.config.chat_url,
                    headers=self._headers(),
                    json=payload,
                    timeout=self.config.timeout_seconds,
                )
                latency_ms = (time.perf_counter() - started) * 1000
                data, status, latency = self._handle_response(response, latency_ms, attempt)
                meta = {
                    "conversation_id": payload["conversation_id"],
                    "message_id": payload["message_id"],
                }
                return data, status, latency, meta
            except YourAIResponseError as e:
                if "Retryable" in str(e) and attempt < self.config.max_retries:
                    last_error = e
                    continue
                raise
            except requests.Timeout:
                last_error = YourAINetworkError(
                    f"Request timed out after {self.config.timeout_seconds}s"
                )
                log.warning("YourAI timeout attempt=%s/%s", attempt, self.config.max_retries)
            except requests.RequestException as e:
                last_error = YourAINetworkError(str(e))
                log.warning(
                    "YourAI network error attempt=%s/%s error=%s",
                    attempt,
                    self.config.max_retries,
                    e,
                )

            if attempt < self.config.max_retries:
                time.sleep(self.config.retry_backoff_seconds * attempt)

        assert last_error is not None
        raise last_error

    def _handle_response(
        self,
        response: Response,
        latency_ms: float,
        attempt: int,
    ) -> tuple[dict[str, Any], int, float]:
        # internal helper — returns 3-tuple
        status = response.status_code
        log.info(
            "YourAI response status=%s latency_ms=%.0f attempt=%s",
            status,
            latency_ms,
            attempt,
        )

        if status in (401, 403):
            log.error("YourAI authentication failed status=%s", status)
            raise YourAIAuthError(
                f"Authentication failed (HTTP {status}). Check YOURAI_CLIENT_ID/SECRET and org/user headers."
            )

        if status in _RETRYABLE_STATUS:
            if attempt < self.config.max_retries:
                sleep_for = self.config.retry_backoff_seconds * attempt
                log.warning("YourAI retryable status=%s sleeping %.1fs", status, sleep_for)
                time.sleep(sleep_for)
                raise YourAIResponseError(f"Retryable HTTP {status}")
            log.error("YourAI retries exhausted status=%s", status)
            raise YourAIResponseError(f"HTTP {status} after {self.config.max_retries} attempts")

        if not response.ok:
            log.error("YourAI HTTP error status=%s body=%s", status, response.text[:300])
            raise YourAIResponseError(f"HTTP {status}: {response.text[:200]}")

        try:
            data = response.json()
        except ValueError as e:
            log.error("YourAI malformed JSON status=%s", status)
            raise YourAIResponseError("Response is not valid JSON") from e

        if not isinstance(data, dict):
            data = {"data": data}

        return data, status, latency_ms
