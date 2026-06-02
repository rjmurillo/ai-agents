#!/usr/bin/env python3
"""Record one issue's Phase 2 AI-triage result as JSON.

Reads the per-issue triage output emitted by ``.github/actions/ai-review`` from
environment variables and writes a small JSON document the summarize job
aggregates. Part of the backlog-triage workflow (issue #1799, ClawSweeper
pattern). Read-only: this never mutates GitHub state.

Input env vars (set by the workflow matrix step):
    ISSUE_NUMBER  Issue number (required, must be a positive integer).
    ISSUE_TITLE   Issue title (free text, untrusted; stored as-is).
    AI_VERDICT    Verdict from the ai-review action (PASS, WARN, etc.).
    AI_LABELS     Suggested labels as a JSON array string (area routing).
    AI_FINDINGS   Raw model output (complexity + routing rationale).

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
from pathlib import Path

DEFAULT_OUTPUT = "backlog-triage-result.json"
MAX_FINDINGS_CHARS = 4000
TRUNCATION_SUFFIX = "... (truncated)"


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
    if len(findings) > MAX_FINDINGS_CHARS:
        prefix_length = MAX_FINDINGS_CHARS - len(TRUNCATION_SUFFIX)
        findings = findings[:prefix_length] + TRUNCATION_SUFFIX

    return {
        "number": number,
        "title": env.get("ISSUE_TITLE") or "",
        "verdict": (env.get("AI_VERDICT") or "UNKNOWN").strip() or "UNKNOWN",
        "labels": parse_labels(env.get("AI_LABELS") or ""),
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
