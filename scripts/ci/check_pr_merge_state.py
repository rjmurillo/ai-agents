#!/usr/bin/env python3
"""Fail loud when a pushed branch has an open PR that cannot merge."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass

EXIT_OK = 0
EXIT_REGRESSION = 1
EXIT_CONFIG = 2
EXIT_EXTERNAL = 3

PASS_STATES = {"CLEAN", "HAS_HOOKS", "UNSTABLE"}
FAIL_STATES = {"BEHIND", "BLOCKED", "DIRTY"}


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
                "number,title,url,mergeStateStatus,headRefName,baseRefName",
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
    prs: list[PullRequest] = []
    for item in payload:
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


def check_prs(prs: Sequence[PullRequest]) -> int:
    if not prs:
        print("PR merge state: no open PR for this branch.")
        return EXIT_OK

    blocked = [pr for pr in prs if pr.merge_state_status in FAIL_STATES]
    unknown = [pr for pr in prs if pr.merge_state_status not in PASS_STATES | FAIL_STATES]
    if blocked:
        for pr in blocked:
            print(
                f"::error::PR #{pr.number} mergeStateStatus={pr.merge_state_status}. "
                "Pull request workflows may be unreachable while this state persists. "
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

    rc, prs = load_open_prs(args.repo, args.head_ref)
    if rc != EXIT_OK:
        return rc
    return check_prs(prs)


if __name__ == "__main__":
    raise SystemExit(main())
