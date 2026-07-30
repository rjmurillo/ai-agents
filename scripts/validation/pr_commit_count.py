#!/usr/bin/env python3
"""Classify a pull request's commit count for the PR validation gate.

Extracted from the inline PowerShell of the ``Check PR commit count`` step in
``.github/workflows/pr-validation.yml`` so the fetch-and-classify logic is
testable (ADR-006) and tolerant of transient GitHub API failures (issue #3262).

Behavior:

* On a healthy API response, count commits and map the count to a status using
  the issue #362 thresholds (warning 10, alert 15, block 20). The downstream
  ``Enforce Blocking Issues`` step enforces the ``BLOCKED`` status; this script
  only classifies.
* On a *transient* transport error (HTTP 503, "no server is currently
  available", connection reset, timeout), degrade to ``status=UNKNOWN`` and
  exit 0. The commit cap is advisory for that run and re-fires on the next
  healthy run, so a GitHub outage no longer red-blocks an otherwise clean PR.
* On a *genuine* error (auth failure, PR not found, bad arguments), exit
  non-zero so the failure stays visible. Transient tolerance must never swallow
  a real policy or auth failure.
* A missing ``gh`` binary is a *config* error (ADR-035 exit 2), not an external
  or transient one: the environment is misconfigured, so the run cannot proceed.

The commit count is fetched with ``per_page=100`` (the GitHub REST maximum for
a single page) and is not paginated, so the reported count saturates at 100.
Classification is unaffected: any PR above ``BLOCK_THRESHOLD`` (20) is
``BLOCKED``, and 100 far exceeds 20, so a PR with more than 100 commits is
always ``BLOCKED`` regardless of the exact count. For such PRs the emitted
``commit_count`` is a floor.

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

from scripts.github_core.api import resolve_repo_params  # noqa: E402

# Commit-count thresholds (issue #362). A PR above BLOCK_THRESHOLD is
# blocked by the downstream Enforce Blocking Issues step unless it carries the
# commit-limit-bypass label.
WARNING_THRESHOLD = 10
ALERT_THRESHOLD = 15
BLOCK_THRESHOLD = 20
# Issue #3596: the ceiling is relieved to 40 for a branch that merges main, and
# the pre-push hook has always honoured that. CI never did, so a branch the
# hook let through was blocked on arrival. These two numbers are the single
# source of truth; `scripts/validation/git_hook_policy.py` imports them rather
# than restating them.
MAIN_MERGE_BLOCK_THRESHOLD = 40

# Sentinel status emitted when a transient API failure prevents a real count.
STATUS_UNKNOWN = "UNKNOWN"

# Substrings that mark a GitHub API failure as transient transport noise rather
# than a real error. Matched case-insensitively against gh's stderr. Kept
# deliberately narrow so auth (401/403) and not-found (404) stay fatal.
_TRANSIENT_MARKERS: tuple[str, ...] = (
    "no server is currently available",
    "http 502",
    "http 503",
    "http 504",
    "bad gateway",
    "service unavailable",
    "gateway timeout",
    "connection reset",
    "connection refused",
    "timeout was reached",
    "i/o timeout",
    "eof",
    "tls handshake timeout",
)


@dataclass(frozen=True)
class CountResult:
    """Outcome of a commit-count fetch.

    Exactly one of ``count`` or ``transient`` is meaningful: when ``transient``
    is True the count could not be determined and ``status`` is UNKNOWN.
    """

    status: str
    count: int | None
    transient: bool
    limit: int = BLOCK_THRESHOLD


def classify_count(count: int, limit: int = BLOCK_THRESHOLD) -> str:
    """Map a commit count to a threshold status (issue #362).

    ``limit`` is the effective block ceiling: BLOCK_THRESHOLD normally, or
    MAIN_MERGE_BLOCK_THRESHOLD when the branch carries a merge from the base
    (issue #3596). The advisory WARNING and ALERT rungs are unchanged.

    The comparison is strict (issue #3721). The local pre-push hook allows
    ``commit_count <= limit``, so blocking at ``count == limit`` here would
    block a push the hook had just accepted.
    """
    if count > limit:
        return "BLOCKED"
    if count >= ALERT_THRESHOLD:
        return "ALERT"
    if count >= WARNING_THRESHOLD:
        return "WARNING"
    return "OK"


def _is_external_parent(parent: object, own_shas: set[str]) -> bool:
    """Return True only when this parent is a readable sha the branch does not own.

    ``contains_base_merge`` gates an exemption, so an unreadable parent must not
    buy it. A parent that is not a mapping, carries no ``sha``, or carries a
    non-string ``sha`` is unreadable and fails closed to False rather than
    reading as evidence of an external merge.
    """
    if not isinstance(parent, dict):
        return False
    sha = parent.get("sha")
    if not isinstance(sha, str) or not sha:
        return False
    return sha not in own_shas


def contains_base_merge(commits: list[Any]) -> bool:
    """Return True when the PR carries a merge commit from outside the branch.

    The commits endpoint returns exactly the commits unique to the head branch.
    A merge commit inside that list whose parents are not all in the list merged
    something the branch did not author, which is the base branch. That is the
    server-side equivalent of the hook's `merge-base --is-ancestor` check
    against origin/main.
    """
    own_shas: set[str] = set()
    for commit in commits:
        if not isinstance(commit, dict):
            continue
        own_sha = commit.get("sha")
        if isinstance(own_sha, str) and own_sha:
            own_shas.add(own_sha)
    for commit in commits:
        if not isinstance(commit, dict):
            continue
        parents = commit.get("parents")
        if not isinstance(parents, list) or len(parents) < 2:
            continue
        if any(_is_external_parent(parent, own_shas) for parent in parents[1:]):
            return True
    return False


def is_transient_error(stderr: str) -> bool:
    """Return True when gh stderr indicates a transient transport failure."""
    haystack = stderr.lower()
    return any(marker in haystack for marker in _TRANSIENT_MARKERS)


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
    saturates at 100. This does not change classification: any count above
    BLOCK_THRESHOLD (20) is BLOCKED, and 100 >> 20.
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

    count = len(commits)
    limit = MAIN_MERGE_BLOCK_THRESHOLD if contains_base_merge(commits) else BLOCK_THRESHOLD
    return CountResult(classify_count(count, limit), count, transient=False, limit=limit)


def _write_github_output(status: str, count: int | None, limit: int = BLOCK_THRESHOLD) -> None:
    """Append status/count/limit key=value lines to $GITHUB_OUTPUT when set."""
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        return
    count_value = "" if count is None else str(count)
    with open(output_path, "a", encoding="utf-8") as handle:
        handle.write(f"status={status}\n")
        handle.write(f"commit_count={count_value}\n")
        handle.write(f"commit_limit={limit}\n")


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

    _write_github_output(outcome.status, outcome.count, outcome.limit)

    if outcome.transient:
        print(
            f"::warning::Commit count for PR #{args.pr_number} could not be "
            "determined (transient GitHub API failure). Skipping the commit-count "
            "check for this run; it re-fires on the next healthy run.",
        )
        return 0

    count = outcome.count if outcome.count is not None else 0
    print(f"PR #{args.pr_number} has {count} commits (status: {outcome.status})")
    if outcome.status == "BLOCKED":
        print(
            f"::error::PR exceeds commit limit ({count} > {outcome.limit}). "
            "Consider splitting this PR."
        )
    elif outcome.status == "ALERT":
        print(
            f"::warning::PR approaching commit limit ({count} >= {ALERT_THRESHOLD}). "
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
