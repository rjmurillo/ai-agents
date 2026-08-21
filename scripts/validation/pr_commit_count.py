#!/usr/bin/env python3
"""Classify a pull request's commit count for the PR validation gate.

Extracted from the inline PowerShell of the ``Check PR commit count`` step in
``.github/workflows/pr-validation.yml`` so the fetch-and-classify logic is
testable (ADR-006) and tolerant of transient GitHub API failures (issue #3262).

Behavior:

* On a healthy API response, count commits and map the count to a status using
  the issue #362 thresholds (warning 10, alert 15). This is advisory only: a
  large commit count never blocks a push or a merge. The
  ``commit-limit-bypass`` label, the 20/40-commit block ceiling, and the
  main-merge relief that used to raise it were removed (issue #5230) because
  the hard block required local verification of a GitHub label that this
  harness cannot always perform (`gh` has no API access in some sandboxed
  sessions), which forced authors into expensive workarounds -- spinning up an
  entirely new stacked branch and PR -- just to route around a check that
  could not confirm a fact that was already true. ``needs-split`` stays: it is
  a purely advisory label with no enforcement attached.
* On a *transient* transport error (HTTP 503, "no server is currently
  available", connection reset, timeout), degrade to ``status=UNKNOWN`` and
  exit 0. A GitHub outage no longer affects this advisory check either way.
* On a *genuine* error (auth failure, PR not found, bad arguments), exit
  non-zero so the failure stays visible. Transient tolerance must never swallow
  a real policy or auth failure.
* A missing ``gh`` binary is a *config* error (ADR-035 exit 2), not an external
  or transient one: the environment is misconfigured, so the run cannot proceed.

The commit count is fetched with ``per_page=100`` (the GitHub REST maximum for
a single page) and is not paginated, so the reported count saturates at 100.
For such PRs the emitted ``commit_count`` is a floor; this has no effect on
classification since the only two active thresholds are 10 and 15.

Exit codes follow ADR-035:
    0 - Success (a status was classified, including transient UNKNOWN)
    2 - Config error (missing/invalid arguments, unresolvable repo, missing gh)
    3 - External error (non-transient gh/API failure)
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.github_core.api import (  # noqa: E402
    GhAuthStatus,
    classify_gh_failure_text,
    resolve_repo_params,
)

# Commit-count thresholds (issue #362). Advisory only (issue #5230): neither
# threshold blocks a push or a merge. WARNING_THRESHOLD and ALERT_THRESHOLD
# only decide which notice is printed and which GitHub Actions annotation
# level is used.
WARNING_THRESHOLD = 10
ALERT_THRESHOLD = 15

# Sentinel status emitted when a transient API failure prevents a real count.
STATUS_UNKNOWN = "UNKNOWN"

# Conditions that mark a GitHub API failure as something to degrade around
# rather than fail on. Auth (401), permission denial (403 without rate-limit
# wording), and not-found (404) stay fatal, so a real policy failure is never
# swallowed. A 403 that carries "API rate limit exceeded" is a refusal that
# clears on its own, and treating it as fatal red-blocked a clean PR during a
# quota window (same shape as issue #4326 defect 1).
_TRANSIENT_STATUSES = frozenset(
    {
        GhAuthStatus.TRANSIENT_ERROR,
        GhAuthStatus.RATE_LIMITED,
        GhAuthStatus.SECONDARY_RATE_LIMITED,
    }
)


@dataclass(frozen=True)
class CountResult:
    """Outcome of a commit-count fetch.

    Exactly one of ``count`` or ``transient`` is meaningful: when ``transient``
    is True the count could not be determined and ``status`` is UNKNOWN.

    ``count`` is the authored (non-merge) commit count used for classification.
    ``total_count`` is the raw total including branch-maintenance merges, kept
    for audit and diagnostics (issue #3920).
    """

    status: str
    count: int | None
    transient: bool
    total_count: int | None = None


def classify_count(count: int) -> str:
    """Map a commit count to an advisory threshold status (issue #362).

    Advisory only (issue #5230): there is no block tier. A PR of any size
    passes; this only decides which notice, if any, gets printed.
    """
    if count >= ALERT_THRESHOLD:
        return "ALERT"
    if count >= WARNING_THRESHOLD:
        return "WARNING"
    return "OK"


def _authored_commit_count(commits: list[Any]) -> int:
    """Count commits with at most one parent (not branch-maintenance merges).

    A merge commit has more than one parent. Branch-maintenance merges from the
    base branch consume the same count threshold as authored changes but do not
    represent scope growth. Issue #3920.

    A commit without a readable ``parents`` key (missing, null, not a list) is
    counted as authored to fail closed: an unreadable parent must not silently
    lower the count and mask real growth from the advisory notice.
    """
    count = 0
    for commit in commits:
        if not isinstance(commit, dict):
            count += 1
            continue
        parents = commit.get("parents")
        if not isinstance(parents, list) or len(parents) <= 1:
            count += 1
    return count


def is_transient_error(stderr: str) -> bool:
    """Return True when gh stderr indicates a condition that clears on its own.

    Routes through the shared classifier so this validator and the gh preflight
    cannot drift on what "transient" means. The local substring list it replaced
    excluded 403 by design, which made an "API rate limit exceeded" refusal fatal
    here while every other caller degraded around it.
    """
    return classify_gh_failure_text(stderr) in _TRANSIENT_STATUSES


def _run_gh(argv: list[str]) -> subprocess.CompletedProcess[str]:
    """Run a gh command, returning the completed process.

    A timeout is surfaced as a transient CompletedProcess (returncode 124,
    ``timeout was reached`` stderr) so the caller degrades rather than crashing.
    A missing gh binary is a config error (ADR-035 exit 2), not transient: it is
    signalled with returncode 127 and empty stderr so ``is_transient_error``
    stays False and ``fetch_commit_count`` maps it to a config failure.
    """
    try:
        return subprocess.run(
            argv,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(
            argv, returncode=124, stdout="", stderr="timeout was reached"
        )
    except FileNotFoundError:
        # gh missing is a config error, not transient. Signal with a distinct
        # returncode and an empty stderr so is_transient_error stays False.
        return subprocess.CompletedProcess(argv, returncode=127, stdout="", stderr="")


def fetch_commit_count(pr_number: int, owner: str, repo: str) -> CountResult:
    """Fetch and classify the commit count for a PR.

    Returns a CountResult. Transient transport failures yield
    ``CountResult(STATUS_UNKNOWN, None, transient=True)``; a non-transient gh
    failure raises RuntimeError so the caller can exit 3; a missing gh binary
    raises FileNotFoundError so the caller can exit 2 (config error, ADR-035).

    The count is fetched with ``per_page=100`` and is not paginated, so it
    saturates at 100. Classification is unaffected since the only active
    thresholds are 10 and 15.
    """
    endpoint = f"repos/{owner}/{repo}/pulls/{pr_number}/commits?per_page=100"
    result = _run_gh(["gh", "api", endpoint])

    if result.returncode == 127:
        raise FileNotFoundError(
            "GitHub CLI (gh) is not installed or not found on PATH; cannot fetch "
            f"the commit count for PR #{pr_number}."
        )

    if result.returncode != 0:
        if is_transient_error(result.stderr):
            return CountResult(STATUS_UNKNOWN, None, transient=True)
        raise RuntimeError(
            f"Failed to fetch commits for PR #{pr_number} "
            f"(exit {result.returncode}): {result.stderr.strip()}"
        )

    try:
        commits: Any = json.loads(result.stdout)
    except (json.JSONDecodeError, ValueError):
        # A 200 with an unparseable body during a degraded window is treated as
        # transient: skip the count rather than block on infra noise.
        return CountResult(STATUS_UNKNOWN, None, transient=True)

    if not isinstance(commits, list):
        raise RuntimeError(
            f"Unexpected commits payload for PR #{pr_number}: expected a list, "
            f"got {type(commits).__name__}"
        )

    total_count = len(commits)
    authored_count = _authored_commit_count(commits)
    return CountResult(
        classify_count(authored_count),
        authored_count,
        transient=False,
        total_count=total_count,
    )


def _write_github_output(status: str, count: int | None) -> None:
    """Append status/count key=value lines to $GITHUB_OUTPUT when set."""
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        return
    count_value = "" if count is None else str(count)
    with open(output_path, "a", encoding="utf-8") as handle:
        handle.write(f"status={status}\n")
        handle.write(f"commit_count={count_value}\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pr-number", type=int, required=True, help="Pull request number")
    parser.add_argument(
        "--owner", default="", help="Repository owner (inferred from git remote if omitted)"
    )
    parser.add_argument(
        "--repo", default="", help="Repository name (inferred from git remote if omitted)"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns an ADR-035 exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.pr_number <= 0:
        print(f"Error: --pr-number must be positive, got {args.pr_number}", file=sys.stderr)
        return 2

    # resolve_repo_params exits 2 on an unresolvable/invalid repo. Its shared
    # remediation text names PowerShell-style -Owner/-Repo flags, so add a hint
    # naming this script's actual --owner/--repo flags (PR #3264 review).
    try:
        repo_info = resolve_repo_params(args.owner, args.repo)
    except SystemExit as exc:
        print(
            "Hint: pass --owner and --repo to this script when the repository "
            "cannot be inferred from the git remote.",
            file=sys.stderr,
        )
        return exc.code if isinstance(exc.code, int) else 2

    try:
        outcome = fetch_commit_count(args.pr_number, repo_info.owner, repo_info.repo)
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 3

    _write_github_output(outcome.status, outcome.count)

    if outcome.transient:
        print(
            f"::warning::Commit count for PR #{args.pr_number} could not be "
            "determined (transient GitHub API failure). Skipping the commit-count "
            "check for this run; it re-fires on the next healthy run.",
        )
        return 0

    count = outcome.count if outcome.count is not None else 0
    total_count = outcome.total_count if outcome.total_count is not None else count
    suffix = f" ({total_count} total, {count} authored)" if total_count != count else ""
    print(f"PR #{args.pr_number} has {count} commits (status: {outcome.status}){suffix}")
    if outcome.status == "ALERT":
        print(
            f"::warning::PR approaching a large commit count ({count} >= {ALERT_THRESHOLD}). "
            "Consider shipping current changes."
        )
    elif outcome.status == "WARNING":
        print(
            f"::notice::PR has many commits ({count} >= {WARNING_THRESHOLD}). "
            "Consider squashing or splitting."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
