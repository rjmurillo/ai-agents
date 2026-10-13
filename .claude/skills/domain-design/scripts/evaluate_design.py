#!/usr/bin/env python3
"""Check a proposed API, schema, or module design against behavior-first rules.

The skill body is the decision procedure. This script is the check behind it:
given a structured proposal, it reports which axes need revision. It encodes a
decision table over answers the author supplies, so it is advisory. It cannot
tell whether the answers are true; a reviewer reads them against the design.

Axes: explicit state versus hidden reconstruction, source shape as an
integration concern, domain operation versus CRUD, temporal modeling, a
speculative mechanism with no behavioral need, and a walk of representative
use cases.

Exit codes:
  0  adopt: no axis needs revision
  1  revise: at least one axis needs revision
  2  bad input: unreadable file, invalid JSON, or invalid proposal
"""

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

EXIT_ADOPT = 0
EXIT_REVISE = 1
EXIT_BAD_INPUT = 2

STATE_VALUES = ("explicit", "reconstructed")
API_VALUES = ("crud", "domain")

_STRING_KEYS = ("business_question", "state_representation", "api_style")
_BOOL_KEYS = (
    "fact_is_first_class",
    "behavior_has_invariant",
    "temporal_question",
    "history_modeled",
    "mirrors_source_payload",
    "behavior_diverges_from_source",
    "mechanism_has_behavioral_need",
)


@dataclass(frozen=True)
class Finding:
    """One axis of the design, evaluated."""

    axis: str
    verdict: str
    message: str


def _check_use_cases(use_cases: Any) -> None:
    if not isinstance(use_cases, list) or not use_cases:
        raise ValueError("'use_cases' must be a non-empty list")
    for index, case in enumerate(use_cases):
        if not isinstance(case, dict):
            raise ValueError(f"'use_cases[{index}]' must be an object")
        question = case.get("question")
        if not isinstance(question, str) or not question.strip():
            raise ValueError(f"'use_cases[{index}].question' must be a non-empty string")
        if not isinstance(case.get("needs_reconstruction"), bool):
            raise ValueError(f"'use_cases[{index}].needs_reconstruction' must be a boolean")


def validate_proposal(proposal: Any) -> dict[str, Any]:
    """Validate structure at the trust boundary. Raise ValueError on bad input."""
    if not isinstance(proposal, dict):
        raise ValueError(f"proposal must be an object, got {type(proposal).__name__}")
    required = (*_STRING_KEYS, *_BOOL_KEYS, "use_cases")
    missing = sorted(key for key in required if key not in proposal)
    if missing:
        raise ValueError(f"proposal missing required keys: {', '.join(missing)}")
    for key in _STRING_KEYS:
        if not isinstance(proposal[key], str) or not proposal[key].strip():
            raise ValueError(f"'{key}' must be a non-empty string")
    if proposal["state_representation"] not in STATE_VALUES:
        raise ValueError(f"'state_representation' must be one of {STATE_VALUES}")
    if proposal["api_style"] not in API_VALUES:
        raise ValueError(f"'api_style' must be one of {API_VALUES}")
    for key in _BOOL_KEYS:
        if not isinstance(proposal[key], bool):
            raise ValueError(f"'{key}' must be a boolean, got {type(proposal[key]).__name__}")
    mechanism = proposal.get("speculative_mechanism")
    if mechanism is not None and not isinstance(mechanism, str):
        raise ValueError("'speculative_mechanism' must be a string or null")
    _check_use_cases(proposal["use_cases"])
    return proposal


def check_reconstruction(proposal: dict[str, Any]) -> Finding:
    """Explicit business state versus hidden reconstruction."""
    if proposal["fact_is_first_class"] and proposal["state_representation"] == "reconstructed":
        return Finding(
            "state",
            "revise",
            "Record this fact as explicit business state. Rebuilding a "
            "first-class fact from incidental fact or output rows is a hidden "
            "obligation, not a safe derivation.",
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
            "Prefer CRUD. The behavior has no invariant, so a domain verb is "
            "ceremony. Do not invent domain commands to avoid CRUD.",
        )
    if style == "crud":
        return Finding(
            "operation",
            "adopt",
            "CRUD is correct. Plain create, read, update, delete with no extra "
            "invariant needs no domain operation.",
        )
    return Finding("operation", "adopt", "Domain operation matches the behavior's invariant.")


def check_temporal(proposal: dict[str, Any]) -> Finding:
    """History or effective-time modeling when the question depends on time."""
    if proposal["temporal_question"] and not proposal["history_modeled"]:
        return Finding(
            "temporal",
            "revise",
            "Model history or effective time. The question depends on what was "
            "true at a prior time, so overwriting current state loses the answer.",
        )
    return Finding("temporal", "adopt", "Time semantics match the business question.")


def check_source_shape(proposal: dict[str, Any]) -> Finding:
    """Source or transport shape is an integration concern, not the domain model."""
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
    """Reject a speculative mechanism with no current behavioral need.

    The quality principles (minimal implementation, YAGNI) belong to the
    artifact-neutral-code-quality capability. This axis applies them; it does
    not restate them.
    """
    mechanism = proposal.get("speculative_mechanism")
    if mechanism and not proposal["mechanism_has_behavioral_need"]:
        return Finding(
            "speculation",
            "revise",
            f"Reject {mechanism}. No current behavior needs it. Apply the "
            "artifact-neutral-code-quality principles.",
        )
    return Finding("speculation", "adopt", "No speculative mechanism to reject.")


def check_use_cases(proposal: dict[str, Any]) -> Finding:
    """Walk representative questions; reconstruction is design evidence."""
    failing = [c["question"] for c in proposal["use_cases"] if c["needs_reconstruction"]]
    if failing:
        listed = "; ".join(failing)
        return Finding(
            "use-cases",
            "revise",
            f"These questions need joins, probes, or inferred time to answer: "
            f"{listed}. Treat that as evidence the state or boundary is wrong.",
        )
    return Finding("use-cases", "adopt", "Every walked question reads directly.")


CHECKS = (
    check_reconstruction,
    check_operation,
    check_temporal,
    check_source_shape,
    check_speculation,
    check_use_cases,
)


def evaluate(proposal: Any) -> list[Finding]:
    """Validate a proposal and return one finding per axis."""
    validated = validate_proposal(proposal)
    return [check(validated) for check in CHECKS]


def needs_revision(findings: Sequence[Finding]) -> bool:
    return any(f.verdict == "revise" for f in findings)


def format_report(findings: Sequence[Finding]) -> str:
    lines = [
        f"[{'REVISE' if f.verdict == 'revise' else 'adopt '}] {f.axis}: {f.message}"
        for f in findings
    ]
    lines.append(
        "Overall: " + ("revise boundaries or state" if needs_revision(findings) else "adopt")
    )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("proposal", type=Path, help="JSON file describing the proposed design.")
    return parser


def _load(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"cannot read {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc}") from exc


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        findings = evaluate(_load(args.proposal))
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return EXIT_BAD_INPUT
    print(format_report(findings))
    return EXIT_REVISE if needs_revision(findings) else EXIT_ADOPT


if __name__ == "__main__":
    sys.exit(main())
