"""Tests for YourAI HTTP client (mocked)."""

from unittest.mock import MagicMock, patch

import pytest
import requests

from yourai_chat.client import YourAIChatClient
from yourai_chat.config import YourAIConfig
from yourai_chat.exceptions import YourAIAuthError, YourAINetworkError, YourAIResponseError


@pytest.fixture
def config() -> YourAIConfig:
    return YourAIConfig(
        base_url="https://ai-dev.yourai.com",
        client_id="dev-client-id",
        client_secret="dev-client-secret",
        org_id="org-uuid",
        user_id="user-uuid",
        default_conversation_id="575272df-3427-43ce-a4d0-d8ffb2b97b5b",
        default_retrieval_mode="hybrid",
        timeout_seconds=5.0,
        max_retries=3,
        retry_backoff_seconds=0.01,
    )


@pytest.fixture
def client(config: YourAIConfig) -> YourAIChatClient:
    return YourAIChatClient(config=config)


def test_build_payload_shared_conversation_new_message_ids(client: YourAIChatClient):
    p1 = client.build_payload(message="Hello", intent_id="intent-1")
    p2 = client.build_payload(message="Follow-up", intent_id="intent-1")
    assert p1["org_id"] == "org-uuid"
    assert p1["user_id"] == "user-uuid"
    assert p1["message"] == "Hello"
    assert p2["message"] == "Follow-up"
    assert p1["intent_id"] == "intent-1"
    assert p1["retrieval_mode"] == "hybrid"
    assert p1["conversation_id"] == p2["conversation_id"] == "575272df-3427-43ce-a4d0-d8ffb2b97b5b"
    assert p1["message_id"] != p2["message_id"]


def test_headers_no_secrets_in_payload(client: YourAIChatClient):
    headers = client._headers()
    assert headers["X-Client-ID"] == "dev-client-id"
    assert headers["X-Client-Secret"] == "dev-client-secret"
    payload = client.build_payload(message="test")
    assert "secret" not in str(payload).lower() or "dev-client-secret" not in str(payload)


@patch.object(requests.Session, "post")
def test_respond_success(mock_post: MagicMock, client: YourAIChatClient):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.ok = True
    mock_resp.json.return_value = {"answer": "OK"}
    mock_post.return_value = mock_resp

    data, status, latency, meta = client.respond(message="Hi")
    assert status == 200
    assert data["answer"] == "OK"
    assert meta["conversation_id"]
    assert meta["message_id"]
    assert latency >= 0


@patch.object(requests.Session, "post")
def test_auth_failure_no_retry(mock_post: MagicMock, client: YourAIChatClient):
    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.ok = False
    mock_resp.text = "Unauthorized"
    mock_post.return_value = mock_resp

    with pytest.raises(YourAIAuthError):
        client.respond(message="Hi")
    assert mock_post.call_count == 1


@patch.object(requests.Session, "post")
def test_timeout_retries(mock_post: MagicMock, client: YourAIChatClient):
    mock_post.side_effect = requests.Timeout("timed out")
    with pytest.raises(YourAINetworkError):
        client.respond(message="Hi")
    assert mock_post.call_count == 3


@patch.object(requests.Session, "post")
def test_malformed_json(mock_post: MagicMock, client: YourAIChatClient):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.ok = True
    mock_resp.json.side_effect = ValueError("not json")
    mock_post.return_value = mock_resp

    with pytest.raises(YourAIResponseError):
        client.respond(message="Hi")
