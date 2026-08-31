#!/usr/bin/env python3
"""Evaluate a proposed API/schema/module design against behavior-first rules.

The skill body (SKILL.md) is the decision procedure a human or agent follows.
This script is the load-bearing check behind it: given a structured proposal, it
applies the behavior-first heuristics and reports which axes need revision.

The heuristics are advisory, not a proof of correctness. They encode the
distinctions the issue requires: explicit business state versus hidden
reconstruction, source/transport shape as an integration concern, domain
operations over CRUD only when invariants justify it (CRUD stays correct when it
fits), temporal/effective-time modeling, and YAGNI rejection of speculative
mechanisms.

EXIT CODES:
  0  - design adopts as-is (no axis needs revision)
  10 - at least one axis needs revision
  1  - tool error (bad input, file not found, invalid proposal)
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence

EXIT_ADOPT = 0
EXIT_ERROR = 1
EXIT_REVISE = 10

_STATE_VALUES = ("explicit", "reconstructed")
_API_VALUES = ("crud", "domain")

_REQUIRED_KEYS: dict[str, type | tuple[type, ...]] = {
    "business_question": str,
    "state_representation": str,
    "fact_is_first_class": bool,
    "api_style": str,
    "behavior_has_invariant": bool,
    "temporal_question": bool,
    "history_modeled": bool,
    "mirrors_source_payload": bool,
    "behavior_diverges_from_source": bool,
    "mechanism_has_behavioral_need": bool,
}


@dataclass(frozen=True)
class Finding:
    """One axis of the design, evaluated."""

    axis: str
    verdict: str  # "adopt" or "revise"
    message: str


def _require_bool(proposal: dict[str, Any], key: str) -> bool:
    value = proposal[key]
    if not isinstance(value, bool):
        raise ValueError(f"'{key}' must be a boolean, got {type(value).__name__}")
    return value


def validate_proposal(proposal: Any) -> dict[str, Any]:
    """Validate structure at the trust boundary. Raise ValueError on bad input."""
    if not isinstance(proposal, dict):
        raise ValueError(f"proposal must be an object, got {type(proposal).__name__}")
    missing = [k for k in _REQUIRED_KEYS if k not in proposal]
    if missing:
        raise ValueError(f"proposal missing required keys: {', '.join(sorted(missing))}")
    question = proposal["business_question"]
    if not isinstance(question, str) or not question.strip():
        raise ValueError("'business_question' must be a non-empty string")
    if proposal["state_representation"] not in _STATE_VALUES:
        raise ValueError(f"'state_representation' must be one of {_STATE_VALUES}")
    if proposal["api_style"] not in _API_VALUES:
        raise ValueError(f"'api_style' must be one of {_API_VALUES}")
    for key, expected in _REQUIRED_KEYS.items():
        if expected is bool:
            _require_bool(proposal, key)
    mechanism = proposal.get("speculative_mechanism")
    if mechanism is not None and not isinstance(mechanism, str):
        raise ValueError("'speculative_mechanism' must be a string or null")
    return proposal


def check_reconstruction(proposal: dict[str, Any]) -> Finding:
    """Explicit business state versus hidden reconstruction."""
    if proposal["fact_is_first_class"] and proposal["state_representation"] == "reconstructed":
        return Finding(
            "state",
            "revise",
            "Record this fact as explicit business state. Reconstructing a "
            "first-class business fact from incidental fact/output rows is a "
            "hidden obligation, not a safe derivation.",
        )
    return Finding("state", "adopt", "State representation matches the business need.")


def check_operation(proposal: dict[str, Any]) -> Finding:
    """Domain operation versus CRUD. CRUD stays correct when it fits."""
    invariant = proposal["behavior_has_invariant"]
    style = proposal["api_style"]
    if invariant and style == "crud":
        return Finding(
            "operation",
            "revise",
            "Expose one domain operation. Generic CRUD leaks the multi-step "
            "mechanics of a behavior that carries invariants or transaction "
            "semantics.",
        )
    if not invariant and style == "domain":
        return Finding(
            "operation",
            "revise",
            "Prefer CRUD. The behavior has no invariant, so a domain verb here "
            "is ceremony. Do not manufacture domain commands to avoid CRUD.",
        )
    if not invariant and style == "crud":
        return Finding(
            "operation",
            "adopt",
            "CRUD is correct. Simple create/read/update/delete with no extra "
            "invariant does not need a domain operation.",
        )
    return Finding("operation", "adopt", "Domain operation matches the behavior's invariant.")


def check_temporal(proposal: dict[str, Any]) -> Finding:
    """History/effective-time modeling when the question depends on time."""
    if proposal["temporal_question"] and not proposal["history_modeled"]:
        return Finding(
            "temporal",
            "revise",
            "Model history or effective-time. The business question depends on "
            "what was true at a prior time, so overwriting current state loses "
            "the answer.",
        )
    return Finding("temporal", "adopt", "Time semantics match the business question.")


def check_source_shape(proposal: dict[str, Any]) -> Finding:
    """Source/transport shape is an integration concern, not the domain model."""
    if proposal["mirrors_source_payload"] and proposal["behavior_diverges_from_source"]:
        return Finding(
            "source-shape",
            "revise",
            "Treat the source payload as an integration contract. Derive the "
            "internal model from the business behavior, not from the payload, "
            "ORM, or transport shape.",
        )
    return Finding("source-shape", "adopt", "Internal model is derived from behavior.")


def check_speculation(proposal: dict[str, Any]) -> Finding:
    """YAGNI: reject a speculative mechanism with no current behavioral need.

    Consumes the quality/YAGNI doctrine owned by #5397 rather than restating it.
    """
    mechanism = proposal.get("speculative_mechanism")
    if mechanism and not proposal["mechanism_has_behavioral_need"]:
        return Finding(
            "speculation",
            "revise",
            f"Reject {mechanism}. No current behavior needs it. Apply the "
            "YAGNI/minimal-implementation doctrine owned by #5397 (golden-principles).",
        )
    return Finding("speculation", "adopt", "No speculative mechanism to reject.")


_CHECKS = (
    check_reconstruction,
    check_operation,
    check_temporal,
    check_source_shape,
    check_speculation,
)


def evaluate(proposal: Any) -> list[Finding]:
    """Validate and evaluate a proposal against every behavior-first axis.

    Returns an EvaluationResult: one Finding per axis.
    """
    validated = validate_proposal(proposal)
    return [check(validated) for check in _CHECKS]


# An EvaluationResult is the ordered list of per-axis findings.
EvaluationResult = list[Finding]


def needs_revision(findings: Sequence[Finding]) -> bool:
    return any(f.verdict == "revise" for f in findings)


def _format(findings: Sequence[Finding]) -> str:
    lines = []
    for f in findings:
        mark = "REVISE" if f.verdict == "revise" else "adopt "
        lines.append(f"[{mark}] {f.axis}: {f.message}")
    verdict = "revise boundaries/state" if needs_revision(findings) else "adopt"
    lines.append(f"Overall: {verdict}")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("proposal", type=Path, help="JSON file describing the proposed design.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        raw = args.proposal.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"Error: cannot read {args.proposal}: {exc}", file=sys.stderr)
        return EXIT_ERROR
    try:
        proposal = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"Error: invalid JSON in {args.proposal}: {exc}", file=sys.stderr)
        return EXIT_ERROR
    try:
        findings = evaluate(proposal)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return EXIT_ERROR
    print(_format(findings))
    return EXIT_REVISE if needs_revision(findings) else EXIT_ADOPT


if __name__ == "__main__":
    sys.exit(main())
