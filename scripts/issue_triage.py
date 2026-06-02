#!/usr/bin/env python3
"""Phase 1 mechanical issue triage scanner.

Implements the read-only mechanical triage layer described in issue #1799
(ClawSweeper pattern for ai-agents). Scans the open-issue backlog and
classifies issues against deterministic, scriptable rules:

- Stale: issues with no activity in N days.
- Missing priority label: issues without a ``priority:Px`` label.
- Missing area label: issues without any ``area-*`` label.

The script is read-only by design: it emits a JSON or human-readable report
and never mutates GitHub state.

The ``--ai`` flag drives Phase 2 (LLM triage). It emits a GitHub Actions
matrix of open issues that a scheduled workflow (.github/workflows/
backlog-triage.yml) fans out to .github/actions/ai-review, one invocation
per issue, for structured complexity, area routing, dependency, scope, and
evidence classification. The model call lives in the workflow; this script
only produces the work list. Phase 3 (recommendation execution / auto-close)
remains out of scope and read-only.

Exit codes follow ADR-035:
    0 - Success: scan completed (findings may exist)
    2 - Config error (bad input, environment, or upstream API failure)
    3 - External error (gh CLI failure beyond config issues)

Related: Issue #1799, ADR-042 (Python-first scripts)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

DEFAULT_STALE_DAYS = 60
PRIORITY_LABEL_PREFIX = "priority:"
AREA_LABEL_PREFIX = "area-"
ISO_TIMESTAMP_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)


@dataclass(frozen=True)
class IssueRecord:
    """Subset of GitHub issue fields the triage rules read."""

    number: int
    title: str
    updated_at: str
    labels: tuple[str, ...]


@dataclass
class IssueFinding:
    """A single triage finding for one issue."""

    number: int
    title: str
    reasons: list[str] = field(default_factory=list)


@dataclass
class TriageReport:
    """Aggregate triage report across all scanned issues."""

    timestamp: str
    repo: str
    stale_days: int
    issues_scanned: int = 0
    stale: list[IssueFinding] = field(default_factory=list)
    missing_priority: list[IssueFinding] = field(default_factory=list)
    missing_area: list[IssueFinding] = field(default_factory=list)

    @property
    def has_findings(self) -> bool:
        """True when any rule produced at least one finding."""
        return bool(self.stale or self.missing_priority or self.missing_area)


def parse_iso_timestamp(value: str) -> datetime:
    """Parse an ISO-8601 UTC timestamp from the GitHub API.

    Accepts both the ``Z`` suffix and explicit offsets. Raises
    ``ValueError`` if the value does not match the expected shape; the
    caller decides whether to surface the error or skip the record.
    """

    if not ISO_TIMESTAMP_PATTERN.match(value):
        raise ValueError(f"Invalid ISO-8601 timestamp: {value!r}")
    normalized = value.replace("Z", "+00:00")
    return datetime.fromisoformat(normalized)


def parse_issue_record(raw: dict) -> IssueRecord:
    """Build an ``IssueRecord`` from the gh JSON shape.

    Raises ``ValueError`` if required fields are missing.
    """

    try:
        number = int(raw["number"])
        title = str(raw["title"])
        updated_at = str(raw["updatedAt"])
    except (KeyError, TypeError, ValueError) as err:
        raise ValueError(f"Malformed issue record: {raw!r}") from err

    labels_raw = raw.get("labels") or []
    labels: list[str] = []
    for entry in labels_raw:
        if isinstance(entry, dict) and "name" in entry:
            labels.append(str(entry["name"]))
        elif isinstance(entry, str):
            labels.append(entry)
    return IssueRecord(
        number=number,
        title=title,
        updated_at=updated_at,
        labels=tuple(labels),
    )


def is_stale(issue: IssueRecord, *, now: datetime, stale_days: int) -> bool:
    """Return True when the issue has not been updated within ``stale_days``."""

    if stale_days <= 0:
        return False
    try:
        updated = parse_iso_timestamp(issue.updated_at)
    except ValueError:
        return False
    return now - updated >= timedelta(days=stale_days)


def has_priority_label(issue: IssueRecord) -> bool:
    """True when any label starts with ``priority:``."""

    return any(label.startswith(PRIORITY_LABEL_PREFIX) for label in issue.labels)


def has_area_label(issue: IssueRecord) -> bool:
    """True when any label starts with ``area-``."""

    return any(label.startswith(AREA_LABEL_PREFIX) for label in issue.labels)


def classify(
    issues: list[IssueRecord],
    *,
    now: datetime,
    stale_days: int,
) -> tuple[list[IssueFinding], list[IssueFinding], list[IssueFinding]]:
    """Apply the three Phase 1 rules to ``issues``.

    Returns a tuple ``(stale, missing_priority, missing_area)``.
    """

    stale: list[IssueFinding] = []
    missing_priority: list[IssueFinding] = []
    missing_area: list[IssueFinding] = []

    for issue in issues:
        if is_stale(issue, now=now, stale_days=stale_days):
            stale.append(
                IssueFinding(
                    number=issue.number,
                    title=issue.title,
                    reasons=[f"no activity in {stale_days}+ days"],
                )
            )
        if not has_priority_label(issue):
            missing_priority.append(
                IssueFinding(
                    number=issue.number,
                    title=issue.title,
                    reasons=["missing priority:* label"],
                )
            )
        if not has_area_label(issue):
            missing_area.append(
                IssueFinding(
                    number=issue.number,
                    title=issue.title,
                    reasons=["missing area-* label"],
                )
            )
    return stale, missing_priority, missing_area


def build_report(
    issues: list[IssueRecord],
    *,
    repo: str,
    now: datetime,
    stale_days: int,
) -> TriageReport:
    """Assemble a ``TriageReport`` from raw issue records."""

    stale, missing_priority, missing_area = classify(
        issues, now=now, stale_days=stale_days
    )
    return TriageReport(
        timestamp=now.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        repo=repo,
        stale_days=stale_days,
        issues_scanned=len(issues),
        stale=stale,
        missing_priority=missing_priority,
        missing_area=missing_area,
    )


def fetch_open_issues(owner: str, repo: str, *, limit: int) -> list[dict]:
    """Fetch open issues via the gh CLI.

    Returns the parsed JSON array. Raises ``RuntimeError`` on failure so
    ``main`` can map to an exit code.
    """

    if not 1 <= limit <= 1000:
        raise ValueError("limit must be between 1 and 1000")

    cmd = [
        "gh", "issue", "list",
        "--repo", f"{owner}/{repo}",
        "--state", "open",
        "--limit", str(limit),
        "--json", "number,title,updatedAt,labels",
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30, check=True,
        )
    except subprocess.CalledProcessError as err:
        stderr = (err.stderr or "").strip() or (err.stdout or "").strip()
        raise RuntimeError(f"gh issue list failed: {stderr}") from err
    except subprocess.TimeoutExpired as err:
        raise RuntimeError(f"gh issue list timed out after {err.timeout}s") from err
    except OSError as err:
        raise RuntimeError(f"gh issue list failed to execute: {err}") from err
    try:
        data = json.loads(result.stdout or "[]")
    except (json.JSONDecodeError, ValueError, TypeError) as err:
        raise RuntimeError(f"Failed to parse gh output: {err}") from err
    if not isinstance(data, list):
        raise RuntimeError(f"gh issue list returned non-list payload: {type(data).__name__}")
    return data


def split_github_repository(value: str) -> tuple[str, str]:
    """Return owner and repo from a GitHub repository slug, or blank values."""

    parts = value.split("/")
    if len(parts) != 2 or not parts[0] or not parts[1]:
        return "", ""
    return parts[0], parts[1]


def build_ai_matrix(issues: list[IssueRecord]) -> dict[str, object]:
    """Build the Phase 2 AI-triage discovery payload.

    The ``--ai`` flag drives Phase 2 of the ClawSweeper pattern (issue #1799):
    a scheduled workflow fans this matrix out to ``.github/actions/ai-review``,
    one invocation per open issue, for complexity classification and area
    routing. The mechanical scan stays Python-side; YAML only fans out
    (ADR-006). This function does not call the model; it produces the work
    list the workflow consumes.

    Returns a dict with ``include`` (the matrix rows) and ``count`` so the
    caller can gate the matrix job on whether any issues exist.
    """

    include = [{"number": issue.number, "title": issue.title} for issue in issues]
    return {"include": include, "count": len(include)}


def write_ai_github_outputs(matrix: dict[str, object], output_path: str) -> None:
    """Write matrix metadata to GitHub Actions output format."""

    include = matrix.get("include")
    count = int(matrix.get("count") or 0)
    github_matrix = {"include": include if isinstance(include, list) else []}
    with Path(output_path).open("a", encoding="utf-8") as handle:
        handle.write(f"matrix={json.dumps(github_matrix)}\n")
        handle.write(f"has-issues={str(count > 0).lower()}\n")
        handle.write(f"count={count}\n")


def format_human(report: TriageReport) -> str:
    """Render a short human-readable summary of the report."""

    lines: list[str] = [
        f"Triage report for {report.repo} ({report.timestamp})",
        f"Issues scanned: {report.issues_scanned} (stale threshold: {report.stale_days} days)",
        "",
        f"Stale ({len(report.stale)}):",
    ]
    lines.extend(_render_findings(report.stale))
    lines.append(f"Missing priority label ({len(report.missing_priority)}):")
    lines.extend(_render_findings(report.missing_priority))
    lines.append(f"Missing area label ({len(report.missing_area)}):")
    lines.extend(_render_findings(report.missing_area))
    return "\n".join(lines)


def _render_findings(findings: list[IssueFinding]) -> list[str]:
    if not findings:
        return ["  (none)"]
    return [f"  #{f.number}: {f.title}" for f in findings]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments."""

    parser = argparse.ArgumentParser(
        description="Phase 1 mechanical issue triage scanner (ClawSweeper pattern).",
    )
    parser.add_argument("--owner", default=os.environ.get("GH_REPO_OWNER", ""))
    parser.add_argument("--repo", default=os.environ.get("GH_REPO_NAME", ""))
    parser.add_argument(
        "--stale-days", type=int, default=DEFAULT_STALE_DAYS,
        help=f"Days of inactivity to flag as stale (default: {DEFAULT_STALE_DAYS}).",
    )
    parser.add_argument(
        "--limit", type=int, default=300,
        help="Max issues to fetch from the API (1-1000, default: 300).",
    )
    parser.add_argument(
        "--format", choices=["json", "human"], default="human",
        help="Output format (default: human).",
    )
    parser.add_argument(
        "--ai", action="store_true",
        help="Emit a GitHub Actions matrix of open issues for Phase 2 AI triage "
             "(complexity + area routing via .github/actions/ai-review). "
             "Overrides --format; prints a JSON matrix payload.",
    )
    parser.add_argument(
        "--input", default="",
        help="Path to a JSON file with prefetched issues (skips gh call). "
             "Useful for testing and air-gapped runs.",
    )
    parser.add_argument(
        "--github-output",
        default="",
        help="Optional GitHub output file for matrix, has-issues, and count values.",
    )
    return parser.parse_args(argv)


def load_issues_from_input(path: str) -> list[dict]:
    """Read prefetched issues from a JSON file."""

    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, list):
        raise ValueError(f"--input file must contain a JSON array; got {type(data).__name__}")
    return data


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if args.stale_days < 0:
        print("--stale-days must be >= 0", file=sys.stderr)
        return 2

    if args.input:
        try:
            raw_issues = load_issues_from_input(args.input)
        except (OSError, ValueError, json.JSONDecodeError) as err:
            print(f"Failed to read --input file: {err}", file=sys.stderr)
            return 2
        repo_label = args.input
    else:
        owner = args.owner
        repo = args.repo
        if args.ai and (not owner or not repo):
            owner, repo = split_github_repository(os.environ.get("GITHUB_REPOSITORY", ""))
        if not owner or not repo:
            print("--owner and --repo are required when --input is not set", file=sys.stderr)
            return 2
        try:
            raw_issues = fetch_open_issues(owner, repo, limit=args.limit)
        except ValueError as err:
            print(str(err), file=sys.stderr)
            return 2
        except RuntimeError as err:
            print(str(err), file=sys.stderr)
            return 3
        repo_label = f"{owner}/{repo}"

    issues: list[IssueRecord] = []
    for raw in raw_issues:
        try:
            issues.append(parse_issue_record(raw))
        except ValueError as err:
            print(f"warn: skipping malformed issue: {err}", file=sys.stderr)

    if args.ai:
        matrix = build_ai_matrix(issues)
        if args.github_output:
            write_ai_github_outputs(matrix, args.github_output)
        print(json.dumps(matrix))
        return 0

    report = build_report(
        issues,
        repo=repo_label,
        now=datetime.now(UTC),
        stale_days=args.stale_days,
    )

    if args.format == "json":
        print(json.dumps(asdict(report), indent=2))
    else:
        print(format_human(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
