"""Collect answers from the real YourAI Chat API."""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path
from typing import Any

# Project root on path when running as script from qa/
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from yourai_chat.client import YourAIChatClient
from yourai_chat.exceptions import YourAIAuthError, YourAIChatError
from yourai_chat.parser import parse_chat_response

from qa.collectors.base import build_result_row

log = logging.getLogger(__name__)


def collect_with_yourai_api(
    test_cases: list[dict[str, Any]],
    *,
    sleep_seconds: float = 0.5,
) -> list[dict[str, Any]]:
    client = YourAIChatClient()
    results: list[dict[str, Any]] = []

    shared_conversation_id = client.config.default_conversation_id
    if shared_conversation_id:
        log.info(
            "Using shared conversation_id=%s for all cases (YOURAI_CONVERSATION_ID)",
            shared_conversation_id,
        )
        print(f"  Conversation thread: {shared_conversation_id}\n")

    for i, tc in enumerate(test_cases, start=1):
        question = (tc.get("question") or "").strip()
        if not question:
            log.warning("Skipping case %s: empty question", tc.get("id"))
            continue

        intent_id = (tc.get("intent_id") or "").strip()
        intent_key = tc.get("intent_key") or tc.get("intent") or ""
        print(f"  [{i}/{len(test_cases)}] {tc['id']} [{intent_key}]: {question[:50]}...")
        retrieval_mode = tc.get("retrieval_mode")
        # Same thread for whole run unless a case sets its own conversation_id
        conversation_id = tc.get("conversation_id") or shared_conversation_id or None

        try:
            raw, status, latency_ms, meta = client.respond(
                message=question,
                intent_id=intent_id,
                conversation_id=conversation_id,
                retrieval_mode=retrieval_mode,
            )
            normalized = parse_chat_response(
                question=tc["question"],
                raw=raw,
                http_status=status,
            )
            normalized["latency_ms"] = round(latency_ms, 2)
            normalized["api_backend"] = "yourai"
            normalized["retrieval_mode"] = retrieval_mode or client.config.default_retrieval_mode
            normalized["conversation_id"] = meta["conversation_id"]
            normalized["message_id"] = meta["message_id"]

            row = build_result_row(tc, normalized)
            results.append(row)
            print(f"        ✓ Answer received ({len(row['answer'])} chars, {latency_ms:.0f}ms)")

        except YourAIAuthError as e:
            log.error("Auth failure for case %s: %s", tc["id"], e)
            results.append(
                build_result_row(
                    tc,
                    parse_chat_response(question=tc["question"], raw={}),
                    error=f"ERROR: AUTH — {e}",
                )
            )
            print(f"        ✗ Auth error: {e}")

        except YourAIChatError as e:
            log.error("YourAI error for case %s: %s", tc["id"], e)
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
            time.sleep(sleep_seconds)

    return results
