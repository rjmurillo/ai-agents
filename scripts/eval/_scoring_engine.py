"""Scoring engine and concrete scorers for eval-agent-vs-baseline.

DESIGN-004 §5.3 (Strategy over AssertionKind). Adding AstScorer or
TestPassScorer later requires only `engine.register(kind, scorer)`; no
edits to ScoringEngine or Fixture.
"""

from __future__ import annotations

import re
from typing import Callable

from _eval_agent_types import Assertion, AssertionKind, AssertionResult

Scorer = Callable[[Assertion, str], AssertionResult]

_VERDICT_RE = re.compile(r"^\s*(IDENTIFY|OK|ESCALATE)\b", re.IGNORECASE)


def regex_scorer(assertion: Assertion, response: str) -> AssertionResult:
    """REGEX kind: case-insensitive `re.search`. Passed iff a match is found."""
    pattern = assertion.pattern
    if pattern is None:
        raise ValueError("RegexScorer requires assertion.pattern to be set")
    match = re.search(pattern, response, re.IGNORECASE)
    extracted = match.group(0) if match else None
    return AssertionResult(
        kind=AssertionKind.REGEX,
        pattern=pattern,
        expected_value=None,
        passed=match is not None,
        extracted=extracted,
    )


def verdict_scorer(assertion: Assertion, response: str) -> AssertionResult:
    """VERDICT kind: extract the first IDENTIFY|OK|ESCALATE token, compare CI."""
    expected = assertion.expected_value
    if expected is None:
        raise ValueError("VerdictScorer requires assertion.expected_value to be set")
    match = _VERDICT_RE.match(response)
    extracted = match.group(1).upper() if match else None
    passed = extracted is not None and extracted == expected.upper()
    return AssertionResult(
        kind=AssertionKind.VERDICT,
        pattern=None,
        expected_value=expected,
        passed=passed,
        extracted=extracted,
    )


# Aliases that match the names used in DESIGN-004 §5.3 ("RegexScorer",
# "VerdictScorer"). Functions are first-class scorers; the design names are
# preserved for readability at registration sites.
RegexScorer: Scorer = regex_scorer
VerdictScorer: Scorer = verdict_scorer


class ScoringEngine:
    """Polymorphic dispatch from `AssertionKind` to a registered scorer."""

    def __init__(self) -> None:
        self._scorers: dict[AssertionKind, Scorer] = {}

    def register(self, kind: AssertionKind, scorer: Scorer) -> None:
        self._scorers[kind] = scorer

    def score(self, assertion: Assertion, response: str) -> AssertionResult:
        scorer = self._scorers.get(assertion.kind)
        if scorer is None:
            raise ValueError(
                f"No scorer registered for AssertionKind={assertion.kind!r}. "
                f"Registered kinds: {sorted(k.value for k in self._scorers)}"
            )
        return scorer(assertion, response)

    def score_all(
        self, assertions: list[Assertion], response: str
    ) -> list[AssertionResult]:
        return [self.score(a, response) for a in assertions]


def build_default_engine() -> ScoringEngine:
    """Engine with REGEX and VERDICT scorers registered."""
    engine = ScoringEngine()
    engine.register(AssertionKind.REGEX, RegexScorer)
    engine.register(AssertionKind.VERDICT, VerdictScorer)
    return engine
