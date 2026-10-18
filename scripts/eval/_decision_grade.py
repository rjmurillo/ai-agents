"""Deterministic decision grader for rule-activation scenarios (issue #6658).

The LLM judge in `eval-rule-activation.py` scores how much a response sounds
like the rule. A response can recite the rule's vocabulary and still make the
wrong call. This module grades the call itself.

A scenario opts in with a `decision` object. The prompt asks the model to end
with two lines (labels in uppercase, matched case-sensitively; the token is not):

    DECISION: <one token from decision.options>
    EVIDENCE: <one line>

The grade reads only those lines. Prose before them, including any rule
keyword, never changes the result. Prose after the last of them does: the
prompt says they are the last two lines, so text that follows (a reversal such
as "actually, no need to run it") fails as trailing_text. Blank lines and a
closing code fence may follow. A response passes when all of these hold:

- Every DECISION line is one bare token, and all carry the same token. Two
  different tokens, or a line that holds more than one token ("A or B"), is
  ambiguous and fails.
- That token is one of `decision.options` and one of `decision.expected`.
- An EVIDENCE line exists, is not empty, and matches every pattern in
  `decision.evidence_all`.
- No prose follows the last DECISION or EVIDENCE line.

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

# A leading list marker (bullet, quote, or number such as "1." or "2)") and
# emphasis marks are allowed so a model that bolds the label still counts.
# The labels are matched case-sensitively, as the prompt asks for uppercase.
# A prose line such as "Decision: I would run rg first." is then not read as a
# contract line and cannot make a correct response ambiguous. Only the token is
# case-insensitive.
# Both contract lines are same-line: the value follows the colon on the same
# line. "DECISION:" with the token on the next line is a labeled line that is
# not one bare token (ambiguous_decision), and "EVIDENCE:" with the value on
# the next line grades no_evidence_line.
# The token must be the whole value: only emphasis marks and a closing period
# may follow it. "DECISION: REUSE or BUILD" is therefore not a REUSE line. It
# is a labeled line that is not one bare token, and it is graded ambiguous.
_LINE_PREFIX = r"^[\s>*_`\-]*(?:\d+[.)][\s>*_`]*)?"
_DECISION_LABEL = _LINE_PREFIX + r"DECISION[\s*_`]*:"
_DECISION_RE = re.compile(
    _DECISION_LABEL + r"[ \t*_`]*((?i:[A-Z][A-Z_]*))[ \t\r*_`.]*$",
    re.MULTILINE,
)
_DECISION_LABEL_RE = re.compile(_DECISION_LABEL, re.MULTILINE)
_EVIDENCE_RE = re.compile(
    _LINE_PREFIX + r"EVIDENCE[\s*_`]*:[ \t*_`]*(.*)$",
    re.MULTILINE,
)
_EVIDENCE_LABEL_RE = re.compile(_LINE_PREFIX + r"EVIDENCE[\s*_`]*:")
_FENCE_LINES = frozenset({"```", "~~~"})

REASON_PASS = "pass"
REASON_NO_DECISION = "no_decision_line"
REASON_AMBIGUOUS = "ambiguous_decision"
REASON_UNKNOWN_TOKEN = "token_not_in_options"
REASON_WRONG_DECISION = "wrong_decision"
REASON_NO_EVIDENCE = "no_evidence_line"
REASON_EVIDENCE_MISMATCH = "evidence_mismatch"
REASON_TRAILING_TEXT = "trailing_text"

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


def _has_trailing_text(response: str) -> bool:
    """True when a non-blank line other than a bare fence follows the last contract line."""
    lines = response.splitlines()
    last = max(
        (
            i
            for i, line in enumerate(lines)
            if _DECISION_LABEL_RE.match(line) or _EVIDENCE_LABEL_RE.match(line)
        ),
        default=-1,
    )
    return any(line.strip() and line.strip() not in _FENCE_LINES for line in lines[last + 1 :])


def grade_decision(spec: Mapping[str, Any], response: str) -> DecisionResult:
    """Grade `response` against `spec`. Raises ValueError on a malformed spec."""
    error = validate_decision_spec(spec)
    if error is not None:
        raise ValueError(error)
    options = {item.strip().upper() for item in spec["options"]}
    expected = {item.strip().upper() for item in spec["expected"]}

    matches = _DECISION_RE.findall(response)
    tokens = {match.upper() for match in matches}
    # A DECISION line that is not one bare token (a hedge such as "A or B", or
    # an echoed "<A or B>" template) never counts as a decision, and it never
    # lets a sibling line decide.
    if len(tokens) > 1 or len(_DECISION_LABEL_RE.findall(response)) > len(matches):
        return DecisionResult(False, REASON_AMBIGUOUS)
    if not tokens:
        return DecisionResult(False, REASON_NO_DECISION)
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
    if _has_trailing_text(response):
        return DecisionResult(False, REASON_TRAILING_TEXT, decision=token, evidence=evidence)
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


VERDICT_FAIL_DECISION = "FAIL_DECISION"


def decision_gate(
    summary: Mapping[str, Any],
    positive_mechanisms: Sequence[str],
    negative_mechanisms: Sequence[str],
) -> dict[str, list[str]]:
    """Name the gated decision cells that failed or were not fully graded.

    The judge verdict reads vocabulary, so a run can PASS while every call is
    wrong. A declared pool is gated the way the judge gates it: the positive
    pool on the mechanism the verdict certifies, the negative pool on every
    reachable rule-carrying mechanism. A cell fails when any graded response
    made the wrong call. A cell is incomplete when a declared scenario went
    ungraded (API error, refusal, token limit), because a pass over a subset
    of the pool is not a pass over the pool. A pool with no declared scenario
    gates nothing.
    """
    failed: list[str] = []
    incomplete: list[str] = []
    for pool, mechanisms in (("positive", positive_mechanisms), ("negative", negative_mechanisms)):
        for mech in mechanisms:
            cell = summary["per_mechanism"][mech][pool]
            if cell["declared"] == 0:
                continue
            label = f"{pool} {mech}"
            if cell["passed"] < cell["graded"]:
                failed.append(label)
            if cell["graded"] < cell["declared"]:
                incomplete.append(label)
    return {"failed": failed, "incomplete": incomplete}


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
    gate = summary.get("gate")
    if gate and (gate["failed"] or gate["incomplete"]):
        rows.append(
            f"Decision gate (a judge PASS becomes {VERDICT_FAIL_DECISION}): "
            f"failed: {', '.join(gate['failed']) or '-'}; "
            f"not fully graded: {', '.join(gate['incomplete']) or '-'}"
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
