#!/usr/bin/env python3
"""Write a GitHub Actions should-run output from dorny/paths-filter results."""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Mapping

_OUTPUT_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")


def should_run(
    event_name: str, filter_outputs: Mapping[str, object], filter_keys: list[str]
) -> bool:
    if event_name == "workflow_dispatch":
        return True
    return any(filter_outputs.get(key) == "true" for key in filter_keys)


def parse_filter_keys(raw_filter_keys: str) -> list[str]:
    return [key.strip() for key in raw_filter_keys.split(",") if key.strip()]


def parse_filter_outputs(raw_filter_outputs: str) -> dict[str, object]:
    if not raw_filter_outputs:
        return {}
    parsed = json.loads(raw_filter_outputs)
    if not isinstance(parsed, dict):
        raise ValueError("FILTER_OUTPUTS must decode to a JSON object")
    return parsed


def write_output(output_path: Path, output_name: str, value: bool) -> None:
    if not _OUTPUT_NAME_PATTERN.fullmatch(output_name):
        raise ValueError(f"invalid GitHub output name: {output_name!r}")

    rendered_value = "true" if value else "false"
    with output_path.open("a", encoding="utf-8") as handle:
        handle.write(f"{output_name}={rendered_value}\n")


def main() -> int:
    try:
        output_name = os.environ["OUTPUT_NAME"]
        output_path = Path(os.environ["GITHUB_OUTPUT"])
        event_name = os.environ.get("GH_EVENT_NAME", "")
        filter_keys = parse_filter_keys(os.environ.get("FILTER_KEYS", ""))
        filter_outputs = parse_filter_outputs(os.environ.get("FILTER_OUTPUTS", "{}"))
        value = should_run(event_name, filter_outputs, filter_keys)
        write_output(output_path, output_name, value)
    except (KeyError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
