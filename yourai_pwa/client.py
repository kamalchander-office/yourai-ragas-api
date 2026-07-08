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
from yourai_pwa.vault import (
    document_is_ready,
    parse_document_id_from_url,
    vault_folder_list_data,
    vault_list_data,
)

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

    def list_vault_documents(
        self,
        *,
        page: int = 1,
        limit: int = 100,
        tab: str = "ALL",
        folder_id: str | None = None,
    ) -> list[dict[str, Any]]:
        query = f"/vault?page={page}&limit={limit}&tab={tab}"
        if folder_id:
            query += f"&folderId={folder_id}"
        body = self._request("GET", query)
        return vault_list_data(body)

    def get_vault_document(self, document_id: str) -> dict[str, Any]:
        body = self._request("GET", f"/vault/{document_id}")
        data = body.get("data") if isinstance(body.get("data"), dict) else body
        if not isinstance(data, dict):
            raise YourAIResponseError(f"GET /vault/{document_id} returned unexpected body")
        return data

    def list_vault_folders(self) -> list[dict[str, Any]]:
        body = self._request("GET", "/vault/folders")
        return vault_folder_list_data(body)

    def download_url(self, url: str) -> bytes:
        """Download bytes from a vault media fileUrl (uses PWA cookie session)."""
        ensure_authenticated(self._session, self.config)
        try:
            response = self._session.get(url, timeout=self.config.timeout_seconds)
        except requests.RequestException as e:
            raise YourAINetworkError(f"Download failed for {url[:80]}: {e}") from e
        if response.status_code != 200:
            raise YourAIResponseError(
                f"Download HTTP {response.status_code} for {url[:80]}: {response.text[:200]}"
            )
        return response.content

    @staticmethod
    def _match_token(value: str, candidate: str) -> bool:
        left = value.strip().lower()
        right = candidate.strip().lower()
        return left == right or left in right or right in left

    def resolve_vault_documents(
        self,
        *,
        document_ids: list[str] | None = None,
        document_names: list[str] | None = None,
        file_urls: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Resolve vault records by UUID, display name, or media URL."""
        wanted_ids: list[str] = [d.strip() for d in (document_ids or []) if d.strip()]
        for url in file_urls or []:
            parsed = parse_document_id_from_url(url)
            if parsed and parsed not in wanted_ids:
                wanted_ids.append(parsed)

        wanted_names = [n.strip() for n in (document_names or []) if n.strip()]
        if not wanted_ids and not wanted_names:
            return []

        all_docs = self.list_vault_documents(limit=100)
        by_id = {str(d.get("id")): d for d in all_docs if d.get("id")}

        resolved: list[dict[str, Any]] = []
        seen: set[str] = set()

        for doc_id in wanted_ids:
            doc = by_id.get(doc_id)
            if not doc:
                try:
                    doc = self.get_vault_document(doc_id)
                except YourAIResponseError:
                    doc = None
            if not doc:
                raise YourAIResponseError(f"Vault document not found: {doc_id}")
            if doc_id not in seen:
                resolved.append(doc)
                seen.add(doc_id)

        for name in wanted_names:
            matches = [
                d
                for d in all_docs
                if self._match_token(name, str(d.get("name") or ""))
            ]
            if not matches:
                raise YourAIResponseError(f"Vault document name not found: {name!r}")
            if len(matches) > 1:
                log.warning(
                    "Multiple vault documents match name %r — using first (id=%s)",
                    name,
                    matches[0].get("id"),
                )
            doc = matches[0]
            doc_id = str(doc.get("id"))
            if doc_id not in seen:
                resolved.append(doc)
                seen.add(doc_id)

        return resolved

    def resolve_vault_folder(
        self,
        *,
        folder_id: str | None = None,
        folder_name: str | None = None,
    ) -> dict[str, Any] | None:
        fid = (folder_id or "").strip()
        fname = (folder_name or "").strip()
        if not fid and not fname:
            return None

        folders = self.list_vault_folders()
        if fid:
            for folder in folders:
                if str(folder.get("id")) == fid:
                    return folder
            raise YourAIResponseError(f"Vault folder not found: {fid}")

        matches = [
            f
            for f in folders
            if self._match_token(fname, str(f.get("name") or ""))
        ]
        if not matches:
            raise YourAIResponseError(f"Vault folder name not found: {fname!r}")
        if len(matches) > 1:
            log.warning(
                "Multiple vault folders match name %r — using first (id=%s)",
                fname,
                matches[0].get("id"),
            )
        return matches[0]

    def set_conversation_scope_vault(
        self,
        conversation_id: str,
        *,
        document_ids: list[str] | None = None,
        folder_id: str | None = None,
        active_vault_document_id: str | None = None,
        knowledge_pack_ids: list[str] | None = None,
    ) -> None:
        """Attach vault document(s) and/or a folder to conversation scope."""
        doc_ids = [d.strip() for d in (document_ids or []) if d.strip()]
        payload: dict[str, Any] = {
            "document_ids": doc_ids,
            "attached_document_ids": doc_ids,
            "active_vault_document_id": active_vault_document_id,
            "knowledge_pack_ids": knowledge_pack_ids or [],
        }
        if folder_id:
            payload["folderId"] = folder_id.strip()
        if not doc_ids and not folder_id:
            raise ValueError("set_conversation_scope_vault requires document_ids and/or folder_id")
        self._request("POST", f"/conversations/{conversation_id}/scope", json_body=payload)

    def set_conversation_scope(
        self,
        conversation_id: str,
        document_id: str,
        *,
        knowledge_pack_ids: list[str] | None = None,
    ) -> None:
        self.set_conversation_scope_vault(
            conversation_id,
            document_ids=[document_id],
            knowledge_pack_ids=knowledge_pack_ids,
        )

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
