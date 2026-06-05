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
        "duration": <float>,
        "threshold": <int>,
        "summary": {"driftDetected": <int>, ...},
        "results": [
            {
                "agentName": <str>,
                "comparison": <str>,
                "overallSimilarity": <float | None>,
                "status": <str>,                 # "DRIFT DETECTED" at agent level
                "driftingSections": [<str>, ...],
                "sections": [
                    {
                        "section": <str>,
                        "similarity": <float>,
                        "claudeHas": <bool>,
                        "vscodeHas": <bool>,
                        "status": <str>,
                    }  # "DRIFT"
                ],
            }
        ],
    }

Stricter/looser/different than canonical: this script validates only the fields
needed to render the issue body and agent count. It intentionally ignores
canonical fields that the issue body does not render (`duration`, `threshold`,
agent `comparison`, and section `claudeHas`/`vscodeHas`).

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

_AGENT_DRIFT_STATUS = "DRIFT DETECTED"
_SECTION_DRIFT_STATUS = "DRIFT"


def _require_mapping(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise TypeError(f"{name} must be an object")
    return value


def _require_list(value: object, name: str) -> list[object]:
    if not isinstance(value, list):
        raise TypeError(f"{name} must be an array")
    return value


def _required_key(mapping: dict[str, object], key: str, owner: str) -> object:
    if key not in mapping:
        raise KeyError(f"{owner}.{key}")
    value = mapping[key]
    if value is None:
        raise TypeError(f"{owner}.{key} must not be null")
    return value


def _format_agent_entry(agent: dict[str, object]) -> str:
    """Render one drifting agent as a markdown block.

    Raises KeyError if a required key from the canonical JSON shape is absent;
    the caller turns that into an exit-1 parse failure.
    """
    agent_name = _required_key(agent, "agentName", "agent")
    similarity = _required_key(agent, "overallSimilarity", "agent")

    entry = f"### {agent_name}\n"
    entry += f"- **Overall similarity**: {similarity}%\n"

    drifting_sections_raw = agent.get("driftingSections")
    drifting_sections = [] if drifting_sections_raw is None else _require_list(
        drifting_sections_raw,
        "agent.driftingSections",
    )
    if drifting_sections:
        entry += f"- **Drifting sections**: {', '.join(str(s) for s in drifting_sections)}\n"

    sections_raw = agent.get("sections")
    sections = [] if sections_raw is None else _require_list(sections_raw, "agent.sections")
    drift_sections = []
    for index, raw_section in enumerate(sections):
        section = _require_mapping(raw_section, f"agent.sections[{index}]")
        if section.get("status") == _SECTION_DRIFT_STATUS:
            drift_sections.append(section)
    if drift_sections:
        entry += "\n**Section Details:**\n"
        for section in drift_sections:
            section_name = _required_key(section, "section", "section")
            similarity = _required_key(section, "similarity", "section")
            entry += f"- {section_name}: {similarity}% similar\n"

    return entry


def build_drift_details(results: object) -> tuple[str, int]:
    """Build the markdown body and the drift-detected count from parsed drift JSON.

    Returns (markdown_body, agent_count). Reads the camelCase keys written by
    `build/scripts/detect_agent_drift.py:format_json`.
    """
    results = _require_mapping(results, "results payload")
    agents = _require_list(_required_key(results, "results", "payload"), "payload.results")

    entries: list[str] = []
    for index, raw_agent in enumerate(agents):
        agent = _require_mapping(raw_agent, f"payload.results[{index}]")
        if agent.get("status") == _AGENT_DRIFT_STATUS:
            entries.append(_format_agent_entry(agent))

    body = "\n".join(entries)
    summary = _require_mapping(_required_key(results, "summary", "payload"), "payload.summary")
    drift_detected = _required_key(summary, "driftDetected", "summary")
    count = int(drift_detected)
    return body, count


def _read_results(json_path: Path) -> object:
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
