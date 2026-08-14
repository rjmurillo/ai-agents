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
    2 - Config error (no candidate plugin lib directory carries github_core)
    3 - External error (git command failure)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

# The package this script imports out of a plugin's ``lib`` directory. Its
# presence is what tells this plugin's lib apart from a foreign plugin's lib
# that merely exists. Used by _resolve_lib_dir below.
_CORE_PACKAGE = "github_core"

# The module inside that package this script actually imports (see the
# ``from github_core.api import RepoInfo`` line below). The candidate check
# validates this file, not just the package directory, because a directory
# named github_core that carries no api.py satisfies a name check and then
# dies at import with ModuleNotFoundError, which is exit 1 with a traceback
# instead of the documented exit 2 (PR #5000 review). Every shipped lib
# carries it: .claude/lib/github_core/api.py and
# src/copilot-cli/lib/github_core/api.py, verified 2026-08-14.
_CORE_MODULE_FILE = "api.py"


def _lib_dir_candidates() -> list[str]:
    """Return candidate ``lib`` directories, highest precedence first.

    1. ``COPILOT_PLUGIN_ROOT`` env (set by the Copilot CLI host; it may point
       at whichever plugin triggered the context-mode hook, not at this one).
    2. ``CLAUDE_PLUGIN_ROOT`` env (set by the Claude Code host; under Copilot
       it can hold a foreign plugin path, which is issue #4961).
    3. ``GITHUB_WORKSPACE`` env: the checkout layout on an Actions runner.
    4. Path relative to this file: the source checkout and the installed
       plugin both put ``lib`` three levels above ``scripts/``.

    Order matches the candidate list in the canonical sibling resolver,
    `.claude/skills/pr-comment-responder/scripts/cluster_threads.py` lines
    518-527, quoted verbatim:

        candidates = []
        copilot_root = os.environ.get("COPILOT_PLUGIN_ROOT")
        claude_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
        if copilot_root:
            candidates.append(os.path.join(copilot_root, "lib"))
        if claude_root:
            candidates.append(os.path.join(claude_root, "lib"))
        if workspace:
            candidates.append(os.path.join(workspace, ".claude", "lib"))
        candidates.append(relative)
    """
    copilot_root = os.environ.get("COPILOT_PLUGIN_ROOT")
    claude_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    workspace = os.environ.get("GITHUB_WORKSPACE")
    candidates: list[str] = []
    if copilot_root:
        candidates.append(os.path.join(copilot_root, "lib"))
    if claude_root:
        candidates.append(os.path.join(claude_root, "lib"))
    if workspace:
        candidates.append(os.path.join(workspace, ".claude", "lib"))
    candidates.append(str(Path(__file__).resolve().parents[3] / "lib"))
    return candidates


def _resolve_lib_dir() -> str:
    """Return the first candidate ``lib`` directory that carries github_core.api.

    Each candidate is validated before use, so a plugin root belonging to
    another plugin falls through to the next candidate instead of ending the
    run. Issue #4961: under the Copilot CLI, ``CLAUDE_PLUGIN_ROOT`` can name
    the context-mode plugin, and taking it as authoritative exits 2 while a
    valid root sits later in the list.

    Fail-closed is preserved: when no candidate carries the module, the
    process exits 2 (config error per ADR-035) naming every candidate tried
    and why each was rejected. It never imports from a foreign plugin.

    Stricter/looser/different than canonical:
    - Stricter than `.claude/skills/pr-comment-responder/scripts/cluster_threads.py`
      lines 529-531, which accepts a candidate on directory existence alone:

          for lib_dir in candidates:
              if os.path.isdir(lib_dir):
                  return lib_dir

      A foreign plugin that ships its own ``lib`` directory satisfies that
      test and then fails at import with a traceback instead of ADR-035
      exit 2. This resolver requires the imported module itself.

    - Stricter than `.claude/skills/github/scripts/issue/claim_issue.py`
      line 26, quoted verbatim:

          if _plugin_root and os.path.isdir(os.path.join(_plugin_root, "lib", "github_core")):

      That check accepts a ``github_core`` directory on name alone, so an
      empty or partial package passes and the import then raises
      ModuleNotFoundError. This resolver requires ``github_core/api.py``,
      the module the import below names.
    - Stricter than that claim_issue.py line in a second way: claim_issue.py
      collapses the two plugin roots with ``or`` (line 24), so a set-but-foreign
      COPILOT_PLUGIN_ROOT skips CLAUDE_PLUGIN_ROOT entirely. This resolver
      validates each root separately, so neither shadows the other.
    - Different in reporting: the failure message names the rejection reason
      per candidate; cluster_threads.py lists the paths alone.
    """
    rejected: list[str] = []
    for lib_dir in _lib_dir_candidates():
        if not os.path.isdir(lib_dir):
            rejected.append(f"{lib_dir} (no such directory)")
            continue
        if os.path.isfile(os.path.join(lib_dir, _CORE_PACKAGE, _CORE_MODULE_FILE)):
            return lib_dir
        rejected.append(f"{lib_dir} (no {_CORE_PACKAGE}/{_CORE_MODULE_FILE})")

    print(
        f"Plugin lib directory not found. Tried: {'; '.join(rejected)}",
        file=sys.stderr,
    )
    sys.exit(2)  # Config error per ADR-035


_LIB_DIR = _resolve_lib_dir()
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from github_core.api import RepoInfo  # noqa: E402

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
    except (RuntimeError, AttributeError):
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
    """Auto-detect owner/repo from git remote.

    Raises:
        RuntimeError: If git is not available, times out, or the remote
            URL cannot be parsed as a GitHub repository.
    """
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True,
            encoding="utf-8", errors="replace",
            check=True,
            timeout=10,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("Could not determine git remote origin") from exc

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


# Packaged plugin manifests carried a shared version counter that every
# plugin-source PR had to bump, so concurrent PRs collided on the version line
# (issue #2543). ADR-092 deleted the field and inverted the gate
# (build/scripts/validate_plugin_version_bump.py): it now fails when a manifest
# carries the field at all. Accept-theirs is still wrong here, because the two
# sides can differ in whether the field is present at all; the resolver below
# handles that shape and the legacy both-sides-semver shape.
_PLUGIN_MANIFEST_SUFFIX = "/.claude-plugin/plugin.json"

_PLAIN_SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def is_plugin_manifest(file_path: str) -> bool:
    """Check if a path is a packaged plugin manifest (plugin.json)."""
    return file_path.replace("\\", "/").endswith(_PLUGIN_MANIFEST_SUFFIX)


def _parse_plain_semver(version: str) -> tuple[int, int, int] | None:
    """Parse MAJOR.MINOR.PATCH; None for prerelease/build/malformed forms."""
    match = _PLAIN_SEMVER_RE.match(version)
    if match is None:
        return None
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


def _write_manifest_resolution(
    file_path: str, resolved: dict[str, Any], cwd: str | None = None
) -> bool:
    """Write a resolved manifest and stage it. False on path escape or git failure."""
    # Anchor the write to the repo the conflict lives in and refuse paths
    # that escape it (CWE-22); file_path normally comes from git itself,
    # but the function is importable with arbitrary arguments.
    base_dir = Path(cwd).resolve() if cwd else Path.cwd().resolve()
    target = (base_dir / file_path).resolve()
    if not target.is_relative_to(base_dir):
        return False
    target.write_text(json.dumps(resolved, indent=2) + "\n", encoding="utf-8")
    return _run_git("add", file_path, cwd=cwd).returncode == 0


def resolve_plugin_manifest_conflict(file_path: str, cwd: str | None = None) -> bool:
    """Resolve a version-only plugin.json conflict and stage the result.

    Reads both sides of the conflicted manifest from the index. Two shapes
    resolve automatically when the sides differ only in ``version``:

    - Either side omits ``version``. ADR-092 deleted the field, so the merged
      manifest carries none. This is the shape every plugin PR opened before
      ADR-092 hits when it merges the fixed ``main``.
    - Both sides carry plain semver. Write ``patch + 1`` above the higher
      version. Kept for branches that predate the field's deletion on both
      sides.

    Returns True when resolved and staged; False when manual resolution is
    required (non-version differences, prerelease/build versions, unreadable
    index stages, or malformed JSON).
    """
    ours_r = _run_git("show", f":2:{file_path}", cwd=cwd)
    theirs_r = _run_git("show", f":3:{file_path}", cwd=cwd)
    if ours_r.returncode != 0 or theirs_r.returncode != 0:
        return False

    try:
        ours = json.loads(ours_r.stdout)
        theirs = json.loads(theirs_r.stdout)
    except json.JSONDecodeError:
        return False
    if not isinstance(ours, dict) or not isinstance(theirs, dict):
        return False

    ours_rest = {k: v for k, v in ours.items() if k != "version"}
    theirs_rest = {k: v for k, v in theirs.items() if k != "version"}
    if ours_rest != theirs_rest:
        return False

    # ADR-092 deleted the field. A side without it is the post-ADR shape, and
    # the merged manifest must carry no version or the version-field gate
    # (build/scripts/validate_plugin_version_bump.py) fails.
    if "version" not in ours or "version" not in theirs:
        return _write_manifest_resolution(file_path, theirs_rest, cwd=cwd)

    ours_version = _parse_plain_semver(str(ours.get("version") or ""))
    theirs_version = _parse_plain_semver(str(theirs.get("version") or ""))
    if ours_version is None or theirs_version is None:
        return False

    major, minor, patch = max(ours_version, theirs_version)
    resolved = dict(theirs)
    resolved["version"] = f"{major}.{minor}.{patch + 1}"
    return _write_manifest_resolution(file_path, resolved, cwd=cwd)


def _resolve_conflicted_file(
    file_path: str,
    result: dict[str, Any],
    cwd: str | None = None,
) -> str:
    """Resolve one conflicted file in place.

    Returns "resolved", "blocked" (manual resolution required), or "error"
    (a git command failed; result["message"] is set).
    """
    if is_plugin_manifest(file_path):
        if resolve_plugin_manifest_conflict(file_path, cwd=cwd):
            result["files_resolved"].append(file_path)
            return "resolved"
        result["files_blocked"].append(file_path)
        return "blocked"
    if not is_auto_resolvable(file_path):
        result["files_blocked"].append(file_path)
        return "blocked"
    checkout_r = _run_git("checkout", "--theirs", file_path, cwd=cwd)
    if checkout_r.returncode != 0:
        result["message"] = f"Failed to checkout --theirs for {file_path}"
        return "error"
    add_r = _run_git("add", file_path, cwd=cwd)
    if add_r.returncode != 0:
        result["message"] = f"Failed to git add {file_path}"
        return "error"
    result["files_resolved"].append(file_path)
    return "resolved"


def _run_git(
    *args: str, cwd: str | None = None, timeout: int = 60
) -> subprocess.CompletedProcess[str]:
    """Run a git command and return the result.

    A timeout returns a synthetic nonzero result instead of raising, so
    every caller's returncode check handles a hung fetch/push the same way
    as any other git failure.
    """
    try:
        return subprocess.run(
            ["git", *args],
            capture_output=True,
            encoding="utf-8", errors="replace",
            cwd=cwd,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(
            args=["git", *args],
            returncode=124,
            stdout="",
            stderr=f"git {args[0]} timed out after {timeout}s",
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

    for ref in (branch_name, target_branch):
        if ref.startswith("-"):
            result["message"] = f"Invalid ref (leading dash): {ref}"
            return result

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
            status = _resolve_conflicted_file(file_path, result)
            if status == "error":
                return result
            if status == "blocked":
                can_auto_resolve = False

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

    repo_root_r = _run_git("rev-parse", "--git-common-dir")
    git_common = Path(repo_root_r.stdout.strip())
    if not git_common.is_absolute():
        git_common = (Path.cwd() / git_common).resolve()
    else:
        git_common = git_common.resolve()
    repo_root = str(git_common.parent)

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
                status = _resolve_conflicted_file(
                    file_path,
                    result,
                    cwd=worktree_path,
                )
                if status == "error":
                    return result
                if status == "blocked":
                    can_auto_resolve = False

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
