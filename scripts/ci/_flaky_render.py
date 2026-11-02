"""Render a flaky test classification for the GitHub job step summary.

The summary is a markdown table, one row per first-run failure, appended to
the file ``GITHUB_STEP_SUMMARY`` names. Outside Actions, where that variable
is unset, the block goes to stdout instead.
"""

from __future__ import annotations

import os
import sys

from scripts.ci._flaky_classify import Outcome
from scripts.ci._flaky_inputs import JunitCounts


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("`", "'").replace("\n", " ")


def render_summary(partition: str, outcome: Outcome, cache_note: str) -> str:
    """The markdown block for the job step summary."""
    lines = [f"## Flaky test report ({_cell(partition)})", "", outcome.headline, ""]
    if cache_note:
        lines += [f"> [!NOTE]\n> {cache_note}", ""]
    if outcome.rows:
        lines += ["| Test | First run | Rerun | Verdict |", "| --- | --- | --- | --- |"]
        lines += [
            f"| `{_cell(nodeid)}` | failed | {rerun} | {verdict} |"
            for nodeid, rerun, verdict in outcome.rows
        ]
        lines.append("")
    if outcome.flaky:
        lines += [
            "Flaky tests failed once and passed on rerun. The leg is still red: fix",
            "the flaky test; a rerun never turns a leg green.",
            "",
        ]
    return "\n".join(lines) + "\n"


def cache_note(first: JunitCounts, nodeids: list[str]) -> str:
    """A warning when the cache lists more failures than the JUnit report."""
    if nodeids and len(nodeids) > first.failed:
        return (
            f"The pytest cache lists {len(nodeids)} failed tests but the JUnit report "
            f"records {first.failed}; some cache entries may predate this run."
        )
    return ""


def emit_summary(content: str) -> bool:
    """Append *content* to the step summary; False when the file cannot be written."""
    summary_file = os.environ.get("GITHUB_STEP_SUMMARY", "")
    if not summary_file:
        print(content, end="")
        return True
    try:
        with open(summary_file, "a", encoding="utf-8") as handle:
            handle.write(content)
    except OSError as exc:
        print(f"::error::could not write the step summary {summary_file}: {exc}", file=sys.stderr)
        return False
    return True
