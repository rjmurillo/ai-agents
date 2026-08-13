#!/usr/bin/env python3
"""Write a GitHub Actions should-run output from dorny/paths-filter results."""

from __future__ import annotations

import json
import os
import re
import sys
from collections.abc import Collection, Mapping
from pathlib import Path

_OUTPUT_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")


def should_run(
    event_name: str,
    filter_outputs: Mapping[str, object],
    filter_keys: list[str],
    force_run_events: Collection[str] = (),
) -> bool:
    """Decide whether the gated job runs for this event.

    ``force_run_events`` names events that bypass the path filter. A path filter
    encodes the claim that the verdict cannot change unless those paths change.
    That holds for a check whose input is the diff. It fails for a whole-tree
    check on the mainline: when the filter misses, the gated job is skipped and
    its companion skip job reports success in its place, so the workflow goes
    green without measuring anything. Nothing carries over from the previous
    run. A fresh green tick is manufactured, and it asserts only that the diff
    was uninteresting.

    Measured 2026-08-02: ``main`` at ``a72ee868c`` was 201 bytes over the
    always-on instruction ceiling while the Instruction Budget workflow reported
    success, because ``Validate budget`` was skipped and ``Skip budget (no
    changes)`` passed in its place. The commit that caused the breach had its own
    run cancelled in a merge burst, so no run ever measured the breach.

    A whole-tree check should drop its filter instead of listing ``push`` here.
    Forcing one event measures the mainline and leaves every pull request
    unmeasured, so two of them each green against their own base still merge to
    a breaching union. ``instruction-budget.yml`` took the filter out for that
    reason and no workflow lists ``push`` today. Leave this empty for a
    diff-scoped check, where re-running on an unrelated push buys nothing.

    ``merge_group`` is different. It represents the synthetic commit that the
    queue will merge, so checks that validate repository content must force a
    real run against that ref when the paths action has no pull request context.
    """
    if event_name == "workflow_dispatch" or event_name in force_run_events:
        return True
    return any(filter_outputs.get(key) == "true" for key in filter_keys)


def parse_filter_keys(raw_filter_keys: str) -> list[str]:
    return [key.strip() for key in raw_filter_keys.split(",") if key.strip()]


def parse_force_run_events(raw_force_run_events: str) -> frozenset[str]:
    return frozenset(
        event.strip() for event in raw_force_run_events.split(",") if event.strip()
    )


def parse_filter_outputs(raw_filter_outputs: str) -> dict[str, object]:
    if not raw_filter_outputs:
        return {}
    parsed = json.loads(raw_filter_outputs)
    if parsed is None:
        return {}
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
        force_run_events = parse_force_run_events(os.environ.get("FORCE_RUN_EVENTS", ""))
        value = should_run(event_name, filter_outputs, filter_keys, force_run_events)
        write_output(output_path, output_name, value)
    except (KeyError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
