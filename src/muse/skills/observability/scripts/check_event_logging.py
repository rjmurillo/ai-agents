#!/usr/bin/env python3
"""Operational event-logging contract checker.

Deterministic decision procedure for the producer-side event-logging contract.
Given a scenario describing what a code path does and what telemetry it emits,
it decides whether the emission complies and reports each missing required
event or prohibited item.

Canonical source: `.claude/skills/observability/references/event-logging-contract.md`
(the "MUST Emit" and "MUST NOT Emit" tables). Conformance is tested by
`tests/skills/observability/test_event_logging_contract.py`, which reads that
document and fails when a table row has no counterpart here.

Stricter/looser/different than canonical:
    Different, not stricter. The document is normative prose for humans. It
    covers row 8 of MUST Emit (free-form "diagnosis needs it") and row 6 of
    MUST NOT Emit (pillar choice), which are judgment calls this checker does
    not adjudicate. The checker enforces the mechanical subset from a
    STRUCTURED scenario, not real source code, so it cannot infer intent. A
    pure helper that declares no behavior flags is compliant with an empty
    emission, matching "Pure and Internal Helpers Emit Nothing".

Scenario shape (JSON object):
    behavior: object of boolean flags naming what the code path does
    emits:    array of events, each {"event": str, "fields": object, plus
              optional boolean prohibited-content flags}

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
from typing import Any

# behavior flag -> required emitted event categories (MUST Emit table).
REQUIRED: dict[str, tuple[str, ...]] = {
    "job_lifecycle": ("job_start", "job_completion"),
    "state_transition": ("state_transition",),
    "external_call": ("external_call_outcome",),
    "retry": ("retry_attempt", "retry_exhaustion"),
    "rate_limited": ("rate_limit",),
    "skip_changes_behavior": ("skip",),
    "error_not_swallowed": ("error",),
    "cancellation_differs": ("cancellation",),
}

# emitted-event flag -> prohibited-content finding (MUST NOT Emit table).
PROHIBITED_FLAGS: dict[str, str] = {
    "contains_secret": "secret_in_telemetry",
    "per_function_entry_exit": "function_entry_exit",
    "duplicate_of_lower_layer": "duplicate_event",
    "high_cardinality_no_value": "high_cardinality",
    "full_body": "full_body",
}

# required category -> fields that MUST be present on that event.
REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "job_completion": ("count", "duration", "result"),
    "external_call_outcome": ("operation", "status"),
    "retry_attempt": ("attempt",),
    "rate_limit": ("limit", "scope"),
    "skip": ("reason",),
    "error": ("operation",),
}


def required_categories(behavior: dict[str, Any]) -> list[str]:
    """Return the event categories a scenario's behavior flags require.

    A pure or internal helper (no flag set) requires nothing. Absence is valid.
    """
    required: list[str] = []
    for flag, categories in REQUIRED.items():
        if behavior.get(flag):
            required.extend(categories)
    return required


def _events_named(emits: list[dict[str, Any]], category: str) -> list[dict[str, Any]]:
    return [event for event in emits if event.get("event") == category]


def _missing_fields(category: str, emits: list[dict[str, Any]]) -> list[str]:
    needed = REQUIRED_FIELDS.get(category, ())
    findings: list[str] = []
    for event in _events_named(emits, category):
        fields = event.get("fields") or {}
        findings.extend(f"missing_field:{category}.{name}" for name in needed if name not in fields)
    return list(dict.fromkeys(findings))


def missing_required(behavior: dict[str, Any], emits: list[dict[str, Any]]) -> list[str]:
    """Return findings for absent required events or missing load-bearing fields."""
    findings: list[str] = []
    for category in required_categories(behavior):
        if not _events_named(emits, category):
            findings.append(f"missing_required_event:{category}")
            continue
        findings.extend(_missing_fields(category, emits))
    return findings


def _duplicate_findings(emits: list[dict[str, Any]]) -> list[str]:
    """One transition, one event: identical event and fields twice is a duplicate.

    Retry attempts differ by their `attempt` field, so repeated attempts are
    distinct events, not duplicates.
    """
    seen: set[str] = set()
    findings: list[str] = []
    for event in emits:
        key = json.dumps([event.get("event"), event.get("fields") or {}], sort_keys=True)
        if key in seen:
            finding = f"duplicate_event:{event.get('event', '?')}"
            if finding not in findings:
                findings.append(finding)
        seen.add(key)
    return findings


def prohibited_findings(emits: list[dict[str, Any]]) -> list[str]:
    """Return findings for prohibited content across all emitted events."""
    findings: list[str] = []
    for event in emits:
        for flag, finding in PROHIBITED_FLAGS.items():
            if event.get(flag):
                findings.append(f"{finding}:{event.get('event', '?')}")
    findings.extend(_duplicate_findings(emits))
    return list(dict.fromkeys(findings))


def classify_scenario(scenario: dict[str, Any]) -> dict[str, Any]:
    """Classify a scenario as compliant or not.

    Returns {"compliant": bool, "findings": [str, ...]}. Raises ValueError when
    `behavior` is not an object or `emits` is not an array of objects.
    """
    behavior = scenario.get("behavior")
    emits = scenario.get("emits")
    behavior = {} if behavior is None else behavior
    emits = [] if emits is None else emits
    if not isinstance(behavior, dict) or not isinstance(emits, list):
        raise ValueError("scenario needs object 'behavior' and array 'emits'")
    if not all(isinstance(event, dict) for event in emits):
        raise ValueError("every item in 'emits' must be an object")
    findings = missing_required(behavior, emits) + prohibited_findings(emits)
    return {"compliant": not findings, "findings": findings}


def _load_scenario(path: str) -> dict[str, Any]:
    raw = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    scenario = json.loads(raw)
    if not isinstance(scenario, dict):
        raise ValueError("scenario must be a JSON object")
    return scenario


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "scenario",
        nargs="?",
        default="-",
        help="Path to a scenario JSON file, or - for stdin.",
    )
    args = parser.parse_args(argv)
    try:
        result = classify_scenario(_load_scenario(args.scenario))
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0 if result["compliant"] else 1


if __name__ == "__main__":
    sys.exit(main())
