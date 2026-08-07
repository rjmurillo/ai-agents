#!/usr/bin/env python3
"""Report open PRs whose work may already be on the base branch.

Three of six open fleet PRs sampled on 2026-08-02 were already fixed on
`main` while they sat (issue #4355). Nothing announced it: GitHub reported
one as `blocked` and two as `dirty`, and neither state distinguishes "needs
a rebase" from "the work is already done". The collision only became
visible when someone started a rebase and read the conflict, which is the
expensive step.

This is a REPORT, not a gate. It never closes a PR and never fails on a
finding, because the signal has a known false positive: PR #4163 has two
closed linked issues and is not superseded, since a different PR closed
them. Every flag needs a human or an agent to confirm.

Three reasons flag a PR, and each is a fact the reader can check:

    closed-linked-issue   a linked issue is already CLOSED while the PR is
                          open. Caught #4164 (issue #4058) and #4102
                          (issue #4015).
    stale-base            the PR is at least --stale-base commits behind its
                          base. All three superseded PRs were 24 or more
                          behind; measured after the fact, 50, 24, and 167.
    no-linked-issue       a stale PR that closes nothing, so issue state can
                          say nothing about it and nobody can check it
                          against a tracked defect. Caught #3979, which the
                          closed-issue signal alone cannot see. Gated on
                          staleness on purpose: unlinked-but-fresh is an
                          issue-linkage question, not a supersession one,
                          and ungated it flagged 27 of 44 open PRs against
                          14 gated.

Patch-id supersession (`git cherry`, as `check_pr_live_state.py` runs it)
is deliberately NOT one of them. Measured against those same four PRs on
2026-08-03 it reported `superseded=0` for every one, because each fix had
been reimplemented differently on main rather than cherry-picked. It
answers a narrower question than this report asks.

EXIT CODES:
  0 - report produced (findings or not)
  2 - usage or configuration error
  3 - external error (GitHub API unreachable)

See ADR-035 Exit Code Standardization.
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

# `pr-maintenance.yml` invokes this file as `python3 scripts/report_pr_supersession.py`,
# so sys.path[0] is `scripts/` and the `scripts` package is unreachable without this
# (.claude/rules/ci-scripts.md MUST 16). Everything reached from here must stay stdlib:
# that job runs `actions/checkout` and nothing else.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.github_core.api import resolve_repo_params

logger = logging.getLogger(__name__)

#: Commits behind base at which a PR's payload is worth re-checking against
#: the base branch. The three confirmed superseded PRs in #4355 were 24, 50,
#: and 167 behind; the false positive #4163 was 12.
DEFAULT_STALE_BASE = 20

REASON_CLOSED_ISSUE = "closed-linked-issue"
REASON_NO_ISSUE = "no-linked-issue"
REASON_STALE_BASE = "stale-base"

OPEN_PRS_QUERY = """\
query($owner: String!, $name: String!, $limit: Int!) {
    repository(owner: $owner, name: $name) {
        pullRequests(states: OPEN, first: $limit, orderBy: {field: UPDATED_AT, direction: DESC}) {
            nodes {
                number
                title
                isDraft
                baseRefName
                headRefOid
                closingIssuesReferences(first: 10) {
                    nodes { number state }
                }
            }
        }
    }
}"""


@dataclass(frozen=True)
class Finding:
    """One open PR, its supersession evidence, and why it was flagged."""

    number: int
    title: str
    is_draft: bool
    base_ref: str
    base_distance: int | None
    closed_issues: list[int] = field(default_factory=list)
    open_issues: list[int] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)

    @property
    def flagged(self) -> bool:
        return bool(self.reasons)


def linked_issue_states(pull_request: dict[str, Any]) -> tuple[list[int], list[int]]:
    """Split a PR's linked issues into (closed, open) issue numbers.

    GraphQL returns ``null`` rather than an absent key for an empty
    connection, so every level is collapsed explicitly instead of relying
    on a ``.get`` default.
    """
    refs = pull_request.get("closingIssuesReferences")
    nodes = (refs or {}).get("nodes") or []
    closed: list[int] = []
    opened: list[int] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        number = node.get("number")
        if not isinstance(number, int):
            continue
        if str(node.get("state", "")).upper() == "CLOSED":
            closed.append(number)
        else:
            opened.append(number)
    return closed, opened


def classify_pull_request(
    pull_request: dict[str, Any],
    base_distance: int | None,
    stale_base: int = DEFAULT_STALE_BASE,
) -> Finding:
    """Turn one PR payload plus its base distance into a Finding.

    Pure: every input is data, so the reasons are testable without GitHub.
    """
    closed, opened = linked_issue_states(pull_request)
    is_stale = base_distance is not None and base_distance >= stale_base
    reasons: list[str] = []
    if closed:
        reasons.append(REASON_CLOSED_ISSUE)
    if is_stale:
        reasons.append(REASON_STALE_BASE)
    if is_stale and not closed and not opened:
        reasons.append(REASON_NO_ISSUE)
    return Finding(
        number=int(pull_request["number"]),
        title=str(pull_request.get("title") or ""),
        is_draft=bool(pull_request.get("isDraft")),
        base_ref=str(pull_request.get("baseRefName") or ""),
        base_distance=base_distance,
        closed_issues=closed,
        open_issues=opened,
        reasons=reasons,
    )


def build_report(
    pull_requests: list[dict[str, Any]],
    distances: dict[int, int | None],
    stale_base: int = DEFAULT_STALE_BASE,
) -> dict[str, Any]:
    """Classify every PR and summarize. Examined count is always reported."""
    findings = [
        classify_pull_request(pr, distances.get(int(pr["number"])), stale_base)
        for pr in pull_requests
    ]
    flagged = [finding for finding in findings if finding.flagged]
    return {
        "examined": len(findings),
        "flagged": len(flagged),
        "stale_base_threshold": stale_base,
        "findings": [asdict(finding) for finding in findings],
    }


def render_human(report: dict[str, Any]) -> str:
    """One line per flagged PR, plus the examined count.

    The examined count is printed whether or not anything was flagged, so a
    run that saw nothing is distinguishable from a run that saw nothing
    wrong (`.claude/rules/ci-scripts.md` MUST 12).
    """
    lines = [
        f"PR supersession report: {report['flagged']} flagged of "
        f"{report['examined']} open PRs examined "
        f"(stale-base threshold {report['stale_base_threshold']})"
    ]
    for finding in report["findings"]:
        if not finding["reasons"]:
            continue
        distance = finding["base_distance"]
        behind = "unknown" if distance is None else str(distance)
        lines.append(
            f"  #{finding['number']} behind={behind} "
            f"closed_issues={finding['closed_issues'] or '-'} "
            f"open_issues={finding['open_issues'] or '-'} "
            f"reasons={','.join(finding['reasons'])} :: {finding['title'][:60]}"
        )
    if report["flagged"]:
        lines.append(
            "  Confirm each one before acting. A closed linked issue can belong "
            "to a different PR (#4163)."
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# I/O adapter
# ---------------------------------------------------------------------------


class GitHubReadError(RuntimeError):
    """The report could not read GitHub. Surfaced as exit 3."""


def _run_gh(args: list[str], timeout: int = 60) -> str:
    try:
        result = subprocess.run(
            ["gh", *args],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except (subprocess.SubprocessError, OSError) as exc:
        raise GitHubReadError(f"gh invocation failed: {exc}") from exc
    if result.returncode != 0:
        raise GitHubReadError(f"gh exited {result.returncode}: {(result.stderr or '')[:200]}")
    return result.stdout or ""


def fetch_open_pull_requests(owner: str, repo: str, limit: int) -> list[dict[str, Any]]:
    """Read open PRs with their linked-issue state in one GraphQL call."""
    raw = _run_gh(
        [
            "api",
            "graphql",
            "-f",
            f"query={OPEN_PRS_QUERY}",
            "-f",
            f"owner={owner}",
            "-f",
            f"name={repo}",
            "-F",
            f"limit={limit}",
        ]
    )
    try:
        payload = json.loads(raw)
        nodes = payload["data"]["repository"]["pullRequests"]["nodes"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise GitHubReadError(f"unparseable PR list: {exc}") from exc
    return [node for node in nodes if isinstance(node, dict)]


def fetch_base_distance(owner: str, repo: str, base: str, head: str) -> int | None:
    """Commits the PR head is behind its base, or None when unreadable.

    One REST compare per PR, which is the cost the issue budgeted. An
    unreadable distance is reported as unknown rather than as zero: zero
    would read as a fresh branch and hide exactly what the report exists
    to surface.
    """
    try:
        raw = _run_gh(
            ["api", f"repos/{owner}/{repo}/compare/{base}...{head}", "--jq", ".behind_by"]
        )
    except GitHubReadError as exc:
        logger.warning("op=base_distance_failed head=%s err=%s", head[:12], exc)
        return None
    text = raw.strip()
    return int(text) if text.lstrip("-").isdigit() else None


def collect_distances(owner: str, repo: str, prs: list[dict[str, Any]]) -> dict[int, int | None]:
    return {
        int(pr["number"]): fetch_base_distance(
            owner, repo, str(pr.get("baseRefName") or "main"), str(pr.get("headRefOid") or "")
        )
        for pr in prs
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--owner", default="", help="Repository owner")
    parser.add_argument("--repo", default="", help="Repository name")
    parser.add_argument("--limit", type=int, default=100, help="Open PRs to read")
    parser.add_argument(
        "--stale-base",
        type=int,
        default=DEFAULT_STALE_BASE,
        help="Commits behind base at which a PR is flagged",
    )
    parser.add_argument("--output-format", choices=["human", "json"], default="human")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    resolved = resolve_repo_params(args.owner, args.repo)
    try:
        prs = fetch_open_pull_requests(resolved.owner, resolved.repo, args.limit)
        distances = collect_distances(resolved.owner, resolved.repo, prs)
    except GitHubReadError as exc:
        print(f"pr-supersession: {exc}", file=sys.stderr)
        return 3
    report = build_report(prs, distances, args.stale_base)
    if args.output_format == "json":
        print(json.dumps(report, indent=2))
    else:
        print(render_human(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
