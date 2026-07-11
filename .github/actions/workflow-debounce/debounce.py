#!/usr/bin/env python3
"""Debounce delay for a workflow run (ADR-006 extraction).

Extracted from the inline run block in `action.yml` so the composite action
carries no logic in YAML (ADR-006). Reads inputs from the environment, sleeps
to create a cancellation window that lets GitHub Actions concurrency control
terminate duplicate runs, computes the actual duration, then writes the step
outputs and a job summary.

The formatting helpers are pure and unit-tested; the sleep and the file
appends are the only side effects, and both are injectable for tests.

Inputs (environment):
    DELAY_SECONDS       delay to sleep, integer seconds (default "10")
    WORKFLOW_NAME       workflow name, for logging and the summary
    CONCURRENCY_GROUP   concurrency group identifier, for the summary
    GITHUB_OUTPUT       step-output file (GitHub sets this); optional
    GITHUB_STEP_SUMMARY job-summary file (GitHub sets this); optional

Exit codes: 0 on success, 1 on a non-integer DELAY_SECONDS.
"""

from __future__ import annotations

import os
import sys
import time
from collections.abc import Callable, Mapping
from datetime import UTC, datetime


def iso_utc(epoch_seconds: float) -> str:
    """Format an epoch timestamp as an ISO 8601 UTC string (second precision)."""
    return datetime.fromtimestamp(epoch_seconds, tz=UTC).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def build_output_lines(start_iso: str, end_iso: str, duration: int) -> list[str]:
    """Return the GITHUB_OUTPUT lines for the debounce step."""
    return [f"start={start_iso}", f"end={end_iso}", f"duration={duration}"]


def build_summary(
    workflow_name: str,
    concurrency_group: str,
    delay_configured: str,
    duration: int,
    start_iso: str,
    end_iso: str,
) -> str:
    """Return the GITHUB_STEP_SUMMARY markdown for the debounce step."""
    return (
        "## Workflow Debouncing Applied\n\n"
        "| Metric | Value |\n"
        "|--------|-------|\n"
        f"| **Workflow** | {workflow_name} |\n"
        f"| **Concurrency Group** | {concurrency_group} |\n"
        f"| **Delay Configured** | {delay_configured}s |\n"
        f"| **Actual Duration** | {duration}s |\n"
        f"| **Start Time** | {start_iso} |\n"
        f"| **End Time** | {end_iso} |\n\n"
        "**Purpose**: Provide cancellation window for GitHub Actions to "
        "terminate duplicate runs\n\n"
        "**Impact**: This delay helps reduce race conditions where multiple "
        "workflow runs start before cancellation takes effect.\n"
    )


def _append(path: str | None, text: str) -> None:
    """Append text to a file if the path is set (GitHub output/summary files)."""
    if not path:
        return
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(text)


def run(
    env: Mapping[str, str],
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.time,
) -> int:
    """Execute the debounce. Returns a process exit code."""
    delay_configured = env.get("DELAY_SECONDS", "10")
    workflow_name = env.get("WORKFLOW_NAME", "")
    concurrency_group = env.get("CONCURRENCY_GROUP", "")

    try:
        delay = int(delay_configured)
    except ValueError:
        print(
            f"error: DELAY_SECONDS must be an integer, got {delay_configured!r}",
            file=sys.stderr,
        )
        return 1

    start = clock()
    start_iso = iso_utc(start)
    print("=== Workflow Debouncing ===")
    print(f"Workflow: {workflow_name}")
    print(f"Concurrency Group: {concurrency_group}")
    print(f"Sleeping for {delay} seconds...")

    sleep(delay)

    end = clock()
    end_iso = iso_utc(end)
    duration = int(round(end - start))

    _append(
        env.get("GITHUB_OUTPUT"),
        "\n".join(build_output_lines(start_iso, end_iso, duration)) + "\n",
    )
    _append(
        env.get("GITHUB_STEP_SUMMARY"),
        build_summary(
            workflow_name,
            concurrency_group,
            delay_configured,
            duration,
            start_iso,
            end_iso,
        ),
    )

    print("=== Debouncing Complete ===")
    print(f"End Time: {end_iso}")
    print(f"Actual Duration: {duration} seconds")
    return 0


def main() -> int:
    return run(os.environ)


if __name__ == "__main__":
    raise SystemExit(main())
