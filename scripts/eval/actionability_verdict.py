"""Parse a model reply into a verdict.

Plan task M1-T14. Stdlib only. The contract is in
``.project-toolkit/specs/SPEC-harness-agnostic-llm-fallback.md``, section Call contract,
Output: a JSON object with a real bool ``is_actionable``, a finite number ``confidence``
clamped to [0, 1], and a ``reason`` string cut to 100 characters.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass

MAX_REASON_CHARS = 100

_FENCE = re.compile(r"\A```(?:json)?[ \t]*\n(.*)\n```\Z", re.DOTALL)


@dataclass(frozen=True, slots=True)
class Verdict:
    """A parsed model verdict."""

    is_actionable: bool
    confidence: float
    reason: str


def _reject_constant(name: str) -> None:
    raise ValueError(f"non-finite JSON constant {name}")


def _clean_confidence(value: object) -> float | None:
    """Return ``value`` clamped to [0, 1], or None when it is not a finite real number."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    try:
        number = float(value)
    except OverflowError:
        return None
    if not math.isfinite(number):
        return None
    return min(1.0, max(0.0, number))


def _strip_one_fence(text: str) -> str:
    stripped = text.strip()
    match = _FENCE.match(stripped)
    return match.group(1).strip() if match else stripped


def parse_verdict(text: str) -> Verdict | None:
    """Parse a model reply into a Verdict, or None when it breaks the contract.

    Stricter than ``scripts/llm_classification/classifier.py``, which defaults a
    missing ``is_actionable`` to False and ``confidence`` to 0.5 (spec Call
    contract, Output). Here a malformed reply is a failure, not a verdict.
    ``reason`` is not part of the verdict, so a missing or non-string one
    becomes the empty string.
    """
    try:
        data = json.loads(_strip_one_fence(text), parse_constant=_reject_constant)
    except (ValueError, RecursionError):
        return None
    if not isinstance(data, dict):
        return None
    flag = data.get("is_actionable")
    confidence = _clean_confidence(data.get("confidence"))
    if not isinstance(flag, bool) or confidence is None:
        return None
    reason = data.get("reason")
    return Verdict(
        is_actionable=flag,
        confidence=confidence,
        reason=reason[:MAX_REASON_CHARS] if isinstance(reason, str) else "",
    )
