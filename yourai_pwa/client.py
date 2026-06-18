"""HTTP client for YourAI PWA QA API (cookie authentication)."""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any

import requests

from yourai_chat.exceptions import YourAIAuthError, YourAINetworkError, YourAIResponseError
from yourai_pwa.auth import (
    _TRANSIENT_HTTP,
    clear_auth_cookies,
    ensure_authenticated,
    is_authenticated,
)
from yourai_pwa.config import PWAConfig, load_pwa_config
from yourai_pwa.intents import parse_intents_response
from yourai_pwa.response import normalize_chat_response

log = logging.getLogger(__name__)

# Login endpoints must not trigger auth-retry loops.
_NO_AUTH_RETRY_PREFIXES = ("/auth/login", "/auth/verify-mfa", "/auth/refresh")


class YourAIPWAClient:
    """Cookie-authenticated client for PWA /api/v1 endpoints."""

    def __init__(self, config: PWAConfig | None = None, *, auto_login: bool = True) -> None:
        self.config = config or load_pwa_config()
        self._auto_login = auto_login
        self._session = requests.Session()
        if self.config.has_cookies:
            from yourai_pwa.auth import apply_env_cookies

            apply_env_cookies(self._session, self.config)
        if auto_login and not is_authenticated(self._session):
            ensure_authenticated(self._session, self.config)

    def _url(self, path: str) -> str:
        return f"{self.config.api_root}{path}"

    @staticmethod
    def _auth_retry_allowed(path: str) -> bool:
        return not any(path.startswith(prefix) for prefix in _NO_AUTH_RETRY_PREFIXES)

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict | None = None,
        files: dict | None = None,
        data: dict | None = None,
        expected_status: int | tuple[int, ...] = (200, 201),
        _auth_retry: bool = True,
        _transient_retry: int | None = None,
    ) -> dict[str, Any]:
        if _transient_retry is None:
            _transient_retry = int(os.getenv("YOURAI_PWA_REQUEST_RETRIES", "2"))

        if not path.startswith("/auth/"):
            ensure_authenticated(self._session, self.config)

        last_response: requests.Response | None = None
        for attempt in range(_transient_retry + 1):
            try:
                response = self._session.request(
                    method,
                    self._url(path),
                    json=json_body,
                    files=files,
                    data=data,
                    timeout=self.config.timeout_seconds,
                )
            except requests.Timeout as e:
                if attempt < _transient_retry:
                    delay = 5 * (attempt + 1)
                    log.warning("%s timed out — retry %s/%s in %ss", path, attempt + 1, _transient_retry, delay)
                    time.sleep(delay)
                    continue
                raise YourAINetworkError(
                    f"Request timed out after {self.config.timeout_seconds}s: {path}"
                ) from e
            except requests.RequestException as e:
                raise YourAINetworkError(str(e)) from e

            last_response = response
            if response.status_code not in _TRANSIENT_HTTP or attempt >= _transient_retry:
                break
            delay = 5 * (attempt + 1)
            log.warning(
                "%s returned HTTP %s — retry %s/%s in %ss",
                path,
                response.status_code,
                attempt + 1,
                _transient_retry,
                delay,
            )
            time.sleep(delay)

        response = last_response
        assert response is not None

        if response.status_code in (401, 403) and _auth_retry and self._auth_retry_allowed(path):
            clear_auth_cookies(self._session)
            ensure_authenticated(self._session, self.config)
            if is_authenticated(self._session):
                return self._request(
                    method,
                    path,
                    json_body=json_body,
                    files=files,
                    data=data,
                    expected_status=expected_status,
                    _auth_retry=False,
                )

        if response.status_code in (401, 403):
            raise YourAIAuthError(
                f"PWA authentication failed (HTTP {response.status_code}) on {path}. "
                "Check YOURAI_PWA_LOGIN_* in .env or refresh cookies."
            )

        ok = expected_status if isinstance(expected_status, tuple) else (expected_status,)
        if response.status_code not in ok:
            raise YourAIResponseError(
                f"HTTP {response.status_code} on {path}: {response.text[:300]}"
            )

        if not response.content:
            return {}
        try:
            body = response.json()
        except ValueError as e:
            raise YourAIResponseError(f"Non-JSON response on {path}") from e
        return body if isinstance(body, dict) else {"data": body}

    def auth_me(self) -> dict[str, Any]:
        body = self._request("GET", "/auth/me")
        data = body.get("data") if isinstance(body.get("data"), dict) else body
        return data if isinstance(data, dict) else body

    def start_conversation(self, *, reuse: bool = False) -> str:
        body = self._request("POST", "/conversations/start", json_body={"reuse": reuse})
        data = body.get("data") if isinstance(body.get("data"), dict) else body
        conversation_id = data.get("conversationId") or data.get("conversation_id")
        if not conversation_id:
            raise YourAIResponseError(
                f"conversations/start missing conversationId: {body!r:.200}"
            )
        return str(conversation_id)

    def get_intents(self) -> list[dict[str, Any]]:
        body = self._request("GET", "/knowledge-base/intents")
        return parse_intents_response(body)

    def upload_document(
        self,
        file_path: Path,
        *,
        name: str | None = None,
        description: str = "",
    ) -> dict[str, Any]:
        path = Path(file_path).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Document not found: {path}")

        doc_name = name or path.stem
        with path.open("rb") as handle:
            body = self._request(
                "POST",
                "/vault/upload",
                files={"file": (path.name, handle)},
                data={
                    "name": doc_name,
                    "description": description,
                    "tags": "[]",
                },
                expected_status=201,
            )

        data = body.get("data") if isinstance(body.get("data"), dict) else body
        document_id = data.get("id") or data.get("documentId")
        if not document_id:
            raise YourAIResponseError(f"vault/upload missing document id: {body!r:.200}")
        return {
            "id": str(document_id),
            "name": data.get("name") or doc_name,
            "status": data.get("status"),
            "processing_status": data.get("processingStatus") or data.get("processing_status"),
            "raw": data,
        }

    def poll_document_ready(self, document_id: str) -> dict[str, Any]:
        """Poll until status=READY and processingStatus=ready (stable for 2 reads)."""
        stable_reads = 0
        last: dict[str, Any] = {}

        for attempt in range(1, self.config.poll_max_attempts + 1):
            body = self._request("GET", f"/vault/{document_id}/poll-status")
            data = body.get("data") if isinstance(body.get("data"), dict) else body
            last = data if isinstance(data, dict) else {}

            status = (last.get("status") or "").upper()
            processing = (last.get("processingStatus") or last.get("processing_status") or "").lower()

            if status == "READY" and processing == "ready":
                stable_reads += 1
                if stable_reads >= 2:
                    log.info("Document %s ready (attempt %s)", document_id, attempt)
                    return last
            else:
                stable_reads = 0

            log.info(
                "Document %s poll %s/%s: status=%s processing=%s",
                document_id,
                attempt,
                self.config.poll_max_attempts,
                status,
                processing,
            )
            time.sleep(self.config.poll_interval_seconds)

        raise YourAIResponseError(
            f"Document {document_id} not READY after {self.config.poll_max_attempts} polls. "
            f"Last state: {last}"
        )

    def set_conversation_scope(
        self,
        conversation_id: str,
        document_id: str,
        *,
        knowledge_pack_ids: list[str] | None = None,
    ) -> None:
        payload = {
            "document_ids": [document_id],
            "attached_document_ids": [document_id],
            "active_vault_document_id": None,
            "knowledge_pack_ids": knowledge_pack_ids or [],
        }
        self._request("POST", f"/conversations/{conversation_id}/scope", json_body=payload)

    def chat(
        self,
        *,
        conversation_id: str,
        message: str,
        intent_id: str,
        retrieval_mode: str | None = None,
    ) -> dict[str, Any]:
        body = self._request(
            "POST",
            "/chat",
            json_body={
                "conversationId": conversation_id,
                "message": message,
                "intentId": intent_id,
                "retrievalMode": retrieval_mode or self.config.default_retrieval_mode,
            },
        )
        return normalize_chat_response(body)
