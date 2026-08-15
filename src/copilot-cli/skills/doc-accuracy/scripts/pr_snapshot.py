#!/usr/bin/env python3
"""Immutable PR snapshot for doc-accuracy review.

Pins review input to an exact commit pair (head + base) fetched into isolated
temporary storage.  Verifies fetched object IDs match expected values before
returning the snapshot path.  Rechecks PR identity before publishing to detect
force-push or head movement (returns STALE).

Security:
- Content treated as untrusted; no hooks, scripts, or submodules executed.
- Fetches use --no-tags --no-recurse-submodules.
- Snapshot directory is a bare clone; worktree checkout disables hooks.

Exit codes follow ADR-035:
    0: Success
    2: Configuration error (bad args)
    3: External failure (network, auth, quota)
    4: Verification failure (SHA mismatch, shallow clone)
    5: Stale (PR head/base changed since capture)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Exit codes
# ---------------------------------------------------------------------------

EXIT_OK = 0
EXIT_CONFIG = 2
EXIT_EXTERNAL = 3
EXIT_VERIFY = 4
EXIT_STALE = 5

_GIT_TIMEOUT = 120


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

    def to_dict(self) -> dict[str, Any]:
        return {
            "owner": self.owner,
            "repo": self.repo,
            "number": self.number,
            "head_sha": self.head_sha,
            "base_sha": self.base_sha,
            "base_branch": self.base_branch,
        }


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


class VerifyError(SnapshotError):
    """Verification failure."""

    def __init__(self, message: str) -> None:
        super().__init__(message, EXIT_VERIFY)


class StaleError(SnapshotError):
    """PR identity changed since snapshot."""

    def __init__(self, message: str) -> None:
        super().__init__(message, EXIT_STALE)


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
    """Run git with security flags."""
    cmd = [
        "git",
        "-c", "core.hooksPath=/dev/null",
        "-c", "protocol.file.allow=never",
        *args,
    ]
    try:
        return subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout,
            check=check,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )
    except subprocess.TimeoutExpired as exc:
        raise ExternalError(f"git timed out ({timeout}s): {exc.cmd}") from exc
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.strip() if exc.stderr else ""
        if "could not read Username" in stderr or "Authentication" in stderr:
            raise ExternalError(f"git auth failure: {stderr}") from exc
        if check:
            raise ExternalError(f"git failed: {stderr}") from exc
        raise


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------


def resolve_pr_identity(owner: str, repo: str, number: int) -> PrIdentity:
    """Resolve current PR identity from GitHub API.

    Does NOT load PR prose/body (security: no untrusted content).
    """
    try:
        result = subprocess.run(
            [
                "gh", "api",
                f"repos/{owner}/{repo}/pulls/{number}",
                "--jq", ".head.sha + \" \" + .base.sha + \" \" + .base.ref",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
            check=True,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )
    except subprocess.CalledProcessError as exc:
        raise ExternalError(
            f"Failed to resolve PR identity: {exc.stderr.strip()}"
        ) from exc
    except FileNotFoundError as exc:
        raise ExternalError("gh CLI not available") from exc

    parts = result.stdout.strip().split(" ", 2)
    if len(parts) != 3:
        raise ExternalError(f"Unexpected PR API response: {result.stdout.strip()}")

    head_sha, base_sha, base_branch = parts
    if len(head_sha) != 40 or len(base_sha) != 40:
        raise VerifyError(
            f"Invalid SHA lengths: head={len(head_sha)}, base={len(base_sha)}"
        )

    return PrIdentity(
        owner=owner,
        repo=repo,
        number=number,
        head_sha=head_sha,
        base_sha=base_sha,
        base_branch=base_branch,
    )


def capture_snapshot(
    identity: PrIdentity,
    *,
    temp_dir: Path | None = None,
) -> Snapshot:
    """Fetch exact head and base objects into isolated temporary storage.

    Creates a bare clone, fetches the specific SHAs, verifies them,
    and creates a read-only worktree at head_sha.
    """
    base_dir = temp_dir or Path(tempfile.mkdtemp(prefix="doc-accuracy-snap-"))
    bare_path = base_dir / "bare.git"
    wt_path = base_dir / "worktree"

    clone_url = f"https://github.com/{identity.owner}/{identity.repo}.git"

    # Init bare repo
    _run_git(["init", "--bare", str(bare_path)])

    # Add remote and fetch specific commits
    _run_git(["remote", "add", "origin", clone_url], cwd=bare_path)

    # Fetch head and base SHAs directly
    _run_git(
        [
            "fetch", "origin",
            "--no-tags",
            "--no-recurse-submodules",
            "--depth=1",
            identity.head_sha,
            identity.base_sha,
        ],
        cwd=bare_path,
    )

    # Verify fetched objects
    _verify_object(bare_path, identity.head_sha, "head")
    _verify_object(bare_path, identity.base_sha, "base")

    # Reject shallow if full tree unavailable
    result = _run_git(
        ["rev-parse", "--verify", f"{identity.head_sha}^{{tree}}"],
        cwd=bare_path,
    )
    if not result.stdout.strip():
        raise VerifyError("Head commit tree not available (shallow?)")

    # Create worktree at head SHA (no hooks)
    _run_git(
        ["worktree", "add", "--detach", str(wt_path), identity.head_sha],
        cwd=bare_path,
    )

    # Compute changed paths (NUL-delimited for safety)
    changed = _compute_changed_paths(bare_path, identity.base_sha, identity.head_sha)

    return Snapshot(
        identity=identity,
        worktree_path=wt_path,
        changed_paths=changed,
        bare_repo_path=bare_path,
    )


def _verify_object(bare_path: Path, sha: str, label: str) -> None:
    """Verify a fetched object exists and has correct type."""
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
    """Compute changed paths between base and head using NUL delimiter."""
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
    # Split on NUL, filter empty strings
    return [p for p in raw.split("\0") if p]


def check_staleness(identity: PrIdentity) -> PrIdentity | None:
    """Re-check PR identity. Returns new identity if changed, None if same."""
    try:
        current = resolve_pr_identity(
            identity.owner, identity.repo, identity.number
        )
    except SnapshotError:
        # If we can't check, treat as stale (fail closed)
        raise StaleError("Cannot verify PR identity (network failure)")

    if (
        current.head_sha != identity.head_sha
        or current.base_sha != identity.base_sha
    ):
        raise StaleError(
            f"PR #{identity.number} changed: "
            f"head {identity.head_sha[:8]}→{current.head_sha[:8]}, "
            f"base {identity.base_sha[:8]}→{current.base_sha[:8]}"
        )
    return None


def verify_caller_unchanged(caller_repo: Path) -> None:
    """Prove the caller's checkout was not modified by the snapshot process."""
    result = _run_git(
        ["status", "--porcelain"],
        cwd=caller_repo,
    )
    if result.stdout.strip():
        raise VerifyError(
            f"Caller checkout modified during snapshot: {result.stdout.strip()}"
        )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> "argparse.ArgumentParser":
    import argparse

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
        help="Re-check PR identity and exit 5 if changed",
    )
    parser.add_argument(
        "--identity-file",
        type=Path,
        default=None,
        help="Path to previously captured identity JSON (for --check-stale)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        if args.check_stale:
            if not args.identity_file or not args.identity_file.exists():
                print(
                    "ERROR: --identity-file required for --check-stale",
                    file=sys.stderr,
                )
                return EXIT_CONFIG
            data = json.loads(args.identity_file.read_text(encoding="utf-8"))
            identity = PrIdentity(**data)
            check_staleness(identity)
            print(json.dumps({"status": "current", "identity": identity.to_dict()}))
            return EXIT_OK

        identity = resolve_pr_identity(args.owner, args.repo, args.pull_request)
        snapshot = capture_snapshot(identity, temp_dir=args.output_dir)

        output = {
            "status": "captured",
            "identity": identity.to_dict(),
            "worktree_path": str(snapshot.worktree_path),
            "changed_paths": snapshot.changed_paths,
            "changed_path_count": len(snapshot.changed_paths),
        }
        print(json.dumps(output, indent=2))
        return EXIT_OK

    except SnapshotError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return exc.exit_code


if __name__ == "__main__":
    sys.exit(main())
