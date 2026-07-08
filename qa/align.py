"""
Keep results.json aligned with test_cases.json.

Rule: test case id is the key — question, ground_truth, and metadata always
come from test_cases.json. results.json only adds API fields (answer, contexts,
raw_response, etc.).
"""

from __future__ import annotations

import json
from pathlib import Path

from qa.paths import TEST_CASES_FILE

_METADATA_KEYS = (
    "question",
    "ground_truth",
    "case_type",
    "intent",
    "intent_key",
    "source",
    "intent_id",
    "retrieval_mode",
    "document_id",
    "expected_doc_id",
    "document_file",
    "reference_contexts",
    "evaluation_mode",
)


def load_test_cases_by_id() -> dict[str, dict]:
    if not TEST_CASES_FILE.exists():
        return {}
    cases = json.loads(TEST_CASES_FILE.read_text())
    return {c["id"]: c for c in cases if c.get("id")}


def load_test_cases_list() -> list[dict]:
    if not TEST_CASES_FILE.exists():
        return []
    return json.loads(TEST_CASES_FILE.read_text())


def align_result_row(row: dict, test_case: dict) -> dict:
    """Copy canonical question/metadata from test_cases into a result row."""
    out = dict(row)
    out["id"] = test_case["id"]
    for key in _METADATA_KEYS:
        if key in test_case and test_case[key] is not None:
            out[key] = test_case[key]
    if test_case.get("intent_id") or test_case.get("intent"):
        out["intent_id"] = (test_case.get("intent_id") or test_case.get("intent") or "").strip()
    return out


def find_alignment_errors(results: list[dict], test_cases: list[dict] | None = None) -> list[str]:
    """Return human-readable errors when results drift from test_cases (matched by id)."""
    if test_cases is None:
        test_cases = load_test_cases_list()
    tc_by_id = {c["id"]: c for c in test_cases if c.get("id")}
    res_by_id = {r["id"]: r for r in results if r.get("id")}

    errors: list[str] = []

    for tc in test_cases:
        tid = tc["id"]
        row = res_by_id.get(tid)
        if not row:
            errors.append(f"{tid}: in test_cases.json but missing from results.json")
            continue
        tq = (tc.get("question") or "").strip()
        rq = (row.get("question") or "").strip()
        if rq != tq:
            errors.append(
                f"{tid}: question mismatch\n"
                f"  test_cases: {tq[:120]}\n"
                f"  results:    {rq[:120]}"
            )

    for rid in res_by_id:
        if rid not in tc_by_id:
            errors.append(f"{rid}: in results.json but missing from test_cases.json")

    if len(results) != len(test_cases):
        errors.insert(
            0,
            f"Count mismatch: {len(results)} results vs {len(test_cases)} test cases.",
        )

    return errors


def align_results(results: list[dict], test_cases: list[dict] | None = None) -> list[dict]:
    """
    Align every result row to test_cases.json by id.

    Output order matches test_cases.json. API fields (answer, raw_response, …)
    are kept from the matching result row.
    """
    if test_cases is None:
        test_cases = load_test_cases_list()
    res_by_id = {r["id"]: r for r in results if r.get("id")}

    aligned: list[dict] = []
    missing: list[str] = []
    for tc in test_cases:
        tid = tc["id"]
        row = res_by_id.get(tid)
        if row is None:
            missing.append(tid)
            continue
        aligned.append(align_result_row(row, tc))

    if missing:
        raise ValueError(
            f"results.json is missing {len(missing)} case(s): {', '.join(missing[:5])}"
            + (" …" if len(missing) > 5 else "")
            + "\nRe-run: python qa/client.py --backend yourai"
        )

    extra = set(res_by_id) - {tc["id"] for tc in test_cases if tc.get("id")}
    if extra:
        raise ValueError(
            f"results.json has id(s) not in test_cases.json: {', '.join(sorted(extra)[:5])}"
            + "\nRe-run ingest or remove stale rows, then run client.py."
        )

    return aligned
