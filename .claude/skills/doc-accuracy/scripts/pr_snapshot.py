#!/usr/bin/env python3
# taste-lint: ignore file-size
"""Immutable PR snapshot for doc-accuracy review.

Pins review input to an exact commit pair (head + base) fetched into isolated
temporary storage.  Verifies fetched object IDs, rejects shallow or partial
clones, sanitizes the Git environment, and rechecks full PR identity before
publishing to detect force-push, head movement, base-branch change, or
repository transfer.

Security:
- Snapshot content treated as untrusted (hostile).
- Git environment fully sanitized (no GIT_DIR, GIT_WORK_TREE, filters, hooks).
- No hooks, scripts, submodules, or filters executed.
- Fetches use --no-tags --no-recurse-submodules (full depth).
- Input owner/repo validated against injection patterns.
- NUL-delimited path output for safe Unicode/newline handling.

Exit codes (ADR-035):
    0: Success
    1: Verification failure (SHA mismatch, shallow, stale, caller dirty)
    2: Configuration error (bad args, missing dependency)
    3: External failure (network, GitHub API, timeout)
    4: Authentication error (token expired, permission denied)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Exit codes (ADR-035)
# ---------------------------------------------------------------------------

EXIT_OK = 0
EXIT_VERIFY = 1       # Validation/verification failure
EXIT_CONFIG = 2       # Configuration error
EXIT_EXTERNAL = 3     # External dependency failure
EXIT_AUTH = 4         # Authentication/permission error

_GIT_TIMEOUT = 120

# Owner/repo pattern: GitHub allows alphanumeric, hyphens, dots, underscores
_OWNER_RE = re.compile(r"^[a-zA-Z0-9]([a-zA-Z0-9._-]*[a-zA-Z0-9])?$")
_REPO_RE = re.compile(r"^[a-zA-Z0-9._-]+$")
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


# ---------------------------------------------------------------------------
# Git environment sanitization (from doc_accuracy.py)
# ---------------------------------------------------------------------------

_GIT_ENV_DENY_EXACT = frozenset((
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_IMPLICIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_COMMON_DIR",
    "GIT_CEILING_DIRECTORIES",
    "GIT_GRAFT_FILE",
    "GIT_REPLACE_REF_BASE",
    "GIT_NO_REPLACE_OBJECTS",
    "GIT_PREFIX",
    "GIT_CONFIG",
    "GIT_CONFIG_PARAMETERS",
    "GIT_CONFIG_COUNT",
))

_GIT_ENV_DENY_PREFIXES = ("GIT_CONFIG_",)

_GIT_ENV_FORCE = {
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
    "GIT_GRAFT_FILE": os.devnull,
    "GIT_NO_REPLACE_OBJECTS": "1",
    "GIT_TERMINAL_PROMPT": "0",
}


def _git_env() -> dict[str, str]:
    """Return a sanitized copy of os.environ without git repo/config vars."""
    env = os.environ.copy()
    for key in tuple(env):
        normalized = key.upper()
        if (
            normalized in _GIT_ENV_DENY_EXACT
            or any(normalized.startswith(p) for p in _GIT_ENV_DENY_PREFIXES)
        ):
            del env[key]
    env.update(_GIT_ENV_FORCE)
    return env


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PrIdentity:
    """Immutable PR identity captured at snapshot time."""

    owner: str
    repo: str
    number: int
    head_sha: str
    base_sha: str
    base_branch: str
    head_repo_full_name: str  # e.g. "owner/repo" or "fork-owner/repo"
    base_repo_full_name: str  # canonical repo

    def to_dict(self) -> dict[str, Any]:
        return {
            "owner": self.owner,
            "repo": self.repo,
            "number": self.number,
            "head_sha": self.head_sha,
            "base_sha": self.base_sha,
            "base_branch": self.base_branch,
            "head_repo_full_name": self.head_repo_full_name,
            "base_repo_full_name": self.base_repo_full_name,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> PrIdentity:
        return cls(
            owner=d["owner"],
            repo=d["repo"],
            number=int(d["number"]),
            head_sha=d["head_sha"],
            base_sha=d["base_sha"],
            base_branch=d["base_branch"],
            head_repo_full_name=d.get("head_repo_full_name", f"{d['owner']}/{d['repo']}"),
            base_repo_full_name=d.get("base_repo_full_name", f"{d['owner']}/{d['repo']}"),
        )


@dataclass
class Snapshot:
    """An immutable snapshot of a PR's code at a specific commit pair."""

    identity: PrIdentity
    worktree_path: Path
    changed_paths: list[str]
    bare_repo_path: Path

    def cleanup(self) -> None:
        """Remove temporary storage."""
        import shutil

        if self.worktree_path.exists():
            _run_git(
                ["worktree", "remove", "--force", str(self.worktree_path)],
                cwd=self.bare_repo_path,
                check=False,
            )
        if self.bare_repo_path.exists():
            shutil.rmtree(self.bare_repo_path, ignore_errors=True)


class SnapshotError(Exception):
    """Base for snapshot errors."""

    def __init__(self, message: str, exit_code: int) -> None:
        super().__init__(message)
        self.exit_code = exit_code


class ConfigError(SnapshotError):
    """Configuration error."""

    def __init__(self, message: str) -> None:
        super().__init__(message, EXIT_CONFIG)


class ExternalError(SnapshotError):
    """External dependency failure."""

    def __init__(self, message: str) -> None:
        super().__init__(message, EXIT_EXTERNAL)


class AuthError(SnapshotError):
    """Authentication or permission error."""

    def __init__(self, message: str) -> None:
        super().__init__(message, EXIT_AUTH)


class VerifyError(SnapshotError):
    """Verification failure (SHA mismatch, shallow, stale, caller dirty)."""

    def __init__(self, message: str) -> None:
        super().__init__(message, EXIT_VERIFY)


class StaleError(VerifyError):
    """PR identity changed since snapshot (subtype of verification failure)."""

    pass


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


def _validate_owner(owner: str) -> None:
    """Reject owner strings that could inject into URLs or commands."""
    if not owner or not _OWNER_RE.match(owner):
        raise ConfigError(f"Invalid owner format: {owner!r}")
    if len(owner) > 39:
        raise ConfigError(f"Owner too long: {len(owner)} chars")


def _validate_repo(repo: str) -> None:
    """Reject repo strings that could inject into URLs or commands."""
    if not repo or not _REPO_RE.match(repo):
        raise ConfigError(f"Invalid repo format: {repo!r}")
    if len(repo) > 100:
        raise ConfigError(f"Repo name too long: {len(repo)} chars")
    if repo in (".", ".."):
        raise ConfigError(f"Invalid repo name: {repo!r}")


def _validate_sha(sha: str, label: str) -> None:
    """Validate a SHA-1 hex string."""
    if not _SHA_RE.match(sha):
        raise VerifyError(f"Invalid SHA for {label}: {sha!r}")


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------


def _run_git(
    args: list[str],
    *,
    cwd: Path | None = None,
    check: bool = True,
    timeout: int = _GIT_TIMEOUT,
) -> subprocess.CompletedProcess[str]:
    """Run git with sanitized environment and security flags."""
    cmd = [
        "git",
        "--no-replace-objects",
        "-c", "core.hooksPath=/dev/null",
        "-c", "core.fsmonitor=false",
        "-c", "protocol.file.allow=never",
        "-c", "transfer.fsckObjects=true",
        "-c", "safe.bareRepository=all",
        *args,
    ]
    env = _git_env()
    try:
        return subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=check,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        raise ExternalError(f"git timed out ({timeout}s): {args[0] if args else '?'}") from exc
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.strip() if exc.stderr else ""
        if "could not read Username" in stderr or "Authentication" in stderr:
            raise AuthError(f"git auth failure: {stderr}") from exc
        if "Permission" in stderr or "denied" in stderr.lower():
            raise AuthError(f"git permission denied: {stderr}") from exc
        if check:
            raise ExternalError(f"git failed ({args[0] if args else '?'}): {stderr}") from exc
        raise


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------


def resolve_pr_identity(owner: str, repo: str, number: int) -> PrIdentity:
    """Resolve current PR identity from GitHub API.

    Fetches head/base SHAs, base branch, and repository identities.
    Does NOT load PR prose/body (security: no untrusted content parsed).
    Rejects cross-repository (fork) PRs.
    """
    _validate_owner(owner)
    _validate_repo(repo)

    jq_expr = (
        ".head.sha + \"\\n\" + .base.sha + \"\\n\" + .base.ref + \"\\n\" "
        "+ .head.repo.full_name + \"\\n\" + .base.repo.full_name"
    )
    try:
        result = subprocess.run(
            ["gh", "api", f"repos/{owner}/{repo}/pulls/{number}", "--jq", jq_expr],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=True,
            env=_git_env(),
        )
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.strip() if exc.stderr else ""
        if "401" in stderr or "403" in stderr or "auth" in stderr.lower():
            raise AuthError(f"GitHub API auth failure: {stderr}") from exc
        if "404" in stderr:
            raise ExternalError(f"PR not found: {owner}/{repo}#{number}") from exc
        raise ExternalError(f"GitHub API failure: {stderr}") from exc
    except FileNotFoundError as exc:
        raise ConfigError("gh CLI not available") from exc

    lines = result.stdout.strip().split("\n")
    if len(lines) != 5:
        raise ExternalError(f"Unexpected PR API response ({len(lines)} lines)")

    head_sha, base_sha, base_branch, head_repo, base_repo = lines
    _validate_sha(head_sha, "head")
    _validate_sha(base_sha, "base")

    # Reject cross-repository (fork) PRs
    if head_repo != base_repo:
        raise VerifyError(
            f"Cross-repository PR rejected: head={head_repo}, base={base_repo}"
        )

    return PrIdentity(
        owner=owner,
        repo=repo,
        number=number,
        head_sha=head_sha,
        base_sha=base_sha,
        base_branch=base_branch,
        head_repo_full_name=head_repo,
        base_repo_full_name=base_repo,
    )


def capture_snapshot(
    identity: PrIdentity,
    *,
    temp_dir: Path | None = None,
) -> Snapshot:
    """Fetch exact head and base objects into isolated temporary storage.

    Creates a bare clone, fetches the specific SHAs (full depth, no partial),
    verifies them, rejects shallow repositories, and creates a worktree at
    head_sha with hooks/filters/submodules disabled.
    """
    base_dir = temp_dir or Path(tempfile.mkdtemp(prefix="doc-accuracy-snap-"))
    bare_path = base_dir / "bare.git"
    wt_path = base_dir / "worktree"

    clone_url = f"https://github.com/{identity.owner}/{identity.repo}.git"

    # Init bare repo
    _run_git(["init", "--bare", str(bare_path)])

    # Disable submodules in the bare repo config
    _run_git(
        ["config", "submodule.recurse", "false"],
        cwd=bare_path,
    )
    _run_git(
        ["config", "protocol.file.allow", "never"],
        cwd=bare_path,
    )

    # Add remote
    _run_git(["remote", "add", "origin", clone_url], cwd=bare_path)

    # Fetch head and base SHAs with FULL depth (no --depth, no --filter)
    _run_git(
        [
            "fetch", "origin",
            "--no-tags",
            "--no-recurse-submodules",
            identity.head_sha,
            identity.base_sha,
        ],
        cwd=bare_path,
    )

    # Reject shallow repository
    shallow_result = _run_git(
        ["rev-parse", "--is-shallow-repository"],
        cwd=bare_path,
    )
    if shallow_result.stdout.strip() == "true":
        raise VerifyError("Shallow repository detected; full object graph required")

    # Verify fetched objects are commits with expected SHAs
    _verify_object(bare_path, identity.head_sha, "head")
    _verify_object(bare_path, identity.base_sha, "base")

    # Verify head tree is fully available (not partial)
    tree_result = _run_git(
        ["rev-parse", "--verify", f"{identity.head_sha}^{{tree}}"],
        cwd=bare_path,
    )
    if not tree_result.stdout.strip():
        raise VerifyError("Head commit tree not available (partial clone?)")

    # Verify base tree is also available
    base_tree_result = _run_git(
        ["rev-parse", "--verify", f"{identity.base_sha}^{{tree}}"],
        cwd=bare_path,
    )
    if not base_tree_result.stdout.strip():
        raise VerifyError("Base commit tree not available (partial clone?)")

    # Create worktree at head SHA (hooks disabled via config and env)
    _run_git(
        ["worktree", "add", "--detach", str(wt_path), identity.head_sha],
        cwd=bare_path,
    )

    # Compute changed paths (NUL-delimited for safety with Unicode/newlines)
    changed = _compute_changed_paths(bare_path, identity.base_sha, identity.head_sha)

    return Snapshot(
        identity=identity,
        worktree_path=wt_path,
        changed_paths=changed,
        bare_repo_path=bare_path,
    )


def _verify_object(bare_path: Path, sha: str, label: str) -> None:
    """Verify a fetched object exists and is a commit."""
    result = _run_git(
        ["cat-file", "-t", sha],
        cwd=bare_path,
        check=False,
    )
    if result.returncode != 0:
        raise VerifyError(f"Object not fetched for {label}: {sha}")
    obj_type = result.stdout.strip()
    if obj_type != "commit":
        raise VerifyError(f"Expected commit for {label}, got {obj_type}: {sha}")


def _compute_changed_paths(
    bare_path: Path, base_sha: str, head_sha: str
) -> list[str]:
    """Compute changed paths between base and head using NUL delimiter.

    Includes renames, deletes, binary files. Uses -z for NUL-delimited output
    to safely handle Unicode and newline characters in paths.
    """
    result = _run_git(
        [
            "diff-tree", "-r", "--name-only", "-z",
            "--diff-filter=ACDMRT",
            "--find-renames",
            base_sha, head_sha,
        ],
        cwd=bare_path,
    )
    raw = result.stdout
    if not raw:
        return []
    return [p for p in raw.split("\0") if p]


def check_staleness(identity: PrIdentity) -> None:
    """Re-check full PR identity. Raises StaleError on any change.

    Compares: head SHA, base SHA, base branch, head repo, base repo.
    """
    try:
        current = resolve_pr_identity(
            identity.owner, identity.repo, identity.number
        )
    except AuthError:
        raise
    except SnapshotError:
        raise StaleError("Cannot verify PR identity (network failure)") from None

    changes: list[str] = []
    if current.head_sha != identity.head_sha:
        changes.append(f"head {identity.head_sha[:8]}->{current.head_sha[:8]}")
    if current.base_sha != identity.base_sha:
        changes.append(f"base {identity.base_sha[:8]}->{current.base_sha[:8]}")
    if current.base_branch != identity.base_branch:
        changes.append(f"branch {identity.base_branch}->{current.base_branch}")
    if current.head_repo_full_name != identity.head_repo_full_name:
        changes.append(f"head_repo {identity.head_repo_full_name}->{current.head_repo_full_name}")
    if current.base_repo_full_name != identity.base_repo_full_name:
        changes.append(f"base_repo {identity.base_repo_full_name}->{current.base_repo_full_name}")

    if changes:
        raise StaleError(f"PR #{identity.number} changed: {'; '.join(changes)}")


def verify_caller_unchanged(caller_repo: Path) -> None:
    """Prove the caller's checkout was not modified by the snapshot process."""
    result = _run_git(
        ["status", "--porcelain"],
        cwd=caller_repo,
    )
    if result.stdout.strip():
        raise VerifyError(
            f"Caller checkout modified during snapshot: {result.stdout.strip()[:200]}"
        )


def run_scanner(
    snapshot: Snapshot,
    *,
    scanner_script: Path | None = None,
) -> int:
    """Run the existing doc-accuracy scanner against the snapshot worktree.

    Returns the scanner's exit code.
    """
    if scanner_script is None:
        scanner_script = Path(__file__).parent / "doc_accuracy.py"
    if not scanner_script.exists():
        raise ConfigError(f"Scanner script not found: {scanner_script}")

    env = _git_env()
    try:
        result = subprocess.run(
            [sys.executable, str(scanner_script), "--target", str(snapshot.worktree_path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,
            check=False,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        raise ExternalError("Scanner timed out (300s)") from exc
    return result.returncode


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:

    parser = argparse.ArgumentParser(
        description="Capture immutable PR snapshot for doc-accuracy review"
    )
    parser.add_argument("--owner", required=True, help="Repository owner")
    parser.add_argument("--repo", required=True, help="Repository name")
    parser.add_argument(
        "--pull-request", type=int, required=True, help="PR number"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory for snapshot (default: auto temp dir)",
    )
    parser.add_argument(
        "--check-stale",
        action="store_true",
        help="Re-check PR identity and exit 1 if changed",
    )
    parser.add_argument(
        "--identity-file",
        type=Path,
        default=None,
        help="Path to previously captured identity JSON (for --check-stale)",
    )
    parser.add_argument(
        "--run-scanner",
        action="store_true",
        help="Run doc-accuracy scanner against snapshot after capture",
    )
    parser.add_argument(
        "--verify-caller",
        type=Path,
        default=None,
        help="Verify this repo path is unchanged after capture",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point.

    Full workflow: resolve -> capture -> verify caller -> run scanner ->
    staleness recheck -> output.
    """
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        # Stale-check mode
        if args.check_stale:
            if not args.identity_file or not args.identity_file.exists():
                print(
                    "ERROR: --identity-file required for --check-stale",
                    file=sys.stderr,
                )
                return EXIT_CONFIG
            data = json.loads(args.identity_file.read_text(encoding="utf-8"))
            identity = PrIdentity.from_dict(data)
            check_staleness(identity)
            print(json.dumps({"status": "current", "identity": identity.to_dict()}))
            return EXIT_OK

        # Capture mode
        identity = resolve_pr_identity(args.owner, args.repo, args.pull_request)
        snapshot = capture_snapshot(identity, temp_dir=args.output_dir)

        # Verify caller unchanged (if requested)
        if args.verify_caller:
            verify_caller_unchanged(args.verify_caller)

        # Run scanner (if requested)
        scanner_exit = None
        if args.run_scanner:
            scanner_exit = run_scanner(snapshot)

        # Publish-time staleness recheck
        check_staleness(identity)

        output = {
            "status": "captured",
            "identity": identity.to_dict(),
            "worktree_path": str(snapshot.worktree_path),
            "changed_paths": snapshot.changed_paths,
            "changed_path_count": len(snapshot.changed_paths),
        }
        if scanner_exit is not None:
            output["scanner_exit_code"] = scanner_exit
        print(json.dumps(output, indent=2))
        return EXIT_OK

    except SnapshotError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return exc.exit_code


if __name__ == "__main__":
    sys.exit(main())
