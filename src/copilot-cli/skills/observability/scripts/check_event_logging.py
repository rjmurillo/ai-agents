#!/usr/bin/env python3
"""Operational event-logging contract checker.

Deterministic decision procedure for the producer-side event-logging contract.
Given a scenario describing what a code path does and what telemetry it emits,
decides whether the emission complies with the contract, and reports the
specific missing-required or prohibited-content findings when it does not.

CANONICAL SOURCE (canonical-source-mirror rule):
    .claude/skills/observability/references/event-logging-contract.md

This checker encodes that document's two tables. The "MUST Emit" triggers and
their required event categories, quoted from the contract:

    1 Job/process where duration/outcome matters -> start + completion
    2 Externally meaningful state transition     -> transition
    3 External dependency call                   -> outcome (identity+status)
    4 Retry path            -> retry-attempt + retry-exhaustion (+backoff)
    5 Quota or rate-limit hit                    -> rate-limit
    6 Skip that changes observable behavior      -> skip (with reason)
    7 Error not swallowed                        -> error (operation context)
    9 Cancellation/timeout differing from failure -> cancellation

The "MUST NOT Emit" prohibitions, quoted from the contract:

    1 Every function entry/exit
    2 Duplicate events at every layer for one transition
    3 Secrets, tokens, credentials, unnecessary PII
    4 Entire request/response bodies by default
    5 High-cardinality telemetry with no operational justification

Stricter/looser/different than canonical:
    Different, not stricter. The document is normative prose for humans and
    covers row 8 (free-form "diagnosis needs it") and pillar-choice (row 6 of
    MUST NOT), which are judgement calls this checker does not adjudicate. The
    checker enforces the mechanical subset: it reads a STRUCTURED scenario, not
    real source code, so it cannot infer intent. A pure/internal helper that
    declares no triggers is compliant with an empty emission (absence is valid),
    matching the "Pure and Internal Helpers Emit Nothing" section.

EXIT CODES (ADR-035):
    0 - Compliant scenario
    1 - Non-compliant: a required event is missing or prohibited content present
    2 - Config: malformed scenario or bad arguments
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# behavior flag -> required emitted event categories (MUST Emit table).
_REQUIRED: dict[str, tuple[str, ...]] = {
    "job_lifecycle": ("job_start", "job_completion"),
    "state_transition": ("state_transition",),
    "external_call": ("external_call_outcome",),
    "retry": ("retry_attempt", "retry_exhaustion"),
    "rate_limited": ("rate_limit",),
    "skip_changes_behavior": ("skip",),
    "error_not_swallowed": ("error",),
    "cancellation_differs": ("cancellation",),
}

# emitted-event field -> prohibited-content finding (MUST NOT Emit table).
_PROHIBITED_FLAGS: dict[str, str] = {
    "contains_secret": "secret_in_telemetry",
    "per_function_entry_exit": "function_entry_exit",
    "duplicate_of_lower_layer": "duplicate_event",
    "high_cardinality_no_value": "high_cardinality",
}

# required category -> fields that MUST be present on that event.
_REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "job_completion": ("count", "duration", "result"),
    "external_call_outcome": ("operation", "status"),
    "skip": ("reason",),
    "error": ("operation",),
}


def required_categories(behavior: dict) -> list[str]:
    """Required emitted categories for a scenario's behavior flags.

    A pure/internal helper (no trigger set) requires nothing; absence is valid.
    """
    required: list[str] = []
    for flag, categories in _REQUIRED.items():
        if behavior.get(flag):
            required.extend(categories)
    return required


def _emitted_categories(emits: list[dict]) -> list[str]:
    return [str(e.get("event", "")) for e in emits]


def missing_required(behavior: dict, emits: list[dict]) -> list[str]:
    """Findings for required events that are absent or missing load-bearing fields."""
    present = _emitted_categories(emits)
    findings: list[str] = []
    for category in required_categories(behavior):
        if category not in present:
            findings.append(f"missing_required_event:{category}")
            continue
        findings.extend(_missing_fields(category, emits))
    return findings


def _missing_fields(category: str, emits: list[dict]) -> list[str]:
    needed = _REQUIRED_FIELDS.get(category)
    if not needed:
        return []
    event = next(e for e in emits if e.get("event") == category)
    fields = event.get("fields") or {}
    return [
        f"missing_field:{category}.{name}" for name in needed if name not in fields
    ]


def prohibited_findings(emits: list[dict]) -> list[str]:
    """Findings for prohibited content across all emitted events."""
    findings: list[str] = []
    for event in emits:
        for flag, finding in _PROHIBITED_FLAGS.items():
            if event.get(flag):
                findings.append(f"{finding}:{event.get('event', '?')}")
    findings.extend(_duplicate_findings(emits))
    return findings


def _duplicate_findings(emits: list[dict]) -> list[str]:
    """One transition, one event: a category emitted more than once duplicates."""
    counts: dict[str, int] = {}
    for category in _emitted_categories(emits):
        counts[category] = counts.get(category, 0) + 1
    return [
        f"duplicate_event:{category}"
        for category, count in counts.items()
        if count > 1
    ]


def classify_scenario(scenario: dict) -> dict:
    """Classify a scenario as compliant or not, with findings.

    Returns {"compliant": bool, "findings": [str, ...]}.
    """
    behavior = scenario.get("behavior")
    emits = scenario.get("emits")
    behavior = {} if behavior is None else behavior
    emits = [] if emits is None else emits
    if not isinstance(behavior, dict) or not isinstance(emits, list):
        raise ValueError("scenario needs object 'behavior' and array 'emits'")
    findings = missing_required(behavior, emits) + prohibited_findings(emits)
    return {"compliant": not findings, "findings": findings}


def _load_scenario(path: str | None) -> dict:
    raw = sys.stdin.read() if path in (None, "-") else Path(path).read_text()
    scenario = json.loads(raw)
    if not isinstance(scenario, dict):
        raise ValueError("scenario must be a JSON object")
    return scenario


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "scenario",
        nargs="?",
        default="-",
        help="Path to a scenario JSON file, or - for stdin.",
    )
    args = parser.parse_args(argv)
    try:
        scenario = _load_scenario(args.scenario)
        result = classify_scenario(scenario)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0 if result["compliant"] else 1


if __name__ == "__main__":
    sys.exit(main())
