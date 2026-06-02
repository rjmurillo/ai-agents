#!/usr/bin/env python3
"""Aggregate per-issue AI-triage results into one human-review summary.

Reads the JSON documents written by ``backlog_triage_result.py`` (one per open
issue, collected as workflow artifacts) and renders a single markdown report.
Part of the backlog-triage workflow (issue #1799, ClawSweeper pattern).
Read-only: produces a report for human review. Suggests labels and complexity;
applies nothing and closes nothing.

Exit codes follow ADR-035:
    0 - Success (an empty or missing results dir yields an empty-state report)
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class TriageResult:
    """One issue's triage result, mapped from an untrusted JSON document.

    The JSON written by ``backlog_triage_result.py`` is read back from a
    workflow artifact, so the shape is untrusted on the way in. ``from_raw``
    is the only place that knows the wire shape; the rest of this module works
    with the typed fields.
    """

    number: int
    title: str
    verdict: str
    labels: tuple[str, ...]

    @classmethod
    def from_raw(cls, raw: object) -> TriageResult | None:
        """Map a parsed JSON value to a result, or None if it is not one.

        A missing or non-integer ``number`` means the file is not a triage
        result; return None so the caller can skip it.
        """

        if not isinstance(raw, dict) or "number" not in raw:
            return None
        try:
            number = int(raw["number"])
        except (TypeError, ValueError):
            return None
        labels_raw = raw.get("labels") or []
        labels = tuple(str(item) for item in labels_raw) if isinstance(labels_raw, list) else ()
        verdict = str(raw.get("verdict") or "UNKNOWN")
        return cls(
            number=number,
            title=str(raw.get("title") or ""),
            verdict=verdict,
            labels=labels,
        )


def load_results(results_dir: Path) -> list[TriageResult]:
    """Load every ``*.json`` result file under ``results_dir``.

    Malformed files are skipped with a stderr warning rather than aborting the
    whole summary. Results are sorted by issue number for a stable report.
    """

    results: list[TriageResult] = []
    for path in sorted(results_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, ValueError) as err:
            print(f"warn: skipping unreadable result {path}: {err}", file=sys.stderr)
            continue
        result = TriageResult.from_raw(data)
        if result is None:
            print(f"warn: skipping malformed result {path}", file=sys.stderr)
            continue
        results.append(result)
    results.sort(key=lambda r: r.number)
    return results


def render_summary(results: list[TriageResult]) -> str:
    """Render the markdown human-review summary."""

    lines: list[str] = [
        "## Backlog Triage Summary",
        "",
        "AI complexity classification and area routing for the open-issue "
        "backlog (issue #1799). Read-only: review and apply suggestions "
        "manually. No labels were applied and no issues were closed.",
        "",
    ]
    if not results:
        lines.append("No issues were triaged in this run.")
        return "\n".join(lines) + "\n"

    lines.append(f"Issues triaged: {len(results)}")
    lines.append("")
    lines.append("| Issue | Title | Verdict | Suggested labels |")
    lines.append("|-------|-------|---------|------------------|")
    for result in results:
        title = _sanitize_cell(result.title)
        verdict = _sanitize_cell(result.verdict)
        labels_text = _sanitize_cell(", ".join(result.labels)) or "-"
        lines.append(f"| #{result.number} | {title} | {verdict} | {labels_text} |")
    return "\n".join(lines) + "\n"


def _sanitize_cell(text: str) -> str:
    """Make free text safe for a single markdown table cell.

    Issue titles are untrusted. Pipes would break the column layout and
    newlines would break the row, so collapse both. This is presentation
    hardening, not a security boundary; the values never reach a shell.
    """

    return (
        text.replace("\\", "\\\\")
        .replace("|", "\\|")
        .replace("\n", " ")
        .replace("\r", " ")
        .strip()
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Aggregate AI-triage results into a human-review summary.",
    )
    parser.add_argument(
        "--results-dir", required=True,
        help="Directory holding per-issue triage result JSON files.",
    )
    parser.add_argument(
        "--output", required=True,
        help="Path to write the markdown summary.",
    )
    parser.add_argument(
        "--github-step-summary",
        default="",
        help="Optional GitHub step summary file to append the markdown report to.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    results_dir = Path(args.results_dir)
    if not results_dir.is_dir():
        # No artifacts can mean every matrix job failed; emit an empty-state
        # report so the summarize job still produces a reviewable artifact.
        summary = render_summary([])
    else:
        summary = render_summary(load_results(results_dir))
    Path(args.output).write_text(summary, encoding="utf-8")
    if args.github_step_summary:
        with Path(args.github_step_summary).open("a", encoding="utf-8") as handle:
            handle.write(summary)
    print(f"Wrote backlog triage summary to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
