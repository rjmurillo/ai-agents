#!/usr/bin/env python3
"""Phase 1 mechanical issue triage scanner.

Implements the read-only mechanical triage layer described in issue #1799
(ClawSweeper pattern for ai-agents). Scans the open-issue backlog and
classifies issues against deterministic, scriptable rules (no LLM):

- Stale: issues with no activity in N days.
- Missing priority label: issues without a ``priority:Px`` label.
- Missing area label: issues without any ``area-*`` label.
- Missing agent label: issues without any ``agent-*`` label.
- Duplicate candidates: issue pairs whose titles are highly similar.
- State inconsistency: a ``Doing`` issue with no assignee, or a ``Planning``
  issue with no description body.
- Linked PR status: issues whose linked PRs are merged or closed (the state
  label can advance).

The script is read-only by design: it emits a JSON or human-readable report
and never mutates GitHub state.

Incremental scan: with ``--state-file`` the scanner persists the run
timestamp and, on the next run, restricts the GitHub query to issues updated
since the last run (``updated:>TIMESTAMP``). ``--full-scan`` ignores the
state file. ``--since`` overrides both. This keeps repeated runs cheap and
lets multiple scanners process disjoint issue sets in parallel.

The ``--ai`` flag drives Phase 2 (LLM triage). It emits a GitHub Actions
matrix of open issues that a scheduled workflow (.github/workflows/
backlog-triage.yml) fans out to .github/actions/ai-review, one invocation
per issue, for structured complexity, area routing, dependency, scope, and
evidence classification. The model call lives in the workflow; this script
only produces the work list. Phase 3 (recommendation execution / auto-close)
remains out of scope and read-only.

Exit codes follow ADR-035:
    0 - Success: scan completed (findings may exist)
    2 - Config error (bad input, environment, or invalid arguments)
    3 - External error (gh CLI failure)

Related: Issue #1799, Issue #2259, ADR-042 (Python-first scripts)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

DEFAULT_STALE_DAYS = 60
DEFAULT_DUP_THRESHOLD = 0.7
PRIORITY_LABEL_PREFIX = "priority:"
AREA_LABEL_PREFIX = "area-"
AGENT_LABEL_PREFIX = "agent-"

# State labels (GitHub labels, not GitHub Projects fields). Confirmed from live
# issue data: issues carry "To Do" / "Planning" / "Doing" labels directly.
STATE_DOING = "Doing"
STATE_PLANNING = "Planning"

# PR states that mean a linked PR has concluded and the issue's state label can
# advance. "MERGED" and "CLOSED" both qualify; "OPEN" does not.
ADVANCING_PR_STATES = frozenset({"MERGED", "CLOSED"})

# Conventional-commit prefix stripped before title-similarity comparison so
# "fix(scope): foo" and "feat(scope): foo" do not collide purely on type/scope.
_CONVENTIONAL_PREFIX = re.compile(r"^\s*[a-z]+(?:\([^)]*\))?!?:\s*", re.IGNORECASE)
_NON_WORD = re.compile(r"[^a-z0-9]+")
# Tokens shorter than this are dropped from the title-similarity comparison.
_MIN_TOKEN_LEN = 3

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
    body: str = ""
    assignees: tuple[str, ...] = ()
    # Linked pull requests as (pr_number, state) pairs. Populated only when
    # linked-PR detection runs (opt-in, per-issue) or supplied via --input.
    linked_prs: tuple[tuple[int, str], ...] = ()


@dataclass
class IssueFinding:
    """A single triage finding for one issue."""

    number: int
    title: str
    reasons: list[str] = field(default_factory=list)


@dataclass
class DuplicateFinding:
    """A candidate duplicate pair with its similarity score."""

    number: int
    title: str
    duplicate_of: int
    duplicate_of_title: str
    score: float


@dataclass
class TriageReport:
    """Aggregate triage report across all scanned issues."""

    timestamp: str
    repo: str
    stale_days: int
    issues_scanned: int = 0
    scanned_since: str | None = None
    stale: list[IssueFinding] = field(default_factory=list)
    missing_priority: list[IssueFinding] = field(default_factory=list)
    missing_area: list[IssueFinding] = field(default_factory=list)
    missing_agent: list[IssueFinding] = field(default_factory=list)
    state_inconsistent: list[IssueFinding] = field(default_factory=list)
    linked_pr_advance: list[IssueFinding] = field(default_factory=list)
    duplicates: list[DuplicateFinding] = field(default_factory=list)

    @property
    def has_findings(self) -> bool:
        """True when any rule produced at least one finding."""
        return bool(
            self.stale
            or self.missing_priority
            or self.missing_area
            or self.missing_agent
            or self.state_inconsistent
            or self.linked_pr_advance
            or self.duplicates
        )


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


def _parse_assignees(raw: object) -> tuple[str, ...]:
    """Extract assignee logins from the gh JSON shape."""

    if not isinstance(raw, list):
        return ()
    logins: list[str] = []
    for entry in raw:
        if isinstance(entry, dict) and entry.get("login"):
            logins.append(str(entry["login"]))
        elif isinstance(entry, str) and entry:
            logins.append(entry)
    return tuple(logins)


def _parse_linked_prs(raw: object) -> tuple[tuple[int, str], ...]:
    """Extract (pr_number, state) pairs from a prefetched ``linkedPrs`` field."""

    if not isinstance(raw, list):
        return ()
    pairs: list[tuple[int, str]] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        number = entry.get("number")
        state = entry.get("state")
        if isinstance(number, int) and isinstance(state, str):
            pairs.append((number, state.upper()))
    return tuple(pairs)


def parse_issue_record(raw: dict[str, Any]) -> IssueRecord:
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

    body = raw.get("body")
    return IssueRecord(
        number=number,
        title=title,
        updated_at=updated_at,
        labels=tuple(labels),
        body=str(body) if body is not None else "",
        assignees=_parse_assignees(raw.get("assignees")),
        linked_prs=_parse_linked_prs(raw.get("linkedPrs")),
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


def has_agent_label(issue: IssueRecord) -> bool:
    """True when any label starts with ``agent-``."""

    return any(label.startswith(AGENT_LABEL_PREFIX) for label in issue.labels)


def check_state_consistency(issue: IssueRecord) -> str | None:
    """Return a reason string when the issue's state label is inconsistent.

    Two mechanical inconsistencies:
      - ``Doing`` with no assignee (work in progress with no active worker).
      - ``Planning`` with an empty body (planning with no description).

    Returns None when the issue is consistent (or carries no state label).
    """

    if STATE_DOING in issue.labels and not issue.assignees:
        return "labeled 'Doing' but has no assignee"
    if STATE_PLANNING in issue.labels and not issue.body.strip():
        return "labeled 'Planning' but has no description body"
    return None


def detect_linked_pr_status(issue: IssueRecord) -> str | None:
    """Return a reason when a linked PR has merged or closed (state can advance).

    Reads ``issue.linked_prs`` (populated by opt-in fetch or --input). Returns
    None when there are no linked PRs or all linked PRs are still open.
    """

    advanced = [
        (num, state)
        for num, state in issue.linked_prs
        if state in ADVANCING_PR_STATES
    ]
    if not advanced:
        return None
    detail = ", ".join(f"#{num} {state.lower()}" for num, state in advanced)
    return f"linked PR(s) concluded ({detail}); state label can advance"


def normalize_title_tokens(title: str) -> frozenset[str]:
    """Return the comparable token set for a title.

    Strips a conventional-commit prefix, lowercases, splits on non-word
    characters, and drops tokens shorter than ``_MIN_TOKEN_LEN``.
    """

    stripped = _CONVENTIONAL_PREFIX.sub("", title).lower()
    tokens = (t for t in _NON_WORD.split(stripped) if len(t) >= _MIN_TOKEN_LEN)
    return frozenset(tokens)


def jaccard_similarity(a: frozenset[str], b: frozenset[str]) -> float:
    """Jaccard similarity of two token sets: |A and B| / |A or B|.

    Returns 0.0 when both sets are empty (no signal to compare).
    """

    if not a and not b:
        return 0.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def detect_duplicates(
    issues: list[IssueRecord], *, threshold: float
) -> list[DuplicateFinding]:
    """Return candidate duplicate pairs whose title similarity >= ``threshold``.

    Each unordered pair is reported at most once, attributed to the
    lower-numbered issue as the canonical ``duplicate_of``. O(n^2) over the
    scanned set; bounded by the API ``--limit``.
    """

    findings: list[DuplicateFinding] = []
    tokenized = [(issue, normalize_title_tokens(issue.title)) for issue in issues]
    for i in range(len(tokenized)):
        issue_i, tokens_i = tokenized[i]
        if not tokens_i:
            continue
        for j in range(i + 1, len(tokenized)):
            issue_j, tokens_j = tokenized[j]
            if not tokens_j:
                continue
            score = jaccard_similarity(tokens_i, tokens_j)
            if score < threshold:
                continue
            canonical, other = sorted(
                (issue_i, issue_j), key=lambda rec: rec.number
            )
            findings.append(
                DuplicateFinding(
                    number=other.number,
                    title=other.title,
                    duplicate_of=canonical.number,
                    duplicate_of_title=canonical.title,
                    score=round(score, 3),
                )
            )
    return findings


def _label_findings(
    issues: list[IssueRecord],
    predicate: Callable[[IssueRecord], bool],
    reason: str,
) -> list[IssueFinding]:
    """Collect findings for issues that fail ``predicate``."""

    return [
        IssueFinding(number=issue.number, title=issue.title, reasons=[reason])
        for issue in issues
        if not predicate(issue)
    ]


def classify(
    issues: list[IssueRecord],
    *,
    now: datetime,
    stale_days: int,
) -> tuple[list[IssueFinding], list[IssueFinding], list[IssueFinding]]:
    """Apply the three original Phase 1 rules to ``issues``.

    Returns ``(stale, missing_priority, missing_area)``. Retained as the stable
    public entry point for the original three rules; ``build_report`` calls it
    and layers the newer rules (#2259) on top.
    """

    stale = [
        IssueFinding(
            number=issue.number,
            title=issue.title,
            reasons=[f"no activity in {stale_days}+ days"],
        )
        for issue in issues
        if is_stale(issue, now=now, stale_days=stale_days)
    ]
    missing_priority = _label_findings(
        issues, has_priority_label, "missing priority:* label"
    )
    missing_area = _label_findings(issues, has_area_label, "missing area-* label")
    return stale, missing_priority, missing_area


def build_report(
    issues: list[IssueRecord],
    *,
    repo: str,
    now: datetime,
    stale_days: int,
    dup_threshold: float = DEFAULT_DUP_THRESHOLD,
    scanned_since: str | None = None,
) -> TriageReport:
    """Assemble a ``TriageReport`` by applying every Phase 1 rule."""

    stale, missing_priority, missing_area = classify(
        issues, now=now, stale_days=stale_days
    )

    state_inconsistent: list[IssueFinding] = []
    linked_pr_advance: list[IssueFinding] = []
    for issue in issues:
        state_reason = check_state_consistency(issue)
        if state_reason is not None:
            state_inconsistent.append(
                IssueFinding(issue.number, issue.title, [state_reason])
            )
        pr_reason = detect_linked_pr_status(issue)
        if pr_reason is not None:
            linked_pr_advance.append(
                IssueFinding(issue.number, issue.title, [pr_reason])
            )

    return TriageReport(
        timestamp=now.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        repo=repo,
        stale_days=stale_days,
        issues_scanned=len(issues),
        scanned_since=scanned_since,
        stale=stale,
        missing_priority=missing_priority,
        missing_area=missing_area,
        missing_agent=_label_findings(
            issues, has_agent_label, "missing agent-* label"
        ),
        state_inconsistent=state_inconsistent,
        linked_pr_advance=linked_pr_advance,
        duplicates=detect_duplicates(issues, threshold=dup_threshold),
    )


def _run_gh(cmd: list[str]) -> str:
    """Run a gh command and return stdout, raising ``RuntimeError`` on failure."""

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30, check=True,
        )
    except subprocess.CalledProcessError as err:
        stderr = (err.stderr or "").strip() or (err.stdout or "").strip()
        raise RuntimeError(f"{' '.join(cmd[:3])} failed: {stderr}") from err
    except subprocess.TimeoutExpired as err:
        raise RuntimeError(f"{' '.join(cmd[:3])} timed out after {err.timeout}s") from err
    except OSError as err:
        raise RuntimeError(f"{' '.join(cmd[:3])} failed to execute: {err}") from err
    return result.stdout or ""


def fetch_open_issues(
    owner: str, repo: str, *, limit: int, since: str | None = None
) -> list[dict[str, Any]]:
    """Fetch open issues via the gh CLI.

    When ``since`` is set (ISO-8601), restrict to issues updated since then via
    a ``updated:>`` search filter (incremental scan). Returns the parsed JSON
    array. Raises ``RuntimeError`` on failure so ``main`` can map an exit code.
    """

    if not 0 <= limit <= 1000:
        raise ValueError("limit must be between 0 and 1000")
    if limit == 0:
        return []

    cmd = [
        "gh", "issue", "list",
        "--repo", f"{owner}/{repo}",
        "--state", "open",
        "--limit", str(limit),
        "--json", "number,title,updatedAt,labels,body,assignees",
    ]
    if since:
        cmd += ["--search", f"updated:>{since}"]

    raw = _run_gh(cmd)
    try:
        data = json.loads(raw or "[]")
    except (json.JSONDecodeError, ValueError, TypeError) as err:
        raise RuntimeError(f"Failed to parse gh output: {err}") from err
    if not isinstance(data, list):
        raise RuntimeError(
            f"gh issue list returned non-list payload: {type(data).__name__}"
        )
    return data


class LinkedPrFetchError(RuntimeError):
    """Raised when linked-PR timeline data cannot be fetched or parsed."""


def fetch_linked_prs(owner: str, repo: str, number: int) -> tuple[tuple[int, str], ...]:
    """Return (pr_number, state) for PRs cross-referenced from an issue timeline."""

    cmd = [
        "gh", "api",
        f"repos/{owner}/{repo}/issues/{number}/timeline",
        "--paginate",
    ]
    try:
        raw = _run_gh(cmd)
        events = json.loads(raw or "[]")
    except (RuntimeError, json.JSONDecodeError, ValueError, TypeError) as err:
        raise LinkedPrFetchError(
            f"failed to fetch linked PRs for issue #{number}: {err}"
        ) from err
    if not isinstance(events, list):
        raise LinkedPrFetchError(
            f"failed to fetch linked PRs for issue #{number}: non-list timeline"
        )

    pairs: list[tuple[int, str]] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        source = event.get("source")
        issue_ref = source.get("issue") if isinstance(source, dict) else None
        if not isinstance(issue_ref, dict):
            continue
        pr = issue_ref.get("pull_request")
        num = issue_ref.get("number")
        if not isinstance(pr, dict) or not isinstance(num, int):
            continue
        state = "MERGED" if pr.get("merged_at") else str(issue_ref.get("state", "")).upper()
        if state:
            pairs.append((num, state))
    return tuple(pairs)


def load_scan_state(path: str) -> str | None:
    """Return the persisted ``last_run`` timestamp, or None if absent/invalid."""

    state_path = Path(path)
    if not state_path.is_file():
        return None
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    last_run = data.get("last_run") if isinstance(data, dict) else None
    if isinstance(last_run, str) and last_run and ISO_TIMESTAMP_PATTERN.match(last_run):
        return last_run
    return None


def save_scan_state(path: str, timestamp: str) -> None:
    """Persist ``last_run`` to the state file (creates parent dirs)."""

    state_path = Path(path)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps({"last_run": timestamp}, indent=2) + "\n", encoding="utf-8"
    )


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
    one invocation per open issue, for structured complexity, area routing,
    dependency, scope, and evidence classification. The mechanical scan stays
    Python-side; YAML only fans out (ADR-006). This function does not call the
    model; it produces the work list the workflow consumes.

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

    scope = (
        f", since {report.scanned_since}" if report.scanned_since else " (full scan)"
    )
    lines: list[str] = [
        f"Triage report for {report.repo} ({report.timestamp})",
        f"Issues scanned: {report.issues_scanned} "
        f"(stale threshold: {report.stale_days} days{scope})",
        "",
    ]
    sections = (
        ("Stale", report.stale),
        ("Missing priority label", report.missing_priority),
        ("Missing area label", report.missing_area),
        ("Missing agent label", report.missing_agent),
        ("State inconsistent", report.state_inconsistent),
        ("Linked PR can advance state", report.linked_pr_advance),
    )
    for heading, findings in sections:
        lines.append(f"{heading} ({len(findings)}):")
        lines.extend(_render_findings(findings))
    lines.append(f"Duplicate candidates ({len(report.duplicates)}):")
    lines.extend(_render_duplicates(report.duplicates))
    return "\n".join(lines)


def _render_findings(findings: list[IssueFinding]) -> list[str]:
    if not findings:
        return ["  (none)"]
    return [f"  #{f.number}: {f.title}" for f in findings]


def _render_duplicates(findings: list[DuplicateFinding]) -> list[str]:
    if not findings:
        return ["  (none)"]
    return [
        f"  #{f.number} ~ #{f.duplicate_of} (score {f.score}): {f.title}"
        for f in findings
    ]


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
        "--dup-threshold", type=float, default=DEFAULT_DUP_THRESHOLD,
        help="Title-similarity threshold for duplicate candidates "
             f"(0.0-1.0, default: {DEFAULT_DUP_THRESHOLD}).",
    )
    parser.add_argument(
        "--limit", type=int, default=300,
        help="Max issues to fetch from the API (0-1000, default: 300).",
    )
    parser.add_argument(
        "--format", choices=["json", "human"], default="human",
        help="Output format (default: human).",
    )
    parser.add_argument(
        "--ai", action="store_true",
        help="Emit a GitHub Actions matrix of open issues for Phase 2 AI triage "
             "(structured classification via .github/actions/ai-review). "
             "Overrides --format; prints a JSON matrix payload.",
    )
    parser.add_argument(
        "--input", default="",
        help="Path to a JSON file with prefetched issues (skips gh call). "
             "Useful for testing and air-gapped runs.",
    )
    parser.add_argument(
        "--state-file", default="",
        help="Path to the incremental-scan state file. When set, the scan is "
             "restricted to issues updated since the last run and the new run "
             "timestamp is persisted.",
    )
    parser.add_argument(
        "--since", default="",
        help="ISO-8601 timestamp; restrict the scan to issues updated since "
             "then. Overrides the --state-file last_run value.",
    )
    parser.add_argument(
        "--full-scan", action="store_true",
        help="Ignore the --state-file last_run and scan all open issues.",
    )
    parser.add_argument(
        "--check-linked-prs", action="store_true",
        help="Fetch each issue's timeline to detect merged/closed linked PRs. "
             "Adds one API call per issue; off by default to keep scans fast.",
    )
    parser.add_argument(
        "--github-output",
        default="",
        help="Optional GitHub output file for matrix, has-issues, and count values.",
    )
    return parser.parse_args(argv)


def load_issues_from_input(path: str) -> list[dict[str, Any]]:
    """Read prefetched issues from a JSON file."""

    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, list):
        raise ValueError(
            f"--input file must contain a JSON array; got {type(data).__name__}"
        )
    return data


def _resolve_since(args: argparse.Namespace) -> str | None:
    """Resolve the incremental-scan ``since`` value from args + state file."""

    if args.since:
        return str(args.since)
    if args.full_scan or not args.state_file:
        return None
    return load_scan_state(args.state_file)


def _enrich_linked_prs(
    issues: list[IssueRecord], owner: str, repo: str
) -> list[IssueRecord]:
    """Return issues with their ``linked_prs`` populated from the timeline API."""

    from dataclasses import replace

    enriched: list[IssueRecord] = []
    for issue in issues:
        try:
            linked = fetch_linked_prs(owner, repo, issue.number)
        except LinkedPrFetchError as err:
            raise _InputError(
                3, f"failed to fetch linked PRs for issue #{issue.number}: {err}"
            ) from err
        enriched.append(replace(issue, linked_prs=linked))
    return enriched


class _InputError(Exception):
    """Carries an exit code and message when issue loading fails."""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _validate_args(args: argparse.Namespace) -> int | None:
    """Return an error exit code for invalid arguments, or None when valid."""

    if args.stale_days < 0:
        print("--stale-days must be >= 0", file=sys.stderr)
        return 2
    if not 0.0 <= args.dup_threshold <= 1.0:
        print("--dup-threshold must be between 0.0 and 1.0", file=sys.stderr)
        return 2
    if not 0 <= args.limit <= 1000:
        print("--limit must be between 0 and 1000", file=sys.stderr)
        return 2
    if args.since and not ISO_TIMESTAMP_PATTERN.match(args.since):
        print(f"Invalid --since timestamp format: {args.since}", file=sys.stderr)
        return 2
    return None


def _obtain_raw_issues(
    args: argparse.Namespace, since: str | None
) -> tuple[list[dict[str, Any]], str]:
    """Load raw issues from --input or the gh CLI. Raise ``_InputError`` on failure."""

    if args.input:
        try:
            return load_issues_from_input(args.input), str(args.input)
        except (OSError, ValueError, json.JSONDecodeError) as err:
            raise _InputError(2, f"Failed to read --input file: {err}") from err

    owner = args.owner
    repo = args.repo
    if args.ai and (not owner or not repo):
        owner, repo = split_github_repository(os.environ.get("GITHUB_REPOSITORY", ""))
    if not owner or not repo:
        raise _InputError(
            2, "--owner and --repo are required when --input is not set"
        )

    try:
        raw = fetch_open_issues(owner, repo, limit=args.limit, since=since)
    except ValueError as err:
        raise _InputError(2, str(err)) from err
    except RuntimeError as err:
        raise _InputError(3, str(err)) from err
    return raw, f"{owner}/{repo}"


def _parse_records(raw_issues: list[dict[str, Any]]) -> list[IssueRecord]:
    """Parse raw issue dicts into records, skipping (and warning on) malformed ones."""


    issues: list[IssueRecord] = []
    for raw in raw_issues:
        try:
            issues.append(parse_issue_record(raw))
        except ValueError as err:
            print(f"warn: skipping malformed issue: {err}", file=sys.stderr)
    return issues


def _emit(report: TriageReport, output_format: str) -> None:
    """Print the report in the requested format."""

    if output_format == "json":
        print(json.dumps(asdict(report), indent=2))
    else:
        print(format_human(report))


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    invalid = _validate_args(args)
    if invalid is not None:
        return invalid

    since = _resolve_since(args)

    try:
        raw_issues, repo_label = _obtain_raw_issues(args, since)
    except _InputError as exc:
        print(exc.message, file=sys.stderr)
        return exc.code

    issues = _parse_records(raw_issues)
    if args.check_linked_prs and not args.input and args.owner and args.repo:
        try:
            issues = _enrich_linked_prs(issues, args.owner, args.repo)
        except _InputError as exc:
            print(exc.message, file=sys.stderr)
            return exc.code

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
        dup_threshold=args.dup_threshold,
        scanned_since=since,
    )
    _emit(report, args.format)

    # Persist the run timestamp only after a successful scan, so a failed run
    # does not advance the watermark and skip issues next time.
    if args.state_file and not args.input:
        try:
            save_scan_state(args.state_file, report.timestamp)
        except OSError as err:
            print(f"Failed to write --state-file: {err}", file=sys.stderr)
            return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
