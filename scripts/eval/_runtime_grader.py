"""Model-graded semantic assertions for runtime parity fixtures (issue #5404).

Split out of `eval_runtime_parity` on purpose: everything here changes when
the grading contract, prompt, or provider selection changes, and nothing here
changes when the CLI argument surface or the report shape changes. The
grading contract mirrors `_providers.EvalProvider` (`scripts/eval/_providers.py`),
quoted verbatim because this module is a consumer, not the definition:

    class EvalProvider(Protocol):
        name: str
        system_fingerprint: str | None

        def complete(
            self,
            *,
            messages: list[dict[str, str]],
            system: str = "",
            model: str,
            max_tokens: int = 1024,
            temperature: float = 0.0,
            seed: int | None = None,
        ) -> str:
            '''Return assistant text. Raise RuntimeError on any failure.'''
            ...

`grade` therefore catches only `RuntimeError`: every provider in this
repository's registry raises that type on failure (see `_providers.py`'s
module docstring, "Error contract (load-bearing)"), so catching anything
broader would also swallow a real programming defect in this module.

Calibration (`calibrate`) is what makes a semantic PASS trustworthy: a grader
that always says PASS would make every fixture look correct. Before grading
the actual runtime response, `calibrate` grades the fixture's own positive
control (must PASS), negative control (must FAIL), and an automatic mutant
(the positive response plus a fixed continuation-offer tail, must FAIL). A
grader that fails any of those three is not discriminating this rubric and
is reported `INVALID_GRADER` rather than trusted for anything.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from _runtime_parity import Fixture

__all__ = [
    "MUTANT_TAIL",
    "CalibrationResult",
    "GradeResult",
    "GraderProtocol",
    "calibrate",
    "grade",
    "grade_semantic_assertions",
]

#: Appended to a fixture's own positive-control response to build the
#: automatic mutant every semantic assertion must be calibrated against
#: (spec-5404.md AC8). A grader that lets this pass is not discriminating a
#: response that reopens the interaction from one that does not.
MUTANT_TAIL = "\n\nWant me to also add tests for this?"

_SYSTEM_PROMPT = (
    "You are grading whether an assistant's response, given the request it "
    "answers, reopens an already-finished interaction with an unsolicited "
    "continuation: a question, an offer, or an invitation to do more work, "
    "instead of ending on the result. Apply the rubric below to the response "
    "only; do not grade style or correctness beyond what the rubric asks. "
    "Reply with exactly one JSON object and nothing else, in this shape: "
    '{"verdict": "PASS", "reason": "<one sentence>"} or '
    '{"verdict": "FAIL", "reason": "<one sentence>"}.'
)


class GraderProtocol(Protocol):
    """The subset of `_providers.EvalProvider` this module calls."""

    name: str
    system_fingerprint: str | None

    def complete(
        self,
        *,
        messages: list[dict[str, str]],
        system: str = "",
        model: str,
        max_tokens: int = 1024,
        temperature: float = 0.0,
        seed: int | None = None,
    ) -> str:
        """Return assistant text. Raise RuntimeError on any failure."""
        ...


@dataclass(frozen=True, slots=True)
class GradeResult:
    """One grader call's outcome. `verdict` is PASS, FAIL, or UNAVAILABLE."""

    verdict: str
    reason: str
    provider: str
    model: str
    fingerprint: str | None

    def to_report(self) -> dict[str, object]:
        return {
            "verdict": self.verdict,
            "reason": self.reason,
            "grader_provider": self.provider,
            "grader_model": self.model,
            "grader_fingerprint": self.fingerprint,
        }


@dataclass(frozen=True, slots=True)
class CalibrationResult:
    """The three calibration grades required before a rubric is trusted."""

    positive: GradeResult
    negative: GradeResult
    mutant: GradeResult

    @property
    def unavailable(self) -> bool:
        """True when any calibration grade could not be produced (AC9)."""
        return any(
            result.verdict == "UNAVAILABLE"
            for result in (self.positive, self.negative, self.mutant)
        )

    @property
    def miscalibrated(self) -> bool:
        """True when the grader fails to discriminate this rubric (AC8)."""
        return (
            self.positive.verdict != "PASS"
            or self.negative.verdict != "FAIL"
            or self.mutant.verdict != "FAIL"
        )

    def to_report(self) -> dict[str, object]:
        return {
            "positive": self.positive.to_report(),
            "negative": self.negative.to_report(),
            "mutant": self.mutant.to_report(),
        }


def _parse_first_json_object(text: str) -> dict[str, object] | None:
    """Return the first balanced JSON object found in `text`, or None.

    A grader can wrap its verdict in prose or a markdown code fence even when
    asked not to; scanning for the first `{` that parses is more robust than
    requiring the whole message to be JSON, and returning None on failure
    (rather than raising) keeps every malformed-output path inside the
    UNAVAILABLE branch in `grade`.
    """
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            value, _ = decoder.raw_decode(text, index)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return None


def grade(
    provider: GraderProtocol,
    model: str,
    rubric: str,
    prompt: str,
    response: str,
) -> GradeResult:
    """Grade one response against one rubric. Never raises (AC9).

    Any provider failure, or any output with no parseable PASS/FAIL verdict,
    is folded into `verdict="UNAVAILABLE"` rather than propagated, so a
    grader outage fails one fixture closed instead of crashing the run.
    """
    message = (
        f"Rubric: {rubric}\n\n"
        f"Original request:\n{prompt}\n\n"
        f"Response to grade:\n{response}"
    )
    try:
        text = provider.complete(
            messages=[{"role": "user", "content": message}],
            system=_SYSTEM_PROMPT,
            model=model,
        )
    except RuntimeError as exc:
        return GradeResult("UNAVAILABLE", str(exc), provider.name, model, None)
    parsed = _parse_first_json_object(text)
    verdict = parsed.get("verdict") if parsed else None
    fingerprint = getattr(provider, "system_fingerprint", None)
    if verdict not in {"PASS", "FAIL"}:
        return GradeResult(
            "UNAVAILABLE",
            "grader returned no parseable PASS/FAIL verdict",
            provider.name,
            model,
            fingerprint,
        )
    reason = str(parsed.get("reason", "")) if parsed else ""
    return GradeResult(str(verdict), reason, provider.name, model, fingerprint)


def calibrate(
    provider: GraderProtocol,
    model: str,
    rubric: str,
    fixture: Fixture,
) -> CalibrationResult:
    """Grade a fixture's positive control, negative control, and mutant."""
    positive = grade(provider, model, rubric, fixture.prompt, fixture.positive.response)
    negative = grade(provider, model, rubric, fixture.prompt, fixture.negative.response)
    mutant = grade(
        provider, model, rubric, fixture.prompt, fixture.positive.response + MUTANT_TAIL
    )
    return CalibrationResult(positive, negative, mutant)


def grade_semantic_assertions(
    fixture: Fixture,
    response: str,
    provider: GraderProtocol,
    model: str,
) -> tuple[list[dict[str, object]], str | None, dict[str, object] | None]:
    """Calibrate and grade every semantic assertion on one runtime response.

    Returns `(assertion_dicts, verdict_override, calibration_report)`.
    `verdict_override` is `None` on success, `"UNAVAILABLE"` when a grader
    call could not produce a verdict (AC9, caller maps to exit 3), or
    `"INVALID_GRADER"` when calibration proves the grader is not
    discriminating this rubric (AC8, caller maps to exit 1). Grading stops
    at the first assertion that fails either check; `assertion_dicts` holds
    only the assertions completed before that point.
    """
    results: list[dict[str, object]] = []
    for spec in fixture.assertions:
        if spec.kind != "semantic":
            continue
        calibration = calibrate(provider, model, spec.rubric, fixture)
        report = calibration.to_report()
        if calibration.unavailable:
            return results, "UNAVAILABLE", report
        if calibration.miscalibrated:
            return results, "INVALID_GRADER", report
        outcome = grade(provider, model, spec.rubric, fixture.prompt, response)
        if outcome.verdict == "UNAVAILABLE":
            return results, "UNAVAILABLE", report
        results.append(
            {
                "kind": "semantic",
                "path": None,
                "expected": spec.rubric,
                "passed": outcome.verdict == "PASS",
                "status": "graded",
                **outcome.to_report(),
                "calibration": report,
            }
        )
    return results, None, None
