"""Evaluation provenance and handoff prompts for a skill-doctor report.

Skill-doctor diagnoses conversations statically. It never measures whether a
candidate change improves outcomes; skillopt does that. This module keeps the
two apart:

- ``evaluation`` in report.json records which stages ran. A report without it
  is a static-only run.
- Each suggestion carries a ``status``. It stays ``unevaluated`` until a
  skillopt run supplies baseline and candidate evidence.
- ``validate_report`` refuses claims the recorded stages cannot support, such
  as a measured status with no evidence or a "no beneficial change" verdict
  from static triage alone.
- ``skillopt_prompt`` and ``skillforge_prompt`` build copyable handoff text
  from the suggestion's own fields. Nothing here starts either skill.

Python 3.10+, stdlib only.
"""

from __future__ import annotations

import re
from typing import Any

UNEVALUATED = "unevaluated"
MEASURED_STATUSES = ("accepted", "rejected", "inconclusive")
SUGGESTION_STATUSES = (UNEVALUATED, *MEASURED_STATUSES)
OWNER_KINDS = ("skill", "new-skill", "tooling")
OPTIMIZATION_STAGES = ("not_run", "run")

NOT_SUPPLIED = "not supplied"

STATIC_ONLY_STATEMENT = (
    "Static triage only. No skillopt baseline or candidate evaluation ran, "
    "so candidate effectiveness remains unevaluated."
)
EMPTY_STATIC_STATEMENT = (
    "No candidates proposed through static triage. "
    "This is not evidence that a skill change would fail to improve outcomes."
)

# Wording that asserts a measured verdict. Static triage cannot support it.
_UNSUPPORTED_VERDICT = re.compile(
    r"\bno\s+(?:skill\s+)?(?:changes?|edits?|improvements?)\s+"
    r"(?:(?:is|are|was|were)\s+)?(?:justified|warranted|needed|beneficial|required)\b"
    r"|\bno\s+beneficial\s+(?:skill\s+)?(?:changes?|edits?)\b"
    r"|\bwould\s+not\s+improve\b",
    re.IGNORECASE,
)


def evaluation_of(report: dict[str, Any]) -> dict[str, Any]:
    """Return the report's evaluation block with static-only defaults filled in."""
    raw = report.get("evaluation")
    evaluation = dict(raw) if isinstance(raw, dict) else {}
    evaluation.setdefault("diagnosis", "static")
    evaluation.setdefault("optimization", "not_run")
    return evaluation


def suggestion_status(suggestion: dict[str, Any]) -> str:
    status = suggestion.get("status")
    return status if isinstance(status, str) and status else UNEVALUATED


def _has_evidence(suggestion: dict[str, Any]) -> bool:
    measured = suggestion.get("evaluation")
    if not isinstance(measured, dict):
        return False
    return all(
        isinstance(measured.get(key), str) and measured[key].strip()
        for key in ("baseline", "candidate")
    )


def has_target(suggestion: dict[str, Any]) -> bool:
    """True when the suggestion names a non-blank edit target path."""
    target = suggestion.get("target")
    return isinstance(target, str) and bool(target.strip())


def _is_measured(suggestion: dict[str, Any], optimization: str) -> bool:
    return (
        optimization == "run"
        and suggestion_status(suggestion) in MEASURED_STATUSES
        and _has_evidence(suggestion)
    )


_SUGGESTION_PROSE = ("change", "mechanism", "expected_improvement")


def _report_text(report: dict[str, Any]) -> list[tuple[str, str]]:
    texts = [("summary", report.get("summary"))]
    texts += [
        (f"top_findings[{index}]", text)
        for index, text in enumerate(report.get("top_findings") or [])
    ]
    return [(where, text) for where, text in texts if isinstance(text, str)]


def _suggestion_errors(index: int, suggestion: dict[str, Any], optimization: str) -> list[str]:
    """Claims one suggestion makes that its recorded evidence does not support."""
    where = f"suggestions[{index}] ({suggestion.get('skill') or 'unnamed'})"
    status = suggestion_status(suggestion)
    if status not in SUGGESTION_STATUSES:
        return [f"{where}: status must be one of {SUGGESTION_STATUSES}, got {status!r}"]
    errors = []
    owner = suggestion.get("owner")
    if owner is not None and owner not in OWNER_KINDS:
        errors.append(f"{where}: owner must be one of {OWNER_KINDS}, got {owner!r}")
    if status in MEASURED_STATUSES and optimization != "run":
        errors.append(f"{where}: status {status!r} needs evaluation.optimization 'run'")
    if status in MEASURED_STATUSES and not _has_evidence(suggestion):
        errors.append(
            f"{where}: status {status!r} needs evaluation.baseline and evaluation.candidate evidence"
        )
    if suggestion.get("variants") and not has_target(suggestion) and suggestion.get("diff"):
        errors.append(
            f"{where}: unresolved variants carry a drafted diff; the user must select an edit target first"
        )
    if not _is_measured(suggestion, optimization):
        errors += [
            f"{where}.{field}: claims a measured no-change verdict without scored evaluation evidence"
            for field in _SUGGESTION_PROSE
            if isinstance(suggestion.get(field), str)
            and _UNSUPPORTED_VERDICT.search(suggestion[field])
        ]
    return errors


def _verdict_errors(report: dict[str, Any], optimization: str) -> list[str]:
    """Report-wide no-change verdicts that the candidates do not all support.

    A blanket verdict holds only when every candidate was measured and none
    was accepted: one accepted or unevaluated candidate contradicts it.
    """
    suggestions = report.get("suggestions") or []
    supported = bool(suggestions) and all(
        _is_measured(s, optimization) and suggestion_status(s) != "accepted" for s in suggestions
    )
    if supported:
        return []
    return [
        f"{where}: claims a measured no-change verdict without scored evaluation evidence"
        for where, text in _report_text(report)
        if _UNSUPPORTED_VERDICT.search(text)
    ]


def validate_report(report: dict[str, Any]) -> list[str]:
    """Return every claim the recorded evaluation stages do not support."""
    optimization = evaluation_of(report)["optimization"]
    errors = []
    if optimization not in OPTIMIZATION_STAGES:
        errors.append(
            f"evaluation.optimization must be one of {OPTIMIZATION_STAGES}, got {optimization!r}"
        )
    for index, suggestion in enumerate(report.get("suggestions") or []):
        errors += _suggestion_errors(index, suggestion, optimization)
    return errors + _verdict_errors(report, optimization)


def evaluation_summary(report: dict[str, Any]) -> str:
    """One status line shared by the HTML page and the CLI text output."""
    evaluation = evaluation_of(report)
    suggestions = report.get("suggestions") or []
    counts = {status: 0 for status in SUGGESTION_STATUSES}
    for suggestion in suggestions:
        status = suggestion_status(suggestion)
        if status in counts:
            counts[status] += 1
    stages = f"Diagnosis: {evaluation['diagnosis']}. Optimization: {evaluation['optimization'].replace('_', ' ')}."
    tally = ", ".join(
        f"{counts[status]} {status}" for status in SUGGESTION_STATUSES if counts[status]
    )
    if evaluation["optimization"] != "run":
        detail = (
            STATIC_ONLY_STATEMENT
            if suggestions
            else f"{STATIC_ONLY_STATEMENT} {EMPTY_STATIC_STATEMENT}"
        )
    else:
        detail = "Measured statuses cite their skillopt baseline and candidate evidence."
    return " ".join(
        part for part in (stages, f"Candidates: {tally}." if tally else "", detail) if part
    )


def _text(value: Any) -> str:
    if isinstance(value, (list, tuple)):
        items = [str(item).strip() for item in value if str(item).strip()]
        return "; ".join(items) if items else NOT_SUPPLIED
    text = str(value).strip() if value is not None else ""
    return text or NOT_SUPPLIED


def target_identity(suggestion: dict[str, Any]) -> str:
    """Exact skill path, or an explicit unresolved-variant identity."""
    target = suggestion.get("target")
    if isinstance(target, str) and target.strip():
        return target.strip()
    name = suggestion.get("skill") or "unnamed"
    variants = suggestion.get("variants") or []
    if variants:
        paths = ", ".join(
            f"{v.get('path', '?')} (sha256 {str(v.get('sha256', '?'))[:12]})"
            if isinstance(v, dict)
            else str(v)
            for v in variants
        )
        return f"unresolved: {name}; variants {paths}; the user must select the edit target"
    if suggestion.get("owner") == "new-skill":
        return f"proposed new skill: {name}"
    return f"{name} (path {NOT_SUPPLIED})"


def missing_evidence(suggestion: dict[str, Any]) -> list[str]:
    """Fields a handoff needs that the suggestion does not supply."""
    gaps = [str(item) for item in suggestion.get("missing_evidence") or [] if str(item).strip()]
    required = {
        "observed failure and source conversation": suggestion.get("evidence"),
        "candidate mechanism": suggestion.get("mechanism") or suggestion.get("change"),
        "reproduction": suggestion.get("reproduction"),
        "acceptance checks": suggestion.get("acceptance_checks"),
    }
    gaps += [
        f"{label} {NOT_SUPPLIED}"
        for label, value in required.items()
        if _text(value) == NOT_SUPPLIED
    ]
    owner = suggestion.get("owner") or "skill"
    if owner == "tooling" and _text(suggestion.get("owner_target")) == NOT_SUPPLIED:
        gaps.append("tooling owner unresolved")
    if owner == "skill" and not has_target(suggestion):
        gaps.append("edit target unresolved")
    return gaps


def _owner_line(suggestion: dict[str, Any]) -> str:
    owner = suggestion.get("owner") or "skill"
    if owner == "tooling":
        owner_target = _text(suggestion.get("owner_target"))
        return (
            f"Owner: tooling ({owner_target}). The observed defect is in tooling, "
            "not proven to be an instruction defect."
        )
    return f"Owner: {owner}."


def _non_skill_route(suggestion: dict[str, Any]) -> str | None:
    """Why skillopt cannot evaluate this candidate directly, or None when it can."""
    owner = suggestion.get("owner") or "skill"
    if owner == "tooling":
        return (
            "This candidate is not a skillopt target: its owner is tooling "
            f"({_text(suggestion.get('owner_target'))}). Hand the defect to that owner. "
            "Use skillopt only for a separate instruction candidate that names an existing skill."
        )
    if owner == "new-skill":
        return (
            "No existing skill exists for skillopt to optimize. Route this gap through "
            "skillforge first; use skillopt only once an existing skill owns the behavior."
        )
    return None


def skillopt_prompt(suggestion: dict[str, Any]) -> str:
    """Copyable skillopt handoff built from the suggestion's own fields.

    Tooling and new-skill candidates get a routing note instead, because skillopt
    needs an existing skill, agent, or prompt artifact to baseline and patch.
    """
    route = _non_skill_route(suggestion)
    if route is not None:
        return "\n".join(
            [
                route,
                f"Target: {target_identity(suggestion)}.",
                f"Observed failure: {_text(suggestion.get('evidence'))}.",
                f"Acceptance checks: {_text(suggestion.get('acceptance_checks'))}.",
                "Do not apply changes without authorization.",
            ]
        )
    lines = [
        "Use skillopt to evaluate this unevaluated candidate.",
        f"Target: {target_identity(suggestion)}.",
        _owner_line(suggestion),
        f"Observed failure: {_text(suggestion.get('evidence'))}.",
        f"Candidate mechanism: {_text(suggestion.get('mechanism') or suggestion.get('change'))}.",
        f"Expected improvement: {_text(suggestion.get('expected_improvement'))}.",
        f"Reproduction: {_text(suggestion.get('reproduction'))}.",
        f"Acceptance checks: {_text(suggestion.get('acceptance_checks'))}.",
        f"Known risks and counterexamples: {_text(suggestion.get('risks'))}.",
        "First establish a scored baseline and held-out acceptance cases.",
        "Compare the unchanged skill with the smallest candidate patch.",
        "Report per-task outcomes, cost, regressions, and uncertainty.",
        "Do not claim improvement without passing the evaluation gate.",
        "Do not apply changes to installed skills without authorization.",
    ]
    if suggestion.get("variants") and not has_target(suggestion):
        lines.insert(3, "Ask the user to select one variant as the edit target before patching.")
    return "\n".join(lines)


def skillforge_prompt(suggestion: dict[str, Any]) -> str:
    """Copyable skillforge handoff built from the suggestion's own fields."""
    lines = [
        "Use skillforge to route this observed workflow gap.",
        f"Goal: {_text(suggestion.get('expected_improvement') or suggestion.get('change'))}.",
        f"Evidence: {_text(suggestion.get('evidence'))}.",
        f"Reproduction: {_text(suggestion.get('reproduction'))}.",
        f"Current target: {target_identity(suggestion)}.",
        _owner_line(suggestion),
        f"Acceptance checks: {_text(suggestion.get('acceptance_checks'))}.",
        "Search existing skills and ownership before proposing a new skill.",
        "Compare reuse, an existing-skill skillopt handoff, and justified creation.",
        "Return scope, non-goals, acceptance checks, and unresolved ownership.",
        "Do not create or modify installed skills without authorization.",
    ]
    return "\n".join(lines)
