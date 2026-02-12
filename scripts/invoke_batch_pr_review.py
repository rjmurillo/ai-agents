#!/usr/bin/env python3
"""Manage git worktrees for batch PR review operations.

Creates, monitors, and cleans up git worktrees for parallel PR review processing.

EXIT CODES:
  0  - Success: Worktree operation completed
  1  - Error: Operation failed

See: ADR-035 Exit Code Standardization
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


def run_git(*args: str, cwd: str | Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        cwd=cwd,
    )


def run_gh(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["gh", *args],
        capture_output=True,
        text=True,
    )


def get_pr_branch(pr_number: int) -> str | None:
    result = run_gh("pr", "view", str(pr_number), "--json", "headRefName")
    if result.returncode != 0:
        print(f"WARNING: PR #{pr_number} not found or not accessible.")
        return None
    try:
        data = json.loads(result.stdout)
        branch: str | None = data.get("headRefName")
        return branch
    except (json.JSONDecodeError, KeyError):
        print(f"WARNING: PR #{pr_number}: Unable to parse branch information.")
        return None


def create_worktree(pr_number: int, worktree_root: Path) -> bool:
    branch = get_pr_branch(pr_number)
    if not branch:
        return False

    worktree_path = worktree_root / f"worktree-pr-{pr_number}"
    if worktree_path.exists():
        print(f"Worktree already exists: {worktree_path}")
        return True

    print(f"PR #{pr_number}: Fetching branch '{branch}' from origin...")
    run_git("fetch", "origin", f"{branch}:{branch}")

    result = run_git("worktree", "add", str(worktree_path), branch)
    if result.returncode != 0:
        print(f"PR #{pr_number}: Retrying with origin/{branch}...")
        result = run_git("worktree", "add", str(worktree_path), f"origin/{branch}")
        if result.returncode != 0:
            print(f"WARNING: Failed to create worktree for PR #{pr_number}.")
            return False

    print(f"Created: {worktree_path}")
    return True


@dataclass
class WorktreeStatus:
    pr: int
    path: Path
    exists: bool
    clean: bool | None = None
    branch: str | None = None
    commit: str | None = None
    unpushed: bool | None = None


def get_worktree_status(pr_number: int, worktree_root: Path) -> WorktreeStatus:
    worktree_path = worktree_root / f"worktree-pr-{pr_number}"
    if not worktree_path.exists():
        return WorktreeStatus(pr=pr_number, path=worktree_path, exists=False)

    status_result = run_git("status", "--short", cwd=worktree_path)
    branch_result = run_git("branch", "--show-current", cwd=worktree_path)
    commit_result = run_git("log", "-1", "--format=%h", cwd=worktree_path)

    clean = not status_result.stdout.strip() if status_result.returncode == 0 else None
    branch = branch_result.stdout.strip() if branch_result.returncode == 0 else None
    commit = commit_result.stdout.strip() if commit_result.returncode == 0 else None

    upstream_result = run_git("rev-parse", "--abbrev-ref", "@{u}", cwd=worktree_path)
    unpushed = None
    if upstream_result.returncode == 0:
        log_result = run_git("log", "@{u}..", "--oneline", cwd=worktree_path)
        unpushed = bool(log_result.stdout.strip())

    return WorktreeStatus(
        pr=pr_number,
        path=worktree_path,
        exists=True,
        clean=clean,
        branch=branch,
        commit=commit,
        unpushed=unpushed,
    )


def remove_worktree(pr_number: int, worktree_root: Path, force: bool = False) -> bool:
    status = get_worktree_status(pr_number, worktree_root)
    if not status.exists:
        print(f"Worktree for PR #{pr_number} does not exist")
        return True

    if not status.clean and not force:
        print(f"WARNING: Worktree for PR #{pr_number} has uncommitted changes. Use --force.")
        return False

    if status.unpushed and not force:
        print(f"WARNING: Worktree for PR #{pr_number} has unpushed commits. Use --force.")
        return False

    print(f"Removing worktree for PR #{pr_number}...")
    args = ["worktree", "remove", str(status.path)]
    if force:
        args.append("--force")
    result = run_git(*args)

    if result.returncode != 0:
        print(f"WARNING: Failed to remove worktree for PR #{pr_number}.")
        return False

    print(f"Removed: {status.path}")
    return True


def push_worktree_changes(pr_number: int, worktree_root: Path) -> bool:
    status = get_worktree_status(pr_number, worktree_root)
    if not status.exists:
        print(f"WARNING: Worktree for PR #{pr_number} does not exist")
        return False

    if status.clean and not status.unpushed:
        print(f"PR #{pr_number}: Already clean and pushed")
        return True

    cwd = status.path
    if not status.clean:
        print(f"PR #{pr_number}: Committing changes...")
        result = run_git("add", ".", cwd=cwd)
        if result.returncode != 0:
            print(f"WARNING: PR #{pr_number}: 'git add .' failed")
            return False
        msg = f"chore(pr-{pr_number}): finalize review response session"
        result = run_git("commit", "-m", msg, cwd=cwd)
        if result.returncode != 0:
            print(f"WARNING: PR #{pr_number}: 'git commit' failed")
            return False

    if status.unpushed or not status.clean:
        print(f"PR #{pr_number}: Pushing to remote...")
        result = run_git("push", cwd=cwd)
        if result.returncode != 0:
            print(f"WARNING: PR #{pr_number}: 'git push' failed")
            return False

    print(f"PR #{pr_number}: Synced")
    return True


def print_status_table(statuses: list[WorktreeStatus]) -> None:
    print(f"{'PR':<8} {'Exists':<8} {'Clean':<8} {'Branch':<30} {'Commit':<10} {'Unpushed'}")
    print("-" * 80)
    for s in statuses:
        print(
            f"{s.pr:<8} {str(s.exists):<8} {str(s.clean):<8} "
            f"{str(s.branch or ''):<30} {str(s.commit or ''):<10} {str(s.unpushed or '')}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manage git worktrees for batch PR review")
    parser.add_argument(
        "--pr-numbers", type=int, nargs="+", required=True, help="PR numbers to process",
    )
    parser.add_argument(
        "--operation",
        choices=["setup", "status", "cleanup", "all"],
        required=True,
        help="Operation to perform",
    )
    parser.add_argument("--worktree-root", type=Path, help="Root directory for worktrees")
    parser.add_argument("--force", action="store_true", help="Force cleanup of dirty worktrees")
    args = parser.parse_args(argv)

    if not args.worktree_root:
        result = run_git("rev-parse", "--show-toplevel")
        if result.returncode != 0:
            print("ERROR: Not in a git repository", file=sys.stderr)
            return 1
        args.worktree_root = Path(result.stdout.strip()).parent

    op = args.operation

    if op in ("setup", "all"):
        pr_list = ", ".join(str(p) for p in args.pr_numbers)
        print(f"\n=== Setting up worktrees for PRs: {pr_list} ===")
        for pr in args.pr_numbers:
            create_worktree(pr, args.worktree_root)

    if op in ("status", "all"):
        print("\n=== Worktree Status ===")
        statuses = [get_worktree_status(pr, args.worktree_root) for pr in args.pr_numbers]
        print_status_table(statuses)

    if op == "cleanup":
        print("\n=== Cleaning up worktrees ===")
        for pr in args.pr_numbers:
            push_worktree_changes(pr, args.worktree_root)
        for pr in args.pr_numbers:
            remove_worktree(pr, args.worktree_root, force=args.force)
        print("\n=== Remaining worktrees ===")
        result = run_git("worktree", "list")
        if result.stdout:
            print(result.stdout)

    if op == "all":
        print("\n=== Ready for parallel PR review ===")
        print(f"Worktrees created at: {args.worktree_root}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
