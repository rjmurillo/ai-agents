#!/usr/bin/env python3
"""Resolve merge conflicts for a PR branch with auto-resolution support.

Features:
- Security validation for branch names and paths
- Auto-resolves conflicts in HANDOFF.md and session files
- Handles both GitHub Actions runner and local worktree environments
- Pushes resolved branch on success

EXIT CODES (ADR-035):
    0 - Success: No conflicts or conflicts auto-resolved
    1 - Error: Conflicts could not be auto-resolved or resolution failed
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

# Files that can be auto-resolved by accepting target branch (main) version
AUTO_RESOLVABLE_FILES = [
    ".agents/HANDOFF.md",
    ".agents/sessions/*",
    ".agents/*",
    ".serena/memories/*",
    ".serena/*",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    ".claude/skills/*",
    ".claude/skills/*/*",
    ".claude/skills/*/*/*",
    ".claude/commands/*",
    ".claude/agents/*",
    "templates/*",
    "templates/*/*",
    "templates/*/*/*",
    "src/copilot-cli/*",
    "src/vs-code-agents/*",
    "src/claude/*",
    ".github/agents/*",
    ".github/prompts/*",
]


def run_git(args: list[str], cwd: str | None = None) -> tuple[int, str]:
    """Run a git command and return (returncode, combined_output)."""
    try:
        result = subprocess.run(
            ["git"] + args,
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=60,
        )
        output = result.stdout.strip()
        if result.stderr.strip():
            output = (output + "\n" + result.stderr.strip()).strip()
        return result.returncode, output
    except FileNotFoundError:
        return -1, "git not found"
    except subprocess.TimeoutExpired:
        return -1, "git command timed out"


def is_safe_branch_name(branch_name: str) -> bool:
    """Validate branch name for command injection prevention (ADR-015)."""
    if not branch_name or not branch_name.strip():
        return False
    if branch_name.startswith("-"):
        return False
    if ".." in branch_name:
        return False
    if re.search(r"[\x00-\x1f\x7f]", branch_name):
        return False
    if re.search(r"[~^:?*\[\]\\]", branch_name):
        return False
    if re.search(r"[`$;&|<>(){}]", branch_name):
        return False
    return True


def get_safe_worktree_path(base_path: str, pr_number: int) -> str:
    """Get a validated worktree path (ADR-015 path traversal prevention)."""
    if pr_number <= 0:
        raise ValueError(f"Invalid PR number: {pr_number}")
    base = Path(base_path).resolve()
    worktree_name = f"ai-agents-pr-{pr_number}"
    worktree_path = base / worktree_name
    resolved = worktree_path.resolve()
    if not str(resolved).startswith(str(base)):
        raise ValueError(f"Worktree path escapes base directory: {worktree_path}")
    return str(resolved)


def get_repo_info() -> dict[str, str]:
    """Auto-detect repository owner and name from git remote."""
    returncode, output = run_git(["remote", "get-url", "origin"])
    if returncode != 0:
        raise RuntimeError("Not in a git repository or no origin remote")
    match = re.search(r"github\.com[:/]([^/]+)/([^/.]+)", output)
    if not match:
        raise RuntimeError(f"Could not parse GitHub repository from remote: {output}")
    return {
        "Owner": match.group(1),
        "Repo": re.sub(r"\.git$", "", match.group(2)),
    }


def is_github_runner() -> bool:
    """Detect if running in GitHub Actions."""
    return os.environ.get("GITHUB_ACTIONS") is not None


def is_auto_resolvable(file_path: str) -> bool:
    """Check if a file matches auto-resolvable patterns."""
    from fnmatch import fnmatch

    for pattern in AUTO_RESOLVABLE_FILES:
        if file_path == pattern or fnmatch(file_path, pattern):
            return True
    return False


def resolve_conflicts_in_checkout(
    branch_name: str,
    target_branch: str,
) -> dict:
    """Core merge + auto-resolve logic for a checked-out branch."""
    result = {
        "Success": False,
        "Message": "",
        "FilesResolved": [],
        "FilesBlocked": [],
    }

    returncode, _ = run_git(["merge", f"origin/{target_branch}"])
    if returncode == 0:
        return {
            "Success": True,
            "Message": "Merge completed without conflicts",
            "FilesResolved": [],
            "FilesBlocked": [],
        }

    returncode, conflicts_output = run_git(["diff", "--name-only", "--diff-filter=U"])
    if returncode != 0:
        result["Message"] = "Failed to list conflicted files"
        return result

    conflicts = [f for f in conflicts_output.splitlines() if f.strip()]
    can_auto_resolve = True

    for file_path in conflicts:
        if is_auto_resolvable(file_path):
            rc, _ = run_git(["checkout", "--theirs", file_path])
            if rc != 0:
                result["Message"] = f"Failed to checkout --theirs for {file_path}"
                return result
            rc, _ = run_git(["add", file_path])
            if rc != 0:
                result["Message"] = f"Failed to git add {file_path}"
                return result
            result["FilesResolved"].append(file_path)
        else:
            can_auto_resolve = False
            result["FilesBlocked"].append(file_path)

    if not can_auto_resolve:
        run_git(["merge", "--abort"])
        blocked = ", ".join(result["FilesBlocked"])
        result["Message"] = (
            f"Conflicts in non-auto-resolvable files: {blocked}"
        )
        return result

    rc, _ = run_git(["diff", "--cached", "--quiet"])
    if rc != 0:
        commit_msg = (
            f"Merge {target_branch} into {branch_name}"
            " - auto-resolve HANDOFF.md conflicts"
        )
        rc, _ = run_git(["commit", "-m", commit_msg])
        if rc != 0:
            result["Message"] = "Failed to commit merge"
            return result

    result["Success"] = True
    result["Message"] = "Conflicts auto-resolved"
    return result


def resolve_pr_conflicts(
    pr_number: int,
    branch_name: str,
    target_branch: str = "main",
    owner: str | None = None,
    repo: str | None = None,
    worktree_base_path: str = "..",
    dry_run: bool = False,
) -> dict:
    """Resolve merge conflicts for a PR branch."""
    result = {
        "Success": False,
        "Message": "",
        "FilesResolved": [],
        "FilesBlocked": [],
    }

    if not is_safe_branch_name(branch_name):
        result["Message"] = f"Rejecting PR #{pr_number} due to unsafe branch name: {branch_name}"
        return result

    if not is_safe_branch_name(target_branch):
        result["Message"] = (
            f"Rejecting PR #{pr_number} due to"
            f" unsafe target branch name: {target_branch}"
        )
        return result

    if dry_run:
        result["Success"] = True
        result["Message"] = f"[DryRun] Would resolve conflicts for PR #{pr_number}"
        return result

    if is_github_runner():
        return _resolve_github_runner(pr_number, branch_name, target_branch)

    return _resolve_local_worktree(pr_number, branch_name, target_branch, worktree_base_path)


def _resolve_github_runner(
    pr_number: int,
    branch_name: str,
    target_branch: str,
) -> dict:
    """Resolve conflicts in GitHub Actions runner mode."""
    result = {
        "Success": False,
        "Message": "",
        "FilesResolved": [],
        "FilesBlocked": [],
    }

    try:
        rc, _ = run_git(["fetch", "origin", branch_name])
        if rc != 0:
            raise RuntimeError(f"Failed to fetch branch {branch_name}")
        rc, _ = run_git(["fetch", "origin", target_branch])
        if rc != 0:
            raise RuntimeError(f"Failed to fetch target branch {target_branch}")
        rc, _ = run_git(["checkout", branch_name])
        if rc != 0:
            raise RuntimeError(f"Failed to checkout branch {branch_name}")

        merge_result = resolve_conflicts_in_checkout(branch_name, target_branch)
        if not merge_result["Success"]:
            return merge_result

        rc, push_output = run_git(["push", "origin", branch_name])
        if rc != 0:
            raise RuntimeError(f"Git push failed: {push_output}")

        return {
            "Success": True,
            "Message": f"Successfully resolved conflicts for PR #{pr_number}",
            "FilesResolved": merge_result["FilesResolved"],
            "FilesBlocked": [],
        }
    except RuntimeError as e:
        result["Message"] = f"Failed to resolve conflicts for PR #{pr_number}: {e}"
        return result


def _resolve_local_worktree(
    pr_number: int,
    branch_name: str,
    target_branch: str,
    worktree_base_path: str,
) -> dict:
    """Resolve conflicts using local worktree."""
    result = {
        "Success": False,
        "Message": "",
        "FilesResolved": [],
        "FilesBlocked": [],
    }

    rc, repo_root = run_git(["rev-parse", "--show-toplevel"])
    if rc != 0:
        result["Message"] = "Not in a git repository"
        return result

    try:
        worktree_path = get_safe_worktree_path(worktree_base_path, pr_number)
    except ValueError as e:
        result["Message"] = str(e)
        return result

    try:
        rc, _ = run_git(["worktree", "add", worktree_path, branch_name])
        if rc != 0:
            raise RuntimeError(f"Failed to create worktree for {branch_name}")

        rc, _ = run_git(["fetch", "origin", target_branch], cwd=worktree_path)
        if rc != 0:
            raise RuntimeError(f"Failed to fetch target branch {target_branch}")

        merge_result = resolve_conflicts_in_checkout(branch_name, target_branch)
        if not merge_result["Success"]:
            return merge_result

        rc, push_output = run_git(["push", "origin", branch_name], cwd=worktree_path)
        if rc != 0:
            raise RuntimeError(f"Git push failed: {push_output}")

        return {
            "Success": True,
            "Message": f"Successfully resolved conflicts for PR #{pr_number}",
            "FilesResolved": merge_result["FilesResolved"],
            "FilesBlocked": [],
        }
    except RuntimeError as e:
        result["Message"] = f"Failed to resolve conflicts for PR #{pr_number}: {e}"
        return result
    finally:
        if Path(worktree_path).exists():
            run_git(["-C", repo_root, "worktree", "remove", worktree_path, "--force"])


def main() -> int:
    """Entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Resolve merge conflicts for a PR branch")
    parser.add_argument("--pr-number", type=int, required=True, help="Pull request number")
    parser.add_argument("--branch-name", required=True, help="Branch name to resolve conflicts for")
    parser.add_argument("--target-branch", default="main", help="Target branch to merge from")
    parser.add_argument("--owner", help="Repository owner (auto-detected)")
    parser.add_argument("--repo", help="Repository name (auto-detected)")
    parser.add_argument("--worktree-base-path", default="..", help="Base path for worktrees")
    parser.add_argument("--dry-run", action="store_true", help="Dry run mode")
    args = parser.parse_args()

    owner = args.owner
    repo = args.repo
    if not owner or not repo:
        try:
            info = get_repo_info()
            owner = owner or info["Owner"]
            repo = repo or info["Repo"]
        except RuntimeError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1

    result = resolve_pr_conflicts(
        pr_number=args.pr_number,
        branch_name=args.branch_name,
        target_branch=args.target_branch,
        owner=owner,
        repo=repo,
        worktree_base_path=args.worktree_base_path,
        dry_run=args.dry_run,
    )

    print(json.dumps(result))
    return 0 if result["Success"] else 1


if __name__ == "__main__":
    sys.exit(main())
