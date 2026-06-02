#!/usr/bin/env python3
"""Aggregate per-issue AI-triage results into one human-review summary.

Reads the JSON documents written by ``backlog_triage_result.py`` (one per open
issue, collected as workflow artifacts) and renders a single markdown report.
Part of the backlog-triage workflow (issue #2260, ClawSweeper Phase 2).
Read-only: produces a report for human review. Suggests labels, complexity,
dependencies, scope, and evidence gaps. It applies nothing and closes nothing.

Exit codes follow ADR-035:
    0 - Success (an empty or missing results dir yields an empty-state report)
    1 - Logic error (downloaded result count does not match discovery count)
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True, slots=True)
class DependencyDetection:
    blocked_by: tuple[int, ...] = ()
    blocks: tuple[int, ...] = ()
    related: tuple[int, ...] = ()
    notes: str = ""

    @classmethod
    def from_raw(cls, raw: object) -> DependencyDetection:
        if not isinstance(raw, dict):
            return cls()
        return cls(
            blocked_by=_number_tuple(raw.get("blocked_by")),
            blocks=_number_tuple(raw.get("blocks")),
            related=_number_tuple(raw.get("related")),
            notes=str(raw.get("notes") or ""),
        )


@dataclass(frozen=True, slots=True)
class ScopeAssessment:
    status: str = "unknown"
    needs_decomposition: bool = False
    can_batch: bool = False
    notes: str = ""

    @classmethod
    def from_raw(cls, raw: object) -> ScopeAssessment:
        if not isinstance(raw, dict):
            return cls()
        return cls(
            status=str(raw.get("status") or "unknown"),
            needs_decomposition=raw.get("needs_decomposition") is True,
            can_batch=raw.get("can_batch") is True,
            notes=str(raw.get("notes") or ""),
        )


@dataclass(frozen=True, slots=True)
class EvidenceCheck:
    has_repro_steps: bool | None = None
    has_acceptance_criteria: bool | None = None
    has_enough_context: bool | None = None
    missing: tuple[str, ...] = ()

    @classmethod
    def from_raw(cls, raw: object) -> EvidenceCheck:
        if not isinstance(raw, dict):
            return cls()
        return cls(
            has_repro_steps=_bool_or_none(raw.get("has_repro_steps")),
            has_acceptance_criteria=_bool_or_none(raw.get("has_acceptance_criteria")),
            has_enough_context=_bool_or_none(raw.get("has_enough_context")),
            missing=_string_tuple(raw.get("missing")),
        )


@dataclass(frozen=True, slots=True)
class TriageResult:
    """One issue's triage result, mapped from an untrusted JSON document.

    The JSON written by ``backlog_triage_result.py`` is read back from a
    workflow artifact, so the shape is untrusted on the way in. ``from_raw``
    is the only place that knows the wire shape; the rest of this module works
    with typed fields.
    """

    number: int
    title: str
    verdict: str
    labels: tuple[str, ...]
    complexity_classification: str = "unknown"
    area_routing: tuple[str, ...] = ()
    dependency_detection: DependencyDetection = field(default_factory=DependencyDetection)
    scope_assessment: ScopeAssessment = field(default_factory=ScopeAssessment)
    evidence_check: EvidenceCheck = field(default_factory=EvidenceCheck)
    findings: str = ""

    @classmethod
    def from_raw(cls, raw: object) -> TriageResult | None:
        """Map a parsed JSON value to a result, or None if it is not one.

        A missing or non-integer ``number`` means the file is not a triage
        result; return None so the caller can skip it.
        """

        if not isinstance(raw, dict) or "number" not in raw:
            return None
        raw_number = raw["number"]
        if isinstance(raw_number, bool):
            return None
        try:
            number = int(raw_number)
        except (TypeError, ValueError):
            return None
        if number <= 0:
            return None
        labels_raw = raw.get("labels") or []
        labels = tuple(str(item) for item in labels_raw) if isinstance(labels_raw, list) else ()
        area_routing = _string_tuple(raw.get("area_routing"))
        verdict = str(raw.get("verdict") or "UNKNOWN")
        return cls(
            number=number,
            title=str(raw.get("title") or ""),
            verdict=verdict,
            labels=labels,
            complexity_classification=str(raw.get("complexity_classification") or "unknown"),
            area_routing=area_routing,
            dependency_detection=DependencyDetection.from_raw(raw.get("dependency_detection")),
            scope_assessment=ScopeAssessment.from_raw(raw.get("scope_assessment")),
            evidence_check=EvidenceCheck.from_raw(raw.get("evidence_check")),
            findings=str(raw.get("findings") or ""),
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
        "AI classification for the open-issue backlog (issue #2260, part of ",
        "epic #1799). Read-only: review and apply suggestions manually. No ",
        "labels were applied and no issues were closed.",
        "",
    ]
    if not results:
        lines.append("No issues were triaged in this run.")
        return "\n".join(lines) + "\n"

    lines.append(f"Issues triaged: {len(results)}")
    lines.append("")
    lines.append(
        "| Issue | Title | Verdict | Complexity | Area routing | Dependencies | "
        "Scope | Evidence | Labels | Findings |"
    )
    lines.append(
        "|-------|-------|---------|------------|--------------|--------------|-------|----------|--------|----------|"
    )
    for result in results:
        title = _sanitize_cell(result.title)
        verdict = _sanitize_cell(result.verdict)
        complexity = _sanitize_cell(result.complexity_classification) or "unknown"
        area = _sanitize_cell(", ".join(result.area_routing)) or "-"
        dependencies = _sanitize_cell(_format_dependencies(result.dependency_detection)) or "-"
        scope = _sanitize_cell(_format_scope(result.scope_assessment)) or "-"
        evidence = _sanitize_cell(_format_evidence(result.evidence_check)) or "-"
        labels_text = _sanitize_cell(", ".join(result.labels)) or "-"
        findings = _sanitize_cell(result.findings) or "-"
        lines.append(
            f"| #{result.number} | {title} | {verdict} | {complexity} | {area} | "
            f"{dependencies} | {scope} | {evidence} | {labels_text} | {findings} |"
        )
    return "\n".join(lines) + "\n"


def _format_dependencies(value: DependencyDetection) -> str:
    parts: list[str] = []
    if value.blocked_by:
        parts.append("blocked by " + ", ".join(f"#{n}" for n in value.blocked_by))
    if value.blocks:
        parts.append("blocks " + ", ".join(f"#{n}" for n in value.blocks))
    if value.related:
        parts.append("related " + ", ".join(f"#{n}" for n in value.related))
    if value.notes:
        parts.append(value.notes)
    return "; ".join(parts)


def _format_scope(value: ScopeAssessment) -> str:
    parts = [value.status]
    flags: list[str] = []
    if value.needs_decomposition:
        flags.append("needs decomposition")
    if value.can_batch:
        flags.append("can batch")
    if flags:
        parts.append("(" + ", ".join(flags) + ")")
    if value.notes:
        parts.append(value.notes)
    return " ".join(part for part in parts if part)


def _format_evidence(value: EvidenceCheck) -> str:
    parts = [
        f"repro={_format_bool(value.has_repro_steps)}",
        f"ac={_format_bool(value.has_acceptance_criteria)}",
        f"context={_format_bool(value.has_enough_context)}",
    ]
    if value.missing:
        parts.append("missing " + ", ".join(value.missing))
    return "; ".join(parts)


def _format_bool(value: bool | None) -> str:
    if value is True:
        return "yes"
    if value is False:
        return "no"
    return "unknown"


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


def _number_tuple(value: object) -> tuple[int, ...]:
    if not isinstance(value, list):
        return ()
    numbers: list[int] = []
    for item in value:
        if isinstance(item, bool):
            continue
        try:
            number = int(item)
        except (TypeError, ValueError):
            continue
        if number > 0:
            numbers.append(number)
    return tuple(numbers)


def _string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(item).strip() for item in value if str(item).strip())


def _bool_or_none(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    return None


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
    parser.add_argument(
        "--expected-count",
        type=int,
        default=-1,
        help="Expected number of result JSON files. Negative disables count validation.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    results_dir = Path(args.results_dir)
    if not results_dir.is_dir():
        # No artifacts can mean every matrix job failed; emit an empty-state
        # report so the summarize job still produces a reviewable artifact.
        results = []
    else:
        results = load_results(results_dir)
    summary = render_summary(results)
    Path(args.output).write_text(summary, encoding="utf-8")
    if args.github_step_summary:
        with Path(args.github_step_summary).open("a", encoding="utf-8") as handle:
            handle.write(summary)
    print(f"Wrote backlog triage summary to {args.output}")
    if args.expected_count >= 0 and len(results) != args.expected_count:
        print(
            f"Downloaded {len(results)} triage results, expected {args.expected_count}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
