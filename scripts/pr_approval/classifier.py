"""Classifier seam for the natural language residue.

The classifier runs only after every deterministic check passes. It may only
hold: ``pass`` never grants approval in this release. ``StubClassifier`` makes
no model call and always reports itself unavailable.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol

VERDICTS = ("pass", "hold", "abstain")
MAX_REASON_CHARS = 240


class ClassifierOutputError(ValueError):
    """Raised when classifier output breaks the JSON contract."""


@dataclass(frozen=True)
class ClassifierResult:
    verdict: str
    reason: str


def parse_classifier_output(text: str) -> ClassifierResult:
    """Validate ``{"verdict": "pass|hold|abstain", "reason": "..."}`` strictly."""
    try:
        payload = json.loads(text)
    except (TypeError, ValueError) as exc:
        raise ClassifierOutputError("classifier output is not JSON") from exc
    if not isinstance(payload, dict) or set(payload) != {"verdict", "reason"}:
        raise ClassifierOutputError("classifier output must have exactly 'verdict' and 'reason'")
    verdict = payload["verdict"]
    reason = payload["reason"]
    if verdict not in VERDICTS:
        raise ClassifierOutputError("classifier verdict is not an allowed value")
    if not isinstance(reason, str) or len(reason) > MAX_REASON_CHARS:
        raise ClassifierOutputError(
            f"classifier reason must be a string of at most {MAX_REASON_CHARS} chars"
        )
    return ClassifierResult(verdict, reason)


class Classifier(Protocol):
    def classify(self, classifier_id: str, evidence: dict[str, object]) -> ClassifierResult | None:
        """Return a parsed result, or None when no classifier is available."""


class StubClassifier:
    """No transport is wired. Every call reports the classifier unavailable."""

    def classify(
        self, _classifier_id: str, _evidence: dict[str, object]
    ) -> ClassifierResult | None:
        return None
