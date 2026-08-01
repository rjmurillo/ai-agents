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
from collections.abc import Callable, Sequence
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

# Wall-clock bound on this module's git calls. Matched to
# `git_hook_policy.DEFAULT_SUBPROCESS_TIMEOUT_SECONDS` on purpose: the two gates
# read the same trunk, so giving CI a shorter budget would let a slow runner
# time out on a walk the hook completes, and the ceilings would diverge again on
# nothing but machine speed. The hosting CI job caps itself at 10 minutes.
_GIT_TIMEOUT_SECONDS = 90

# A git runner: given a repo root and git arguments, return the finished
# process. `git_hook_policy` supplies its own so a trunk read inside a hook
# keeps that module's scrubbed environment and timeout reporting.
GitRunner = Callable[[Path, Sequence[str]], subprocess.CompletedProcess[str]]

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


def _run_git(repo_root: Path, argv: Sequence[str]) -> subprocess.CompletedProcess[str]:
    """Run a git command in repo_root, failing closed instead of raising or hanging.

    ``core.commitGraph=false`` mirrors the pre-push hook's runner
    (``git_hook_policy._git_command``). A stale or corrupt commit-graph file can
    make ``rev-list`` report a trunk the repository does not actually have, and
    a governance decision must not rest on a cache this gate cannot verify.

    Every failure mode is returned rather than raised: a timeout comes back as
    returncode 124 and a missing or unusable git binary as 127, so callers read
    a non-zero returncode and deny relief. Without the timeout a wedged
    ``rev-list`` would hang the CI step until the job timeout, and, since the
    pre-push hook shares this module's trunk reader, could wedge a push.
    """
    command = ["git", "-c", "core.commitGraph=false", *argv]
    try:
        return subprocess.run(
            command,
            cwd=repo_root,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=_GIT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        # Deliberately not the wording in _TRANSIENT_MARKERS. That vocabulary is
        # for gh transport noise, where degrading to UNKNOWN is right. A git
        # timeout here denies relief instead, and the two must not be confused
        # if this result ever reaches is_transient_error.
        return subprocess.CompletedProcess(command, 124, "", "git rev-list exceeded its budget")
    except OSError:
        # FileNotFoundError (git absent) and its OSError siblings are config
        # problems, not merge evidence. Fail closed to the 20-commit ceiling.
        return subprocess.CompletedProcess(command, 127, "", "git is not available")


def main_first_parent_shas(repo_root: Path, run_git: GitRunner | None = None) -> frozenset[str]:
    """Return the SHAs on origin/main's first-parent lineage (the direct trunk).

    A branch that main has landed through a merge PR is reachable from main but
    sits on a non-first parent of the landing merge. Merging such a branch does
    not bring in new history, so it does not qualify for the raised commit limit.
    Only commits on the first-parent spine count.

    ``run_git`` lets a caller supply its own vetted git runner. The pre-push hook
    passes ``git_hook_policy._run_git`` so a trunk read taken inside a hook keeps
    that module's scrubbed git environment (``GIT_DIR``, ``GIT_SHALLOW_FILE`` and
    the rest of ``GIT_ENV_KEYS`` are unset there, and git sets several of them
    while a hook runs) along with its timeout diagnostics. CI takes this module's
    ``_run_git``. Only the process invocation varies; the traversal stays one
    implementation, which is what issue #3997 requires.

    Returns an empty frozenset when git fails or origin/main does not exist,
    so callers fail closed (no relief) rather than open. CI therefore requires a
    checkout that populates ``refs/remotes/origin/main``; ``pr-validation.yml``
    pins ``fetch-depth: 0`` for that reason.
    """
    runner = _run_git if run_git is None else run_git
    result = runner(repo_root, ["rev-list", "--first-parent", "origin/main"])
    if result.returncode != 0:
        return frozenset()
    return frozenset(result.stdout.split())


def _is_external_parent(parent: object, own_shas: set[str]) -> bool:
    """Return True only when this parent is a readable sha the branch does not own.

    An unreadable parent must not buy relief: a parent that is not a mapping,
    carries no ``sha``, or carries a non-string ``sha`` is unreadable and fails
    closed to False.
    """
    if not isinstance(parent, dict):
        return False
    sha = parent.get("sha")
    if not isinstance(sha, str) or not sha:
        return False
    return sha not in own_shas


def _external_non_first_parent_shas(commits: list[Any]) -> set[str]:
    """Collect SHAs of non-first parents that are not in the PR's own commit list.

    Used by contains_main_merge (precise check verified against origin/main).
    """
    own_shas: set[str] = set()
    for commit in commits:
        if not isinstance(commit, dict):
            continue
        own_sha = commit.get("sha")
        if isinstance(own_sha, str) and own_sha:
            own_shas.add(own_sha)
    shas: set[str] = set()
    for commit in commits:
        if not isinstance(commit, dict):
            continue
        parents = commit.get("parents")
        if not isinstance(parents, list) or len(parents) < 2:
            continue
        for parent in parents[1:]:
            if _is_external_parent(parent, own_shas):
                sha = parent.get("sha")
                if isinstance(sha, str) and sha:
                    shas.add(sha)
    return shas


def contains_main_merge(
    commits: list[Any], repo_root: Path, run_git: GitRunner | None = None
) -> bool:
    """True when the PR carries a merge of origin/main's direct trunk.

    The single shared predicate for the 40-commit-limit relief: a non-first
    parent of a merge commit in the PR must belong to origin/main's first-parent
    history. Merging a side branch that main has already landed does not qualify;
    merging origin/main (or an older commit on its trunk) does.

    This is the server-side counterpart of the pre-push hook's
    _contains_main_merge in git_hook_policy.py. Both callers call
    main_first_parent_shas to obtain the trunk frozenset, which is the one
    shared implementation.

    Fails closed (returns False) when git is unavailable or origin/main does
    not exist. Use main_merge_evidence when the caller needs to tell that case
    apart from an honest "this branch merges nothing on the trunk".
    """
    return main_merge_evidence(commits, repo_root, run_git).granted


@dataclass(frozen=True)
class ReliefEvidence:
    """Why the commit-limit relief was granted or withheld.

    ``granted`` is the decision. ``trunk_unreadable`` separates the two ways of
    withholding it: the branch merges nothing on origin/main's trunk, or the
    trunk could not be read at all. Both deny relief, but only the second is an
    infrastructure fault, and a gate that cannot say which one it hit sends an
    author to re-cut a branch that was never the problem.
    """

    granted: bool
    trunk_unreadable: bool


def main_merge_evidence(
    commits: list[Any], repo_root: Path, run_git: GitRunner | None = None
) -> ReliefEvidence:
    """Decide the relief and report whether the trunk was actually readable.

    One trunk read serves both answers, so asking for the diagnostic costs no
    extra git call. See contains_main_merge for the predicate's contract.
    """
    external_shas = _external_non_first_parent_shas(commits)
    if not external_shas:
        return ReliefEvidence(granted=False, trunk_unreadable=False)
    trunk = main_first_parent_shas(repo_root, run_git)
    if not trunk:
        return ReliefEvidence(granted=False, trunk_unreadable=True)
    return ReliefEvidence(granted=bool(external_shas & trunk), trunk_unreadable=False)


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
    evidence = main_merge_evidence(commits, Path.cwd())
    if evidence.trunk_unreadable:
        print(
            "::warning::Could not read origin/main's first-parent history, so the "
            "commit-limit relief was denied without being evaluated and this PR is "
            "held to the base ceiling. The checkout must populate "
            "refs/remotes/origin/main; pr-validation.yml pins fetch-depth: 0 for "
            "that reason (issue #3997)."
        )
    limit = MAIN_MERGE_BLOCK_THRESHOLD if evidence.granted else BLOCK_THRESHOLD
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
