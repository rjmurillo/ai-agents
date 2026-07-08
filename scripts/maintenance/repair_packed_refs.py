#!/usr/bin/env python3
"""Repair blank-line corruption in git packed-refs files.

Issue #2903 records an external C# LSP session-init path that can insert a
blank line into ``packed-refs``. Git rejects any blank line in that file, so
the guard removes only blank records, preserves every real ref record, and
verifies refs after a rewrite.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

_GIT_TIMEOUT_SECONDS = 15


@dataclass(frozen=True, slots=True)
class RepairResult:
    """Outcome from one packed-refs repair pass."""

    packed_refs_path: Path | None
    status: str
    removed_blank_lines: int = 0
    backup_path: Path | None = None


def find_worktree_root(start_path: Path) -> Path | None:
    """Return the nearest ancestor containing a .git marker."""
    current = start_path.resolve()
    if current.is_file():
        current = current.parent

    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def resolve_common_git_dir(worktree_root: Path) -> Path:
    """Resolve the common git directory for normal and linked worktrees."""
    git_marker = worktree_root / ".git"
    git_dir = _resolve_git_dir(git_marker, worktree_root)
    common_dir_file = git_dir / "commondir"
    if not common_dir_file.exists():
        return git_dir

    common_dir_text = common_dir_file.read_text(encoding="utf-8").strip()
    common_dir = Path(common_dir_text)
    if not common_dir.is_absolute():
        common_dir = git_dir / common_dir
    return common_dir.resolve()


def normalize_packed_refs(data: bytes) -> tuple[bytes, int]:
    """Remove blank lines while preserving all non-blank packed-refs records."""
    kept_lines: list[bytes] = []
    removed_blank_lines = 0

    for line in data.splitlines(keepends=True):
        if line.rstrip(b"\r\n") == b"":
            removed_blank_lines += 1
            continue
        kept_lines.append(line)

    return b"".join(kept_lines), removed_blank_lines


def verify_git_refs(worktree_root: Path) -> None:
    """Verify git can parse refs after repair."""
    env = os.environ.copy()
    for key in ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE"):
        env.pop(key, None)

    try:
        result = subprocess.run(
            ["git", "for-each-ref", "--format=%(refname)"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            cwd=worktree_root,
            env=env,
            timeout=_GIT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"git for-each-ref failed: {exc}") from exc

    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"git for-each-ref failed: {message}")


def repair_packed_refs(
    start_path: Path,
    verifier: Callable[[Path], None] = verify_git_refs,
) -> RepairResult:
    """Repair a packed-refs file when blank lines are present."""
    worktree_root = find_worktree_root(start_path)
    if worktree_root is None:
        return RepairResult(packed_refs_path=None, status="not-a-git-worktree")

    packed_refs_path = resolve_common_git_dir(worktree_root) / "packed-refs"
    if not packed_refs_path.exists():
        return RepairResult(packed_refs_path=packed_refs_path, status="missing")

    original = packed_refs_path.read_bytes()
    repaired, removed_blank_lines = normalize_packed_refs(original)
    if removed_blank_lines == 0:
        return RepairResult(packed_refs_path=packed_refs_path, status="clean")

    backup_path = _backup_packed_refs(packed_refs_path)
    _write_repaired_packed_refs(packed_refs_path, repaired)
    try:
        verifier(worktree_root)
    except Exception:
        shutil.copy2(backup_path, packed_refs_path)
        raise

    return RepairResult(
        packed_refs_path=packed_refs_path,
        status="repaired",
        removed_blank_lines=removed_blank_lines,
        backup_path=backup_path,
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--path",
        type=Path,
        default=Path.cwd(),
        help="Worktree path to inspect. Defaults to the current directory.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the packed-refs repair guard."""
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        result = repair_packed_refs(args.path)
    except Exception as exc:
        print(f"ERROR: packed-refs repair failed: {exc}", file=sys.stderr)
        return 1

    if result.status == "repaired":
        print(
            "Repaired git packed-refs: "
            f"removed {result.removed_blank_lines} blank line(s) from "
            f"{result.packed_refs_path}; backup: {result.backup_path}"
        )
    return 0


def _resolve_git_dir(git_marker: Path, worktree_root: Path) -> Path:
    if git_marker.is_dir():
        return git_marker.resolve()

    text = git_marker.read_text(encoding="utf-8").strip()
    prefix = "gitdir:"
    if not text.lower().startswith(prefix):
        raise ValueError(f"invalid .git file at {git_marker}")

    git_dir = Path(text[len(prefix) :].strip())
    if not git_dir.is_absolute():
        git_dir = worktree_root / git_dir
    return git_dir.resolve()


def _backup_packed_refs(packed_refs_path: Path) -> Path:
    backup_path = packed_refs_path.with_name(f"{packed_refs_path.name}.before-repair")
    if backup_path.exists():
        for suffix in range(1, 1000):
            candidate = packed_refs_path.with_name(
                f"{packed_refs_path.name}.before-repair.{suffix}"
            )
            if not candidate.exists():
                backup_path = candidate
                break
        else:
            raise RuntimeError("could not choose a packed-refs backup path")

    shutil.copy2(packed_refs_path, backup_path)
    return backup_path


def _write_repaired_packed_refs(packed_refs_path: Path, repaired: bytes) -> None:
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=packed_refs_path.parent, delete=False) as temp_file:
            temporary_path = Path(temp_file.name)
            temp_file.write(repaired)
            temp_file.flush()
            shutil.copymode(packed_refs_path, temporary_path)
            os.fsync(temp_file.fileno())
    except Exception:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise

    if temporary_path is None:
        raise RuntimeError("temporary packed-refs path was not created")
    try:
        os.replace(temporary_path, packed_refs_path)
    except OSError:
        temporary_path.unlink(missing_ok=True)
        raise


if __name__ == "__main__":
    sys.exit(main())
