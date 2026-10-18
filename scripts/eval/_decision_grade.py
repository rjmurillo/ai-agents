"""Deterministic decision grader for rule-activation scenarios (issue #6658).

The LLM judge in `eval-rule-activation.py` scores how much a response sounds
like the rule. A response can recite the rule's vocabulary and still make the
wrong call. This module grades the call itself.

A scenario opts in with a `decision` object. The prompt asks the model to end
with two lines (labels in uppercase, matched case-sensitively; the token is not):

    DECISION: <one token from decision.options>
    EVIDENCE: <one line>

The grade reads only those lines. Prose around them, including any rule
keyword, never changes the result. A response passes when all of these hold:

- Every DECISION line carries the same token (two different tokens is
  ambiguous and fails).
- That token is one of `decision.options` and one of `decision.expected`.
- An EVIDENCE line exists, is not empty, and matches every pattern in
  `decision.evidence_all`.

Each failure carries a stable `reason` code, so a report says why.

Out of scope: this module never calls a model and never touches the judge
scores. It does not replace the durable-outcome schema (#5768), the skillopt
runner (#6655), or the routing benchmark (#5422).
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

# A leading list marker, quote, or emphasis mark is allowed so a model that
# bolds the label still counts. The token itself is a bare identifier.
# The labels are matched case-sensitively, as the prompt asks for uppercase.
# A prose line such as "Decision: I would run rg first." is then not read as a
# contract line and cannot make a correct response ambiguous. Only the token is
# case-insensitive.
_LINE_PREFIX = r"^[\s>*_`\-]*"
_DECISION_RE = re.compile(
    _LINE_PREFIX + r"DECISION[\s*_`]*:[\s*_`]*((?i:[A-Z][A-Z_]*))",
    re.MULTILINE,
)
_EVIDENCE_RE = re.compile(
    _LINE_PREFIX + r"EVIDENCE[\s*_`]*:[ \t*_`]*(.*)$",
    re.MULTILINE,
)

REASON_PASS = "pass"
REASON_NO_DECISION = "no_decision_line"
REASON_AMBIGUOUS = "ambiguous_decision"
REASON_UNKNOWN_TOKEN = "token_not_in_options"
REASON_WRONG_DECISION = "wrong_decision"
REASON_NO_EVIDENCE = "no_evidence_line"
REASON_EVIDENCE_MISMATCH = "evidence_mismatch"

UNMEASURED = "UNMEASURED"

_SPEC_STRING_LISTS = ("options", "expected")


@dataclass(frozen=True, slots=True)
class DecisionResult:
    """Outcome of grading one response against one decision spec."""

    passed: bool
    reason: str
    decision: str | None = None
    evidence: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "decision": self.decision,
            "evidence": self.evidence,
        }


def _string_list(value: object) -> list[str] | None:
    if not isinstance(value, list) or not value:
        return None
    if not all(isinstance(item, str) and item.strip() for item in value):
        return None
    return list(value)


def _validate_tokens(spec: Mapping[str, Any]) -> str | None:
    for key in _SPEC_STRING_LISTS:
        if _string_list(spec.get(key)) is None:
            return f"decision.{key} must be a non-empty list of non-empty strings"
    options = {item.strip().upper() for item in spec["options"]}
    expected = {item.strip().upper() for item in spec["expected"]}
    if len(options) < 2:
        return "decision.options needs at least two distinct tokens, or no choice is graded"
    if not expected <= options:
        return "decision.expected must be a subset of decision.options"
    if expected == options:
        return "decision.expected equals decision.options, so no response could fail"
    if not all(re.fullmatch(r"[A-Z][A-Z_]*", token) for token in options):
        return "decision.options tokens must be letters and underscores"
    return None


def _validate_evidence_patterns(spec: Mapping[str, Any]) -> str | None:
    patterns = spec.get("evidence_all", [])
    if not isinstance(patterns, list) or not all(isinstance(p, str) and p for p in patterns):
        return "decision.evidence_all must be a list of non-empty regex strings"
    for pattern in patterns:
        try:
            re.compile(pattern)
        except re.error as exc:
            return f"decision.evidence_all pattern {pattern!r} is not a valid regex: {exc}"
    return None


def validate_decision_spec(spec: object) -> str | None:
    """Return a human-readable error for a malformed spec, or None when sound.

    Refusing a bad spec at load time matters because a spec that can never
    pass (or never fail) would certify a scenario without measuring it.
    """
    if not isinstance(spec, Mapping):
        return "decision must be an object"
    return _validate_tokens(spec) or _validate_evidence_patterns(spec)


def grade_decision(spec: Mapping[str, Any], response: str) -> DecisionResult:
    """Grade `response` against `spec`. Raises ValueError on a malformed spec."""
    error = validate_decision_spec(spec)
    if error is not None:
        raise ValueError(error)
    options = {item.strip().upper() for item in spec["options"]}
    expected = {item.strip().upper() for item in spec["expected"]}

    tokens = {match.upper() for match in _DECISION_RE.findall(response)}
    if not tokens:
        return DecisionResult(False, REASON_NO_DECISION)
    if len(tokens) > 1:
        return DecisionResult(False, REASON_AMBIGUOUS)
    token = next(iter(tokens))
    if token not in options:
        return DecisionResult(False, REASON_UNKNOWN_TOKEN, decision=token)
    if token not in expected:
        return DecisionResult(False, REASON_WRONG_DECISION, decision=token)

    evidence_lines = [line.strip() for line in _EVIDENCE_RE.findall(response) if line.strip()]
    if not evidence_lines:
        return DecisionResult(False, REASON_NO_EVIDENCE, decision=token)
    evidence = " ".join(evidence_lines)
    for pattern in spec.get("evidence_all", []):
        if not re.search(pattern, evidence, re.IGNORECASE):
            return DecisionResult(
                False, REASON_EVIDENCE_MISMATCH, decision=token, evidence=evidence
            )
    return DecisionResult(True, REASON_PASS, decision=token, evidence=evidence)


def summarize_decisions(
    scenario_results: Sequence[Mapping[str, Any]],
    mechanisms: Sequence[str],
) -> dict[str, Any]:
    """Count decision passes per mechanism and pool.

    `scenario_results` are the per-scenario records `eval_one_scenario` builds.
    A scenario counts as declared when it carries `decision_declared`. A cell
    counts as graded only when it carries a `decision` result, so a cell that
    hit an API error or a dry run is ungraded, never a failure and never a
    pass. A mechanism with nothing graded reports UNMEASURED, not 0.
    """
    summary: dict[str, Any] = {"declared": 0, "per_mechanism": {}}
    declared = [r for r in scenario_results if r.get("decision_declared")]
    summary["declared"] = len(declared)
    for mech in mechanisms:
        cells: dict[str, Any] = {}
        for pool, negative in (("positive", False), ("negative", True)):
            pool_results = [r for r in declared if bool(r.get("negative_case")) is negative]
            graded = [
                r["mechanisms"][mech]["decision"]
                for r in pool_results
                if isinstance(r.get("mechanisms", {}).get(mech, {}).get("decision"), dict)
            ]
            passed = sum(1 for d in graded if d.get("passed") is True)
            cells[pool] = {
                "declared": len(pool_results),
                "graded": len(graded),
                "passed": passed,
                "pass_rate": round(passed / len(graded), 3) if graded else UNMEASURED,
                "failure_reasons": sorted(
                    {str(d.get("reason")) for d in graded if d.get("passed") is not True}
                ),
            }
        summary["per_mechanism"][mech] = cells
    return summary


def _fully_graded(cell: Mapping[str, Any]) -> bool:
    return bool(cell["declared"] > 0 and cell["graded"] == cell["declared"])


def render_decision_check(summary: Mapping[str, Any], mechanisms: Sequence[str]) -> str:
    """Render the decision summary with its limits, for the run report."""
    if not summary.get("declared"):
        return ""
    rows = [
        "",
        "Decision check (deterministic, DECISION/EVIDENCE lines only):",
        "| Mechanism    | Positive pass | Negative pass |",
        "|--------------|---------------|---------------|",
    ]
    for mech in mechanisms:
        cells = summary["per_mechanism"][mech]
        rows.append(
            f"| {mech:<12} | {_render_cell(cells['positive']):>13} "
            f"| {_render_cell(cells['negative']):>13} |"
        )
    base = summary["per_mechanism"].get("baseline")
    for mech in mechanisms:
        if mech == "baseline":
            continue
        cells = summary["per_mechanism"][mech]
        if base and _fully_graded(base["positive"]) and _fully_graded(cells["positive"]):
            gap = round(cells["positive"]["pass_rate"] - base["positive"]["pass_rate"], 3)
            rows.append(f"Positive pass-rate gap {mech} vs baseline: {gap:+} (descriptive)")
        else:
            rows.append(f"Positive pass-rate gap {mech} vs baseline: {UNMEASURED}")
    rows.append(
        "Limits: one response per cell, no tool execution, and the prompt names the "
        "decision options, so a high baseline can reflect a cue and not the rule. "
        "A gap is not evidence of uplift without repeated runs. "
        f"Tool calls and cost per cell: {UNMEASURED} (single-turn harness)."
    )
    return "\n".join(rows)


def _render_cell(cell: Mapping[str, Any]) -> str:
    if cell["declared"] == 0:
        return "-"
    if cell["graded"] == 0:
        return UNMEASURED
    text = f"{cell['passed']}/{cell['graded']}"
    if cell["graded"] < cell["declared"]:
        text += f" of {cell['declared']}"
    return text
