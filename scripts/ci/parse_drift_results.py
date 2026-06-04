#!/usr/bin/env python3
"""Parse agent-drift JSON into the markdown body the drift-detection workflow posts.

This is the parse half of `.github/workflows/drift-detection.yml`. The workflow
runs `build/scripts/detect_agent_drift.py --output-format json`, then calls this
script to turn that JSON into the issue/comment body and an agent count. Keeping
the logic here (ADR-006: no logic in YAML) lets it be tested; the inline `python`
heredoc it replaces silently produced an empty body because it read snake_case
keys the emitter never writes (issue #2381).

Canonical source it mirrors: `build/scripts/detect_agent_drift.py`, function
`format_json`. That function is the only writer of the JSON shape this script
reads. The keys, copied verbatim from `format_json`:

    {
        "summary": {"driftDetected": <int>, ...},
        "results": [
            {
                "agentName": <str>,
                "overallSimilarity": <int | None>,
                "status": <str>,                 # "DRIFT DETECTED" at agent level
                "driftingSections": [<str>, ...],
                "sections": [
                    {"section": <str>, "similarity": <int>, "status": <str>}  # "DRIFT"
                ],
            }
        ],
    }

Stricter/looser/different than canonical: none. This script reads the shape
`format_json` writes and reports a missing key as a parse failure (exit 1)
rather than silently emitting an empty body, which is the bug it fixes.

EXIT CODES (ADR-035):
  0  - Success: details and count written
  1  - Error: malformed input (bad JSON, missing expected key)
  2  - Error: usage/configuration (file not found, bad argument)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_AGENT_DRIFT_STATUS = "DRIFT DETECTED"
_SECTION_DRIFT_STATUS = "DRIFT"


def _format_agent_entry(agent: dict[str, Any]) -> str:
    """Render one drifting agent as a markdown block.

    Raises KeyError if a required key from the canonical JSON shape is absent;
    the caller turns that into an exit-1 parse failure.
    """
    entry = f"### {agent['agentName']}\n"
    entry += f"- **Overall similarity**: {agent['overallSimilarity']}%\n"

    drifting_sections = agent.get("driftingSections") or []
    if drifting_sections:
        entry += f"- **Drifting sections**: {', '.join(drifting_sections)}\n"

    sections = agent.get("sections") or []
    drift_sections = [s for s in sections if s.get("status") == _SECTION_DRIFT_STATUS]
    if drift_sections:
        entry += "\n**Section Details:**\n"
        for section in drift_sections:
            entry += f"- {section['section']}: {section['similarity']}% similar\n"

    return entry


def build_drift_details(results: dict[str, Any]) -> tuple[str, int]:
    """Build the markdown body and the drift-detected count from parsed drift JSON.

    Returns (markdown_body, agent_count). Reads the camelCase keys written by
    `build/scripts/detect_agent_drift.py:format_json`.
    """
    entries: list[str] = []
    for agent in results.get("results", []):
        if agent.get("status") == _AGENT_DRIFT_STATUS:
            entries.append(_format_agent_entry(agent))

    body = "\n".join(entries)
    count = int(results.get("summary", {}).get("driftDetected", 0))
    return body, count


def _read_results(json_path: Path) -> dict[str, Any]:
    try:
        text = json_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise SystemExit(_fail(f"input not found: {json_path}", code=2)) from exc
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise SystemExit(_fail(f"invalid JSON in {json_path}: {exc}", code=1)) from exc


def _fail(message: str, *, code: int) -> int:
    print(f"parse_drift_results: {message}", file=sys.stderr)
    return code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        required=True,
        type=Path,
        help="path to the drift JSON (detect_agent_drift.py --output-format json)",
    )
    parser.add_argument(
        "--details-out",
        required=True,
        type=Path,
        help="path to write the markdown drift details",
    )
    parser.add_argument(
        "--count-out",
        required=True,
        type=Path,
        help="path to write the drift-detected agent count",
    )
    args = parser.parse_args(argv)

    results = _read_results(args.input)

    try:
        body, count = build_drift_details(results)
    except KeyError as exc:
        return _fail(f"missing expected key {exc} in drift JSON", code=1)
    except (TypeError, ValueError) as exc:
        return _fail(f"malformed drift JSON: {exc}", code=1)

    args.details_out.write_text(body, encoding="utf-8")
    args.count_out.write_text(str(count), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
