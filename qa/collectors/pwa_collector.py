"""Collect answers via YourAI PWA QA API using qa/session.json."""

from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from yourai_chat.exceptions import YourAIAuthError, YourAIChatError, YourAIResponseError
from yourai_chat.parser import parse_chat_response
from yourai_pwa.client import YourAIPWAClient
from yourai_pwa.config import PWAConfig, load_pwa_config

from qa.collectors.base import build_result_row
from qa.session_store import get_session_scope, load_session, resolve_intent_id

log = logging.getLogger(__name__)

_DEFAULT_COLLECT_SLEEP = float(os.getenv("YOURAI_PWA_COLLECT_SLEEP", "2"))


def collect_with_pwa_api(
    test_cases: list[dict[str, Any]],
    *,
    session_path: Path | None = None,
    sleep_seconds: float | None = None,
    fresh_conversation_per_case: bool | None = None,
) -> list[dict[str, Any]]:
    session = load_session(session_path)
    config = load_pwa_config()
    client = YourAIPWAClient(config)

    scope = get_session_scope(session)
    document_ids = scope["document_ids"]
    folder_id = scope.get("folder_id")
    primary_document_id = scope.get("primary_document_id") or (document_ids[0] if document_ids else "")

    if not document_ids and not folder_id:
        raise YourAIResponseError(
            "session.json has no vault attachment — run bootstrap_session.py "
            "(upload or vault pick)."
        )
    if fresh_conversation_per_case is None:
        fresh_conversation_per_case = os.getenv(
            "YOURAI_PWA_FRESH_CONVERSATION_PER_CASE", "true"
        ).strip().lower() in ("1", "true", "yes")
    pause = sleep_seconds if sleep_seconds is not None else _DEFAULT_COLLECT_SLEEP

    print(f"  PWA session: {session.get('base_url')}")
    print(f"  document_ids : {', '.join(document_ids) if document_ids else '—'}")
    print(f"  folder_id    : {folder_id or '—'}")
    print(
        f"  mode         : "
        f"{'fresh conversation per case' if fresh_conversation_per_case else 'reuse session conversation'}\n"
    )

    results: list[dict[str, Any]] = []

    for i, tc in enumerate(test_cases, start=1):
        question = (tc.get("question") or "").strip()
        if not question:
            log.warning("Skipping case %s: empty question", tc.get("id"))
            continue

        intent_id = resolve_intent_id(session, tc)
        if not intent_id:
            raise YourAIResponseError(
                f"{tc.get('id')}: no platform intent_id — run bootstrap_session.py and "
                "set intent/intent_key on the test case."
            )

        if fresh_conversation_per_case:
            conversation_id = client.start_conversation(reuse=False)
            client.set_conversation_scope_vault(
                conversation_id,
                document_ids=document_ids,
                folder_id=folder_id,
            )
        else:
            conversation_id = session["conversation_id"]
            if i == 1:
                client.set_conversation_scope_vault(
                    conversation_id,
                    document_ids=document_ids,
                    folder_id=folder_id,
                )

        intent_key = tc.get("intent_key") or tc.get("intent") or intent_id[:8]
        print(f"  [{i}/{len(test_cases)}] {tc['id']} [{intent_key}]: {question[:50]}...")

        try:
            started = time.perf_counter()
            raw = client.chat(
                conversation_id=conversation_id,
                message=question,
                intent_id=intent_id,
                retrieval_mode=tc.get("retrieval_mode") or config.default_retrieval_mode,
            )
            latency_ms = (time.perf_counter() - started) * 1000

            normalized = parse_chat_response(
                question=tc["question"],
                raw=raw,
                http_status=200,
            )
            normalized["latency_ms"] = round(latency_ms, 2)
            normalized["api_backend"] = "pwa"
            normalized["retrieval_mode"] = tc.get("retrieval_mode") or config.default_retrieval_mode
            normalized["conversation_id"] = conversation_id
            normalized["intent_id"] = intent_id

            row = build_result_row(tc, normalized)
            row["document_id"] = tc.get("document_id") or primary_document_id
            row["expected_doc_id"] = tc.get("expected_doc_id") or primary_document_id
            row["folder_id"] = folder_id or ""
            row["scope_document_ids"] = document_ids
            row["intent_id"] = intent_id
            row["intent_key"] = tc.get("intent_key") or ""
            results.append(row)
            print(f"        ✓ Answer received ({len(row['answer'])} chars, {latency_ms:.0f}ms)")

        except YourAIAuthError as e:
            results.append(
                build_result_row(
                    tc,
                    parse_chat_response(question=tc["question"], raw={}),
                    error=f"ERROR: AUTH — {e}",
                )
            )
            print(f"        ✗ Auth error: {e}")

        except (YourAIChatError, YourAIResponseError) as e:
            results.append(
                build_result_row(
                    tc,
                    parse_chat_response(question=tc["question"], raw={}),
                    error=f"ERROR: {str(e)[:120]}",
                )
            )
            print(f"        ✗ {e}")

        except Exception as e:
            log.exception("Unexpected error for case %s", tc["id"])
            results.append(
                build_result_row(
                    tc,
                    parse_chat_response(question=tc["question"], raw={}),
                    error=f"ERROR: {str(e)[:120]}",
                )
            )
            print(f"        ✗ {e}")

        if i < len(test_cases):
            time.sleep(pause)

    return results
