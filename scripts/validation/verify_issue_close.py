#!/usr/bin/env python3
"""Verify resolution claims before an automated issue close (issue #2481).

The auto-close pipeline closed issues with "resolved by commit X" or "via PR #N"
claims that were false on ``main`` (audit 2026-06-06 confirmed #134, #139, #702,
#907). This module gates a close on the truth of any commit or PR it cites: a
cited commit must exist in the local history, and a cited PR must be MERGED. A
close whose rationale cites neither is allowed (the close reason is not a
resolution claim, for example "stale" or "superseded").

Scope: this is the citation-truth gate. It does NOT assert that a named
deliverable is present on ``main`` (that case is fuzzier and tracked separately).
The epic-auto-close guard lives at the executor's mutation point in
``scripts/triage_batch_apply.py``.

Used two ways:
    1. As a library by ``scripts/triage_batch_apply.py`` (pure extraction plus
       injected checker callables, so the executor verifies through its existing
       gateway boundary and stays testable).
    2. As a CLI to spot-check a rationale string before posting a close comment.

Exit codes follow ADR-035:
    0 - Success (all cited commits/PRs verified, or none cited)
    1 - Logic error (one or more cited commits/PRs could not be verified)
    2 - Config error (bad arguments)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections.abc import Callable

# A commit citation: the word "commit" followed by a 7-to-40 char hex SHA, or a
# bare full 40-char SHA. Case-insensitive; abbreviated SHAs are accepted because
# bot close comments often cite the short form.
_COMMIT_NEAR_KEYWORD = re.compile(r"(?i)\bcommit\s+([0-9a-f]{7,40})\b")
_FULL_SHA = re.compile(r"(?i)\b([0-9a-f]{40})\b")

# A PR resolution citation: the literal token "PR" followed by an optional "#"
# and the number. A bare "#123" is deliberately NOT treated as a PR-merged claim,
# because it is commonly a supersession or related-issue reference, not an
# assertion that a PR merged.
_PR_CITATION = re.compile(r"(?i)\bPR\s*#?(\d+)\b")

# Bounded timeout for every subprocess call (Release It! integration-point rule).
_TIMEOUT = 30.0

CommitChecker = Callable[[str], bool]
PrChecker = Callable[[int], bool]


def extract_commit_shas(text: str) -> list[str]:
    """Return the lowercased commit SHAs cited as a resolution in ``text``.

    Order-preserving and deduplicated. Matches "commit <sha>" (7-40 hex) and any
    bare full 40-char SHA.
    """

    found: list[str] = []
    seen: set[str] = set()
    for match in _COMMIT_NEAR_KEYWORD.finditer(text):
        sha = match.group(1).lower()
        if sha not in seen:
            seen.add(sha)
            found.append(sha)
    for match in _FULL_SHA.finditer(text):
        sha = match.group(1).lower()
        if sha not in seen:
            seen.add(sha)
            found.append(sha)
    return found


def extract_pr_numbers(text: str) -> list[int]:
    """Return the PR numbers cited as a resolution ("PR #N") in ``text``.

    Order-preserving and deduplicated. A bare "#N" without the "PR" token is
    ignored on purpose to avoid blocking supersession or related-issue closes.
    """

    found: list[int] = []
    seen: set[int] = set()
    for match in _PR_CITATION.finditer(text):
        number = int(match.group(1))
        if number not in seen:
            seen.add(number)
            found.append(number)
    return found


def unverified_claims(
    rationale: str,
    *,
    commit_exists: CommitChecker,
    pr_is_merged: PrChecker,
) -> list[str]:
    """Return human-readable labels for each cited commit/PR that did not verify.

    Pure orchestration: the caller injects ``commit_exists`` and ``pr_is_merged``
    so the same logic runs against a real repo (CLI) or a fake (executor tests).
    An empty list means the close is safe with respect to its citations.
    """

    bad: list[str] = []
    for sha in extract_commit_shas(rationale):
        if not commit_exists(sha):
            bad.append(f"commit {sha}")
    for pr in extract_pr_numbers(rationale):
        if not pr_is_merged(pr):
            bad.append(f"PR #{pr}")
    return bad


def verify_commit_exists(
    sha: str,
    *,
    repo: str = "",
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> bool:
    """Return True if ``sha`` resolves to a commit.

    When repo context is available, verifies against GitHub's commit API so a
    shallow CI checkout does not reject valid commits that are not local. Without
    repo context, falls back to ``git cat-file -e <sha>^{commit}``.
    """

    if repo:
        try:
            result = runner(
                ["gh", "api", f"repos/{repo}/commits/{sha}"],
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                timeout=_TIMEOUT,
            )
        except (OSError, subprocess.SubprocessError):
            return False
        return result.returncode == 0

    try:
        result = runner(
            ["git", "cat-file", "-e", f"{sha}^{{commit}}"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            env=dict(os.environ, LC_ALL="C"),
            check=False,
            timeout=_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def verify_pr_merged(
    pr: int,
    repo: str,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> bool:
    """Return True if PR ``pr`` in ``repo`` is in the MERGED state per gh.

    A closed-unmerged PR returns False: citing it as a resolution is also a false
    claim. Any gh failure yields False.
    """

    try:
        result = runner(
            ["gh", "pr", "view", str(pr), "--repo", repo, "--json", "state"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    if result.returncode != 0:
        return False
    try:
        data = json.loads(result.stdout)
    except (json.JSONDecodeError, ValueError):
        return False
    if not isinstance(data, dict):
        return False
    raw_state = data.get("state")
    state = "" if raw_state is None else str(raw_state)
    return state.upper() == "MERGED"


def _cli_unverified(rationale: str, repo: str) -> list[str]:
    """CLI helper: verify a rationale against the real git history and gh."""

    return unverified_claims(
        rationale,
        commit_exists=lambda sha: verify_commit_exists(sha, repo=repo),
        pr_is_merged=lambda pr: verify_pr_merged(pr, repo),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify commit/PR resolution claims before an issue close.",
    )
    parser.add_argument(
        "--rationale", required=True,
        help="The close rationale text to scan for commit/PR resolution claims.",
    )
    parser.add_argument(
        "--repo", default="",
        help=(
            "owner/repo for PR and remote commit verification "
            "(required only if the rationale cites a PR)."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if extract_pr_numbers(args.rationale) and not args.repo:
        print("error: --repo is required when the rationale cites a PR", file=sys.stderr)
        return 2
    bad = _cli_unverified(args.rationale, args.repo)
    if bad:
        print(f"UNVERIFIED close claim(s): {', '.join(bad)}", file=sys.stderr)
        return 1
    print("OK: all cited commits/PRs verified (or none cited)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
