"""
Layer 1 — rule-based validation (source, document, reference).

Integrates with normalized collector output. Skips checks when expected fields
are absent in the dataset.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RuleValidationResult:
    passed: bool
    failures: list[str] = field(default_factory=list)


class RuleValidator:
    """Compare expected vs actual attribution fields from API responses."""

    def validate(self, test_case: dict[str, Any], result: dict[str, Any]) -> RuleValidationResult:
        failures: list[str] = []

        expected_source = test_case.get("expected_source")
        if expected_source and result.get("actual_source") != expected_source:
            failures.append(
                f"source mismatch: expected={expected_source!r} actual={result.get('actual_source')!r}"
            )

        expected_doc = test_case.get("expected_doc_id")
        if expected_doc and result.get("actual_doc_id") != expected_doc:
            failures.append(
                f"document mismatch: expected={expected_doc!r} actual={result.get('actual_doc_id')!r}"
            )

        expected_ref = test_case.get("expected_reference")
        if expected_ref and result.get("reference") != expected_ref:
            failures.append(
                f"reference mismatch: expected={expected_ref!r} actual={result.get('reference')!r}"
            )

        return RuleValidationResult(passed=len(failures) == 0, failures=failures)
