#!/usr/bin/env python3
"""Record one issue's Phase 2 AI-triage result as JSON.

Reads the per-issue triage output emitted by ``.github/actions/ai-review`` from
environment variables and writes a small JSON document the summarize job
aggregates. Part of the backlog-triage workflow (issue #2260, ClawSweeper Phase
2). Read-only: this never mutates GitHub state.

Input env vars (set by the workflow matrix step):
    ISSUE_NUMBER  Issue number (required, must be a positive integer).
    ISSUE_TITLE   Issue title (free text, untrusted; stored as-is).
    AI_VERDICT    Verdict from the ai-review action (PASS, WARN, etc.).
    AI_LABELS     Suggested labels as a JSON array string (area routing).
    AI_FINDINGS   Raw model output. Prefer a JSON object with the Phase 2 fields.

Output: ``backlog-triage-result.json`` in the current directory (override with --output).

Exit codes follow ADR-035:
    0 - Success
    2 - Config error (missing or invalid ISSUE_NUMBER)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

DEFAULT_OUTPUT = "backlog-triage-result.json"
MAX_FINDINGS_CHARS = 4000
TRUNCATION_SUFFIX = "... (truncated)"
VALID_COMPLEXITY = {"junior", "medior", "senior"}
VALID_SCOPE_STATUS = {"too_broad", "too_narrow", "right_sized", "unknown"}


def parse_labels(raw: str) -> list[str]:
    """Parse the AI_LABELS JSON array, tolerating empty or malformed input.

    The ai-review action emits a JSON array string. A missing or unparseable
    value degrades to an empty list rather than failing the whole run.
    """

    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    return [str(item) for item in data]


def parse_structured_findings(raw_findings: str, labels: list[str]) -> dict[str, object]:
    """Extract the five Phase 2 fields from model output.

    ``AI_FINDINGS`` is raw model output from the action. The categorize prompt
    asks for JSON, but this parser tolerates surrounding text and falls back to
    typed unknown values so malformed model output remains reviewable.
    """

    payload = _extract_json_object(raw_findings)
    return {
        "complexity_classification": _parse_complexity(payload),
        "area_routing": _parse_area_routing(payload, labels),
        "dependency_detection": _parse_dependency_detection(payload),
        "scope_assessment": _parse_scope_assessment(payload),
        "evidence_check": _parse_evidence_check(payload),
    }


def _extract_json_object(text: str) -> Mapping[str, Any]:
    if not text:
        return {}
    candidates = [text.strip()]
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        candidates.append(text[start : end + 1])
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except (json.JSONDecodeError, ValueError, TypeError):
            continue
        if isinstance(parsed, dict):
            return parsed
    return {}


def _parse_complexity(payload: Mapping[str, Any]) -> str:
    raw = payload.get("complexity_classification", payload.get("complexity", ""))
    value = str(raw or "").strip().lower()
    return value if value in VALID_COMPLEXITY else "unknown"


def _parse_area_routing(payload: Mapping[str, Any], labels: list[str]) -> list[str]:
    raw = payload.get("area_routing", payload.get("agent_labels", []))
    values = _string_list(raw)
    if not values:
        values = [label for label in labels if label.startswith("agent-")]
    return values


def _parse_dependency_detection(payload: Mapping[str, Any]) -> dict[str, object]:
    raw = payload.get("dependency_detection", {})
    if not isinstance(raw, Mapping):
        raw = {}
    return {
        "blocked_by": _issue_number_list(raw.get("blocked_by")),
        "blocks": _issue_number_list(raw.get("blocks")),
        "related": _issue_number_list(raw.get("related")),
        "notes": str(raw.get("notes") or ""),
    }


def _parse_scope_assessment(payload: Mapping[str, Any]) -> dict[str, object]:
    raw = payload.get("scope_assessment", {})
    if not isinstance(raw, Mapping):
        raw = {}
    status = str(raw.get("status") or "unknown").strip().lower().replace("-", "_")
    if status not in VALID_SCOPE_STATUS:
        status = "unknown"
    return {
        "status": status,
        "needs_decomposition": _bool_or_false(raw.get("needs_decomposition")),
        "can_batch": _bool_or_false(raw.get("can_batch")),
        "notes": str(raw.get("notes") or ""),
    }


def _parse_evidence_check(payload: Mapping[str, Any]) -> dict[str, object]:
    raw = payload.get("evidence_check", {})
    if not isinstance(raw, Mapping):
        raw = {}
    return {
        "has_repro_steps": _bool_or_none(raw.get("has_repro_steps")),
        "has_acceptance_criteria": _bool_or_none(raw.get("has_acceptance_criteria")),
        "has_enough_context": _bool_or_none(raw.get("has_enough_context")),
        "missing": _string_list(raw.get("missing")),
    }


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _issue_number_list(value: object) -> list[int]:
    numbers: list[int] = []
    if not isinstance(value, list):
        return numbers
    for item in value:
        if isinstance(item, bool):
            continue
        try:
            number = int(item)
        except (TypeError, ValueError):
            continue
        if number > 0:
            numbers.append(number)
    return numbers


def _bool_or_false(value: object) -> bool:
    return value is True


def _bool_or_none(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    return None


def build_result(env: dict[str, str]) -> dict[str, object]:
    """Build the per-issue result document from environment variables.

    Raises ``ValueError`` when ISSUE_NUMBER is missing or not a positive int.
    """

    raw_number = (env.get("ISSUE_NUMBER") or "").strip()
    if not raw_number:
        raise ValueError("ISSUE_NUMBER is required")
    try:
        number = int(raw_number)
    except ValueError as err:
        raise ValueError(f"ISSUE_NUMBER must be an integer: {raw_number!r}") from err
    if number <= 0:
        raise ValueError(f"ISSUE_NUMBER must be positive: {number}")

    findings = env.get("AI_FINDINGS") or ""
    labels = parse_labels(env.get("AI_LABELS") or "")
    structured = parse_structured_findings(findings, labels)
    if len(findings) > MAX_FINDINGS_CHARS:
        prefix_length = MAX_FINDINGS_CHARS - len(TRUNCATION_SUFFIX)
        findings = findings[:prefix_length] + TRUNCATION_SUFFIX

    return {
        "number": number,
        "title": env.get("ISSUE_TITLE") or "",
        "verdict": (env.get("AI_VERDICT") or "UNKNOWN").strip() or "UNKNOWN",
        "labels": labels,
        **structured,
        "findings": findings,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Record one issue's Phase 2 AI-triage result as JSON.",
    )
    parser.add_argument(
        "--output", default=DEFAULT_OUTPUT,
        help=f"Path to write the result JSON (default: {DEFAULT_OUTPUT}).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = build_result(dict(os.environ))
    except ValueError as err:
        print(str(err), file=sys.stderr)
        return 2
    Path(args.output).write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"Wrote triage result for issue #{result['number']} to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
