#!/usr/bin/env python3
"""Fail loud when a pushed branch has an open PR that cannot merge."""

from __future__ import annotations

import argparse
import json
import os
import random
import subprocess
import sys
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

EXIT_OK = 0
EXIT_REGRESSION = 1
EXIT_CONFIG = 2
EXIT_EXTERNAL = 3

# This script answers "can this PR still reach a merge?", so BEHIND and BLOCKED
# pass: both are repairable without a force-push or a conflict resolution.
# `_SUPPORTED_MERGE_STATES` in the `github` skill's `test_pr_merge_ready.py`
# answers the narrower "can pr-autofix merge it right now?", so it holds only
# CLEAN, HAS_HOOKS, and UNSTABLE. The two sets differ by question, not by
# disagreement about the enum: both read HAS_HOOKS as mergeable, per GitHub's
# GraphQL MergeStateStatus reference ("Mergeable with passing commit status and
# pre-receive hooks").
PASS_STATES = {"BEHIND", "BLOCKED", "CLEAN", "HAS_HOOKS", "UNSTABLE"}
FAIL_STATES = {"DIRTY"}

RETRY_DELAY_MIN_SECONDS = 10
RETRY_DELAY_MAX_SECONDS = 20


@dataclass(frozen=True, slots=True)
class PullRequest:
    number: int
    title: str
    url: str
    merge_state_status: str
    head_ref_name: str
    base_ref_name: str


def run_gh(argv: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["gh", *argv],
        capture_output=True,
        text=True,
        errors="replace",
        encoding="utf-8",
        check=False,
    )


def load_open_prs(repo: str, head_ref: str) -> tuple[int, list[PullRequest]]:
    try:
        proc = run_gh(
            [
                "pr",
                "list",
                "--repo",
                repo,
                "--state",
                "open",
                "--head",
                head_ref,
                "--json",
                # `mergeable` is requested and never parsed, on purpose. GitHub
                # computes mergeability lazily and asking for mergeStateStatus
                # alone does not trigger that computation, so a query without
                # `mergeable` can report UNKNOWN indefinitely and no amount of
                # retrying converges. Measured on this repository: 46 open PRs
                # read seconds apart returned UNKNOWN=40 without the field and a
                # decided verdict for all 46 with it. See
                # .serena/memories/ci/ci-mergeability-is-not-computed-until-you-ask.md
                "number,title,url,mergeable,mergeStateStatus,headRefName,baseRefName",
            ]
        )
    except (FileNotFoundError, OSError) as exc:
        print(f"error: gh could not be launched: {exc}", file=sys.stderr)
        return EXIT_EXTERNAL, []
    if proc.returncode != 0:
        print(proc.stderr or proc.stdout, file=sys.stderr)
        return EXIT_EXTERNAL, []
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        print(f"error: gh emitted invalid JSON: {exc}", file=sys.stderr)
        return EXIT_EXTERNAL, []
    if not isinstance(payload, list):
        print("error: gh emitted JSON that was not a PR list", file=sys.stderr)
        return EXIT_EXTERNAL, []
    prs: list[PullRequest] = []
    for item in payload:
        if not isinstance(item, Mapping):
            print("error: gh emitted a malformed PR item", file=sys.stderr)
            return EXIT_EXTERNAL, []
        prs.append(
            PullRequest(
                number=int(item["number"]),
                title=str(item.get("title") or ""),
                url=str(item.get("url") or ""),
                merge_state_status=str(item.get("mergeStateStatus") or "UNKNOWN"),
                head_ref_name=str(item.get("headRefName") or ""),
                base_ref_name=str(item.get("baseRefName") or ""),
            )
        )
    return EXIT_OK, prs


def has_no_verdict(merge_state_status: str) -> bool:
    """True when GitHub gave no authoritative merge verdict for this status.

    UNKNOWN is what GitHub reports while mergeability is still being computed,
    but it is not the only status outside the decided sets: an unlisted or
    newly-added status lands here too. check_prs and load_open_prs_with_retry
    share this predicate so that every status which can fail the run is also a
    status the retry will wait on. A stricter retry predicate would let an
    unlisted status skip the wait and still exit 3.
    """
    return merge_state_status not in PASS_STATES | FAIL_STATES


def load_open_prs_with_retry(
    repo: str, head_ref: str, max_attempts: int = 3
) -> tuple[int, list[PullRequest]]:
    """Load open PRs, re-reading while GitHub reports no merge verdict yet.

    GitHub computes mergeability lazily, so the first read after a push can
    come back without a verdict. This makes up to max_attempts reads, sleeping
    a random RETRY_DELAY_MIN_SECONDS to RETRY_DELAY_MAX_SECONDS between them,
    and never sleeps after the final read.

    Returns whatever load_open_prs last returned: an early non-EXIT_OK on a gh
    failure, or EXIT_OK with the PR list from the last read, a verdict-less
    merge state included if every read stayed that way. Deciding whether a
    missing verdict should fail the run is check_prs's job, not this one's.

    Raises ValueError when max_attempts is not an integer of 1 or more. A zero
    or negative budget previously skipped the loop and then read unassigned
    locals; a non-integer raised out of range().

    Canonical bound, scripts/validate_pr_review_config.py:284-290, quoted:

        retries = il.get("completion_gate_max_retries")
        if retries is not None and (
            not isinstance(retries, int) or isinstance(retries, bool) or retries < 0
        ):
            errors.append(
                "invocation_limits.completion_gate_max_retries must be an integer >= 0"
            )

    Stricter than canonical: the floor here is 1, not 0, because this counts
    attempts rather than retries and zero attempts reads nothing. The bool
    exclusion is carried over unchanged, so max_attempts=True is rejected rather
    than silently meaning one attempt.
    """
    if not isinstance(max_attempts, int) or isinstance(max_attempts, bool) or max_attempts < 1:
        raise ValueError(f"max_attempts must be an integer >= 1, got {max_attempts!r}")

    rc, prs = load_open_prs(repo, head_ref)
    for _ in range(max_attempts - 1):
        if rc != EXIT_OK or not any(has_no_verdict(pr.merge_state_status) for pr in prs):
            return rc, prs
        time.sleep(random.randint(RETRY_DELAY_MIN_SECONDS, RETRY_DELAY_MAX_SECONDS))
        rc, prs = load_open_prs(repo, head_ref)
    return rc, prs


def check_prs(prs: Sequence[PullRequest]) -> int:
    if not prs:
        print("PR merge state: no open PR for this branch.")
        return EXIT_OK

    blocked = [pr for pr in prs if pr.merge_state_status in FAIL_STATES]
    unknown = [pr for pr in prs if has_no_verdict(pr.merge_state_status)]
    if blocked:
        for pr in blocked:
            print(
                f"::error::PR #{pr.number} mergeStateStatus={pr.merge_state_status}. "
                "Pull request workflows are unreachable while this conflict persists. "
                f"Merge or rebase {pr.head_ref_name} onto {pr.base_ref_name}."
            )
            print(f"::error::{pr.url}")
        return EXIT_REGRESSION
    if unknown:
        for pr in unknown:
            print(
                f"::error::PR #{pr.number} mergeStateStatus={pr.merge_state_status}. "
                "GitHub did not provide an authoritative merge verdict."
            )
            print(f"::error::{pr.url}")
        return EXIT_EXTERNAL

    for pr in prs:
        print(f"PR #{pr.number} merge state OK: {pr.merge_state_status}.")
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Detect open PRs whose merge state makes PR validation unreachable."
    )
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument("--head-ref", default=os.environ.get("GITHUB_REF_NAME", ""))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.repo:
        print("error: --repo or GITHUB_REPOSITORY is required", file=sys.stderr)
        return EXIT_CONFIG
    if not args.head_ref:
        print("error: --head-ref or GITHUB_REF_NAME is required", file=sys.stderr)
        return EXIT_CONFIG

    rc, prs = load_open_prs_with_retry(args.repo, args.head_ref)
    if rc != EXIT_OK:
        return rc
    return check_prs(prs)


if __name__ == "__main__":
    raise SystemExit(main())
