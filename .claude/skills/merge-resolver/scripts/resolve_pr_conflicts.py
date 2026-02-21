#!/usr/bin/env python3
"""Resolve merge conflicts for a PR branch with auto-resolution support.

Extracted from Invoke-PRMaintenance to be reusable by merge-resolver skill.

Features:
- Security validation for branch names and paths (ADR-015)
- Auto-resolves conflicts in HANDOFF.md and session files
- Handles both GitHub Actions runner and local worktree environments
- Pushes resolved branch on success

Exit codes follow ADR-035:
    0 - Success: No conflicts or conflicts auto-resolved
    1 - Error: Conflicts could not be auto-resolved or resolution failed
    3 - External error (git command failure)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class RepoInfo:
    """Structured repository information from git remote.

    Frozen dataclass enforces immutability and enables type-safe attribute access.
    """

    owner: str
    repo: str


# Files that can be auto-resolved by accepting target branch (main) version.
# These are typically auto-generated or frequently-updated files where
# the main branch version is authoritative.
AUTO_RESOLVABLE_PATTERNS: list[str] = [
    # Session artifacts - constantly changing, main is authoritative
    ".agents/HANDOFF.md",
    ".agents/sessions/*",
    ".agents/*",
    # Serena memories - auto-generated, main is authoritative
    ".serena/memories/*",
    ".serena/*",
    # Lock files - should match main
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    # Skill definitions - main is authoritative
    ".claude/skills/*",
    ".claude/skills/*/*",
    ".claude/skills/*/*/*",
    ".claude/commands/*",
    ".claude/agents/*",
    # Template files - main is authoritative (include subdirectories)
    "templates/*",
    "templates/*/*",
    "templates/*/*/*",
    # Platform-specific agent definitions - main is authoritative
    "src/copilot-cli/*",
    "src/vs-code-agents/*",
    "src/claude/*",
    # GitHub configs - main is authoritative
    ".github/agents/*",
    ".github/prompts/*",
]

# Security patterns for branch name validation (ADR-015)
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f]")
_GIT_SPECIAL_RE = re.compile(r"[~^:?*\[\]\\]")
_SHELL_META_RE = re.compile(r"[`$;&|<>(){}]")


def is_safe_branch_name(branch_name: str) -> bool:
    """Validate branch name for command injection prevention (ADR-015)."""
    if not branch_name or branch_name.isspace():
        return False
    if branch_name.startswith("-"):
        return False
    if ".." in branch_name:
        return False
    if _CONTROL_CHARS_RE.search(branch_name):
        return False
    if _GIT_SPECIAL_RE.search(branch_name):
        return False
    if _SHELL_META_RE.search(branch_name):
        return False
    return True


def get_safe_worktree_path(base_path: str, pr_number: int) -> str:
    """Get a validated worktree path that cannot escape the base directory (ADR-015)."""
    if pr_number <= 0:
        raise ValueError(f"Invalid PR number: {pr_number}")

    base = Path(base_path).resolve()
    if not base.exists():
        raise FileNotFoundError(f"Base path does not exist: {base_path}")

    try:
        repo_info = get_repo_info()
        repo_name = repo_info.repo
    except RuntimeError:
        repo_name = "plugin"
    worktree_name = f"{repo_name}-pr-{pr_number}"
    worktree_path = (base / worktree_name).resolve()

    # Verify path stays within base directory
    try:
        worktree_path.relative_to(base)
    except ValueError as exc:
        raise ValueError(f"Worktree path escapes base directory: {worktree_path}") from exc

    return str(worktree_path)


def get_repo_info() -> RepoInfo:
    """Auto-detect owner/repo from git remote."""
    result = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError("Not in a git repository or no origin remote")

    remote = result.stdout.strip()
    match = re.search(r"github\.com[:/]([^/]+)/([^/.]+)", remote)
    if not match:
        raise RuntimeError(f"Could not parse GitHub repository from remote: {remote}")

    return RepoInfo(
        owner=match.group(1),
        repo=match.group(2).removesuffix(".git"),
    )


def is_github_runner() -> bool:
    """Check if running in GitHub Actions."""
    return os.environ.get("GITHUB_ACTIONS") is not None


def is_auto_resolvable(file_path: str) -> bool:
    """Check if a file matches auto-resolvable patterns."""
    for pattern in AUTO_RESOLVABLE_PATTERNS:
        if file_path == pattern or fnmatch(file_path, pattern):
            return True
    return False


def _run_git(*args: str, cwd: str | None = None) -> subprocess.CompletedProcess[str]:
    """Run a git command and return the result."""
    return subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        cwd=cwd,
    )


def resolve_conflicts_runner(
    branch_name: str,
    target_branch: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Resolve conflicts in GitHub Actions runner mode (no worktree)."""
    result: dict[str, Any] = {
        "success": False,
        "message": "",
        "files_resolved": [],
        "files_blocked": [],
    }

    if dry_run:
        result["message"] = (
            f"[DryRun] Would resolve conflicts for branch {branch_name} in GitHub runner mode"
        )
        result["success"] = True
        return result

    # Fetch PR branch and target branch
    r = _run_git("fetch", "origin", branch_name)
    if r.returncode != 0:
        result["message"] = f"Failed to fetch branch {branch_name}"
        return result

    r = _run_git("fetch", "origin", target_branch)
    if r.returncode != 0:
        result["message"] = f"Failed to fetch target branch {target_branch}"
        return result

    # Checkout PR branch
    r = _run_git("checkout", branch_name)
    if r.returncode != 0:
        result["message"] = f"Failed to checkout branch {branch_name}"
        return result

    # Attempt merge with target branch
    r = _run_git("merge", f"origin/{target_branch}")

    if r.returncode != 0:
        # Get conflicted files
        conflicts_r = _run_git("diff", "--name-only", "--diff-filter=U")
        conflicts = [f for f in conflicts_r.stdout.strip().split("\n") if f]

        can_auto_resolve = True
        for file_path in conflicts:
            if is_auto_resolvable(file_path):
                checkout_r = _run_git("checkout", "--theirs", file_path)
                if checkout_r.returncode != 0:
                    result["message"] = f"Failed to checkout --theirs for {file_path}"
                    return result
                add_r = _run_git("add", file_path)
                if add_r.returncode != 0:
                    result["message"] = f"Failed to git add {file_path}"
                    return result
                result["files_resolved"].append(file_path)
            else:
                can_auto_resolve = False
                result["files_blocked"].append(file_path)

        if not can_auto_resolve:
            _run_git("merge", "--abort")
            blocked = ", ".join(result["files_blocked"])
            result["message"] = f"Conflicts in non-auto-resolvable files: {blocked}"
            return result

        # Check if there are staged changes to commit
        diff_r = _run_git("diff", "--cached", "--quiet")
        if diff_r.returncode != 0:
            commit_msg = (
                f"Merge {target_branch} into {branch_name} - auto-resolve HANDOFF.md conflicts"
            )
            commit_r = _run_git("commit", "-m", commit_msg)
            if commit_r.returncode != 0:
                result["message"] = "Failed to commit merge"
                return result

    # Push
    push_r = _run_git("push", "origin", branch_name)
    if push_r.returncode != 0:
        result["message"] = f"Git push failed: {push_r.stderr}"
        return result

    result["success"] = True
    result["message"] = f"Successfully resolved conflicts for branch {branch_name}"
    return result


def resolve_conflicts_worktree(
    branch_name: str,
    target_branch: str,
    pr_number: int,
    worktree_base_path: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Resolve conflicts using a local worktree for isolation."""
    result: dict[str, Any] = {
        "success": False,
        "message": "",
        "files_resolved": [],
        "files_blocked": [],
    }

    repo_root_r = _run_git("rev-parse", "--show-toplevel")
    repo_root = repo_root_r.stdout.strip()

    try:
        worktree_path = get_safe_worktree_path(worktree_base_path, pr_number)
    except (ValueError, FileNotFoundError) as exc:
        result["message"] = f"Failed to get safe worktree path for PR #{pr_number}: {exc}"
        return result

    if dry_run:
        result["message"] = (
            f"[DryRun] Would create worktree at {worktree_path} "
            f"and resolve conflicts for PR #{pr_number}"
        )
        result["success"] = True
        return result

    try:
        # Create worktree
        r = _run_git("worktree", "add", worktree_path, branch_name)
        if r.returncode != 0:
            result["message"] = f"Failed to create worktree for {branch_name}"
            return result

        # Fetch and merge target branch
        r = _run_git("fetch", "origin", target_branch, cwd=worktree_path)
        if r.returncode != 0:
            result["message"] = f"Failed to fetch target branch {target_branch}"
            return result

        r = _run_git("merge", f"origin/{target_branch}", cwd=worktree_path)

        if r.returncode != 0:
            conflicts_r = _run_git(
                "diff",
                "--name-only",
                "--diff-filter=U",
                cwd=worktree_path,
            )
            conflicts = [f for f in conflicts_r.stdout.strip().split("\n") if f]

            can_auto_resolve = True
            for file_path in conflicts:
                if is_auto_resolvable(file_path):
                    checkout_r = _run_git(
                        "checkout",
                        "--theirs",
                        file_path,
                        cwd=worktree_path,
                    )
                    if checkout_r.returncode != 0:
                        result["message"] = f"Failed to checkout --theirs for {file_path}"
                        return result
                    add_r = _run_git("add", file_path, cwd=worktree_path)
                    if add_r.returncode != 0:
                        result["message"] = f"Failed to git add {file_path}"
                        return result
                    result["files_resolved"].append(file_path)
                else:
                    can_auto_resolve = False
                    result["files_blocked"].append(file_path)

            if not can_auto_resolve:
                _run_git("merge", "--abort", cwd=worktree_path)
                blocked = ", ".join(result["files_blocked"])
                result["message"] = f"Conflicts in non-auto-resolvable files: {blocked}"
                return result

            diff_r = _run_git("diff", "--cached", "--quiet", cwd=worktree_path)
            if diff_r.returncode != 0:
                commit_msg = (
                    f"Merge {target_branch} into {branch_name} - auto-resolve HANDOFF.md conflicts"
                )
                commit_r = _run_git("commit", "-m", commit_msg, cwd=worktree_path)
                if commit_r.returncode != 0:
                    result["message"] = "Failed to commit merge"
                    return result

        push_r = _run_git("push", "origin", branch_name, cwd=worktree_path)
        if push_r.returncode != 0:
            result["message"] = f"Git push failed: {push_r.stderr}"
            return result

        result["success"] = True
        result["message"] = f"Successfully resolved conflicts for PR #{pr_number}"
        return result

    except Exception as exc:
        result["message"] = f"Failed to resolve conflicts for PR #{pr_number}: {exc}"
        return result
    finally:
        # Clean up worktree
        if Path(worktree_path).exists():
            _run_git(
                "-C",
                repo_root,
                "worktree",
                "remove",
                worktree_path,
                "--force",
            )


def resolve_pr_conflicts(
    pr_number: int,
    branch_name: str,
    target_branch: str = "main",
    worktree_base_path: str = "..",
    owner: str = "",
    repo: str = "",
    dry_run: bool = False,
) -> dict[str, Any]:
    """Main entry point for conflict resolution."""
    # Validate branch names (ADR-015)
    if not is_safe_branch_name(branch_name):
        return {
            "success": False,
            "message": (f"Rejecting PR #{pr_number} due to unsafe branch name: {branch_name}"),
            "files_resolved": [],
            "files_blocked": [],
        }

    if not is_safe_branch_name(target_branch):
        return {
            "success": False,
            "message": (f"Rejecting PR #{pr_number} due to unsafe target branch: {target_branch}"),
            "files_resolved": [],
            "files_blocked": [],
        }

    if is_github_runner():
        return resolve_conflicts_runner(branch_name, target_branch, dry_run)

    return resolve_conflicts_worktree(
        branch_name,
        target_branch,
        pr_number,
        worktree_base_path,
        dry_run,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Resolve merge conflicts for a PR branch with auto-resolution.",
    )
    parser.add_argument("--owner", default="", help="Repository owner")
    parser.add_argument("--repo", default="", help="Repository name")
    parser.add_argument(
        "--pr-number",
        type=int,
        required=True,
        help="Pull request number",
    )
    parser.add_argument(
        "--branch-name",
        required=True,
        help="Branch name (headRefName)",
    )
    parser.add_argument(
        "--target-branch",
        default="main",
        help="Target branch (baseRefName)",
    )
    parser.add_argument(
        "--worktree-base-path",
        default="..",
        help="Base path for worktrees when running locally",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without acting",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    owner = args.owner
    repo = args.repo
    if not owner or not repo:
        try:
            info = get_repo_info()
            owner = owner or info.owner
            repo = repo or info.repo
        except RuntimeError as exc:
            print(json.dumps({"success": False, "message": str(exc)}))
            return 1

    result = resolve_pr_conflicts(
        pr_number=args.pr_number,
        branch_name=args.branch_name,
        target_branch=args.target_branch,
        worktree_base_path=args.worktree_base_path,
        owner=owner,
        repo=repo,
        dry_run=args.dry_run,
    )

    print(json.dumps(result))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
