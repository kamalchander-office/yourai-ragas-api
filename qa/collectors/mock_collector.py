"""Collect answers from the local mock API (main.py /v1/query)."""

from __future__ import annotations

import time
from typing import Any

import requests

from qa.collectors.base import build_result_row


def collect_with_mock_api(
    test_cases: list[dict[str, Any]],
    *,
    api_url: str,
    bearer_token: str,
    sleep_seconds: float = 0.5,
) -> list[dict[str, Any]]:
    api_url = api_url.rstrip("/")
    query_url = f"{api_url}/v1/query"
    headers = {"Authorization": f"Bearer {bearer_token}"}

    # Health check
    health_response = requests.get(f"{api_url}/health", timeout=5)
    health_response.raise_for_status()
    print(f"✓ API is healthy at {api_url}\n")

    results: list[dict[str, Any]] = []

    for i, tc in enumerate(test_cases, start=1):
        print(f"  [{i}/{len(test_cases)}] {tc['id']}: {tc['question'][:60]}...")

        payload = {
            "question": tc["question"],
            "intent": tc.get("intent", "General Chat"),
        }

        try:
            resp = requests.post(query_url, json=payload, headers=headers, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            normalized = {
                "question": tc["question"],
                "actual_answer": data.get("answer", ""),
                "answer": data.get("answer", ""),
                "actual_source": None,
                "actual_doc_id": None,
                "reference": None,
                "reference_text": None,
                "contexts": data.get("contexts", []),
                "raw_response": data,
                "http_status": resp.status_code,
                "api_backend": "mock",
            }
            row = build_result_row(tc, normalized)
            results.append(row)
            print(f"        ✓ Answer received ({len(row['answer'])} chars)")

        except requests.HTTPError as e:
            status = e.response.status_code if e.response is not None else "?"
            results.append(
                build_result_row(
                    tc,
                    {"contexts": [], "raw_response": {}},
                    error=f"ERROR: HTTP {status}",
                )
            )
            print(f"        ✗ HTTP {status}")

        except Exception as e:
            results.append(
                build_result_row(
                    tc,
                    {"contexts": [], "raw_response": {}},
                    error=f"ERROR: {str(e)[:100]}",
                )
            )
            print(f"        ✗ {e}")

        if i < len(test_cases):
            time.sleep(sleep_seconds)

    return results
