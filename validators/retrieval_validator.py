"""
Layer 2 — retrieval validation (placeholder).

Wire shadow retrieval / vector DB checks here when backend access is available.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RetrievalValidationResult:
    passed: bool
    notes: list[str] = field(default_factory=list)


class RetrievalValidator:
    """Stub — always passes until shadow retrieval is implemented."""

    def validate(self, test_case: dict[str, Any], result: dict[str, Any]) -> RetrievalValidationResult:
        return RetrievalValidationResult(passed=True, notes=["retrieval validation not configured"])
