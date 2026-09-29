"""Git and path operations for isolated mutation worktrees."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import IO

GIT_COMMAND_TIMEOUT_SECONDS = 30
MARKER_DIRECTORY_NAME = "mutation-active"
SCRATCH_DIRECTORY_SUFFIX = ".mutation-worktrees"
# Markers written before scratch worktrees moved out of the clone still name
# this location. Recovery must clear them; creation never uses it.
LEGACY_SCRATCH_DIRECTORY = Path(".pytest_cache") / "mutation-worktrees"
_WORKTREE_LOCK_NAME = "mutation-worktrees.lock"
STALE_LOCK_REASON = "initializing"
_GIT_ENVIRONMENT_KEYS = {
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_CEILING_DIRECTORIES",
    "GIT_COMMON_DIR",
    "GIT_CONFIG_COUNT",
    "GIT_CONFIG_GLOBAL",
    "GIT_CONFIG_NOSYSTEM",
    "GIT_CONFIG_PARAMETERS",
    "GIT_CONFIG_SYSTEM",
    "GIT_DIR",
    "GIT_EXEC_PATH",
    "GIT_INDEX_FILE",
    "GIT_NAMESPACE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_PREFIX",
    "GIT_SHALLOW_FILE",
    "GIT_WORK_TREE",
}
_GIT_ENVIRONMENT_PREFIXES = ("GIT_CONFIG_KEY_", "GIT_CONFIG_VALUE_", "GIT_TRACE")


class MutationWorkspaceError(RuntimeError):
    """Raised when mutation isolation or cleanup cannot be proven."""


if sys.platform == "win32":
    import msvcrt

    _win_lock_positions: dict[int, int] = {}

    def _lock_file(handle: IO[bytes]) -> None:
        fd = handle.fileno()
        _win_lock_positions[fd] = handle.tell()
        handle.seek(0)
        msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
        handle.seek(_win_lock_positions.get(fd, 0))

    def _unlock_file(handle: IO[bytes]) -> None:
        fd = handle.fileno()
        position = handle.tell()
        handle.seek(0)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        _win_lock_positions.pop(fd, None)
        handle.seek(position)
else:
    import fcntl

    def _lock_file(handle: IO[bytes]) -> None:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)

    def _unlock_file(handle: IO[bytes]) -> None:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def run_git(repo_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    command = [
        "git",
        f"--work-tree={repo_root.resolve()}",
        "-c",
        "core.bare=false",
        "-c",
        "trace2.normalTarget=0",
        "-c",
        "trace2.perfTarget=0",
        "-c",
        "trace2.eventTarget=0",
        *args,
    ]
    environment = {
        key: value
        for key, value in os.environ.items()
        if key not in _GIT_ENVIRONMENT_KEYS
        and not key.startswith(_GIT_ENVIRONMENT_PREFIXES)
    }
    environment["GIT_CONFIG_GLOBAL"] = os.devnull
    environment["GIT_CONFIG_NOSYSTEM"] = "1"
    environment["GIT_CONFIG_SYSTEM"] = os.devnull
    try:
        return subprocess.run(
            command,
            cwd=repo_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            env=environment,
            timeout=GIT_COMMAND_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise MutationWorkspaceError(
            f"git command timed out after {GIT_COMMAND_TIMEOUT_SECONDS}s: {' '.join(command)}"
        ) from exc
    except OSError as exc:
        raise MutationWorkspaceError(f"cannot run git command: {exc}") from exc


def require_git_stdout(cwd: Path, *args: str, error: str) -> str:
    result = run_git(cwd, *args)
    if result.returncode != 0 or not result.stdout.strip():
        raise MutationWorkspaceError(f"{error}: {result.stderr.strip()}")
    stdout = result.stdout.strip()
    if "\n" in stdout or "\r" in stdout:
        raise MutationWorkspaceError(f"{error}: unexpected multiline git output")
    return stdout


def git_root(path: Path) -> Path:
    candidate = _find_worktree_root(path)
    if candidate is None:
        raise MutationWorkspaceError(f"cannot find git worktree root from {path}")
    stdout = require_git_stdout(
        candidate,
        "rev-parse",
        "--show-toplevel",
        error=f"cannot find git worktree root from {path}",
    )
    root = Path(stdout).resolve()
    if root != candidate:
        raise MutationWorkspaceError(
            f"git worktree root mismatch: expected {candidate}, got {root}"
        )
    return root


def _find_worktree_root(path: Path) -> Path | None:
    resolved = path.resolve()
    start = resolved if resolved.is_dir() else resolved.parent
    for candidate in (start, *start.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def marker_directory(repo_root: Path) -> Path:
    """Return the worktree-specific mutation marker directory."""
    root = git_root(repo_root)
    stdout = require_git_stdout(
        root,
        "rev-parse",
        "--git-path",
        MARKER_DIRECTORY_NAME,
        error="cannot locate git marker directory",
    )
    path = Path(stdout)
    if not path.is_absolute():
        path = root / path
    return path.resolve()


def _worktree_lock_path(repo_root: Path) -> Path:
    root = git_root(repo_root)
    stdout = require_git_stdout(
        root,
        "rev-parse",
        "--git-path",
        _WORKTREE_LOCK_NAME,
        error="cannot locate mutation worktree lock",
    )
    path = Path(stdout)
    if not path.is_absolute():
        path = root / path
    return path.resolve()


@contextmanager
def _serialized_worktree_state(repo_root: Path) -> Iterator[None]:
    lock_path = _worktree_lock_path(repo_root)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as handle:
        _lock_file(handle)
        try:
            yield
        finally:
            _unlock_file(handle)


def tracked_repository_path(path: Path) -> tuple[Path, Path] | None:
    """Return ``(repo_root, relative_path)`` when ``path`` is tracked by git."""
    resolved = path.resolve()
    candidate = _find_worktree_root(resolved)
    if candidate is None:
        return None
    result = run_git(candidate, "rev-parse", "--show-toplevel")
    if result.returncode != 0 or not result.stdout.strip():
        raise MutationWorkspaceError(
            f"cannot resolve repository for tracked path {resolved}: "
            f"{result.stderr.strip()}"
        )
    stdout = result.stdout.strip()
    if "\n" in stdout or "\r" in stdout:
        raise MutationWorkspaceError(
            f"cannot resolve repository for tracked path {resolved}: "
            "unexpected multiline git output"
        )
    repo_root = Path(stdout).resolve()
    if repo_root != candidate:
        raise MutationWorkspaceError(
            f"repository root mismatch for tracked path {resolved}: "
            f"expected {candidate}, got {repo_root}"
        )
    if not resolved.is_relative_to(repo_root):
        return None
    relative = resolved.relative_to(repo_root)
    tracked = run_git(
        repo_root,
        "ls-files",
        "--error-unmatch",
        "--",
        relative.as_posix(),
    )
    if tracked.returncode == 1:
        _reject_tracked_inode_alias(repo_root, resolved)
        return None
    if tracked.returncode != 0:
        raise MutationWorkspaceError(
            f"cannot determine whether path is tracked {relative}: "
            f"{tracked.stderr.strip()}"
        )
    return repo_root, relative


def _reject_tracked_inode_alias(repo_root: Path, path: Path) -> None:
    target_stat = path.stat()
    result = run_git(repo_root, "ls-files", "-z")
    if result.returncode != 0:
        raise MutationWorkspaceError(
            f"cannot inspect tracked paths for inode aliases: {result.stderr.strip()}"
        )
    for raw_path in result.stdout.split("\0"):
        if not raw_path:
            continue
        if "\n" in raw_path or "\r" in raw_path:
            raise MutationWorkspaceError(
                "cannot inspect tracked paths: unexpected multiline git output"
            )
        tracked_path = repo_root / raw_path
        try:
            tracked_stat = tracked_path.lstat()
        except FileNotFoundError:
            continue
        if (
            tracked_stat.st_dev == target_stat.st_dev
            and tracked_stat.st_ino == target_stat.st_ino
        ):
            raise MutationWorkspaceError(
                f"untracked mutation target aliases tracked path: {path} -> {raw_path}"
            )


def relative_target(repo_root: Path, target: Path | str) -> Path:
    candidate = Path(target)
    if not candidate.is_absolute():
        candidate = repo_root / candidate
    resolved = candidate.resolve()
    if not resolved.is_relative_to(repo_root):
        raise MutationWorkspaceError(f"mutation target escapes repository: {target}")
    if not resolved.is_file():
        raise MutationWorkspaceError(f"mutation target is not a file: {resolved}")
    relative = resolved.relative_to(repo_root)
    tracked = run_git(
        repo_root,
        "ls-files",
        "--error-unmatch",
        "--",
        relative.as_posix(),
    )
    if tracked.returncode == 1:
        raise MutationWorkspaceError(f"mutation target is not tracked by git: {relative}")
    if tracked.returncode != 0:
        raise MutationWorkspaceError(
            f"cannot verify mutation target {relative}: {tracked.stderr.strip()}"
        )
    return relative


def enclosing_checkout(path: Path) -> Path | None:
    """Return the nearest ancestor of ``path`` (or ``path``) that holds a ``.git`` entry."""
    resolved = path.resolve()
    for candidate in (resolved, *resolved.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def scratch_directory(repo_root: Path) -> Path:
    """Return the external scratch directory for ``repo_root``.

    Worktrees must never live under any clone (universal.md MUST NOT 6): every
    recursive filesystem walk of the clone would multiply its findings. The
    default is a sibling of the checkout. A checkout nested inside another
    checkout would put that sibling inside the outer clone, so it falls back
    to ``~/worktrees``.
    """
    root = repo_root.resolve()
    sibling = root.parent / f"{root.name}{SCRATCH_DIRECTORY_SUFFIX}"
    if enclosing_checkout(root.parent) is None:
        return sibling
    digest = hashlib.sha256(str(root).encode("utf-8")).hexdigest()[:8]
    return Path.home() / "worktrees" / f"{root.name}-{digest}{SCRATCH_DIRECTORY_SUFFIX}"


def allowed_scratch_roots(repo_root: Path) -> tuple[Path, ...]:
    """Return every directory recovery may remove a scratch worktree from."""
    return (
        scratch_directory(repo_root),
        (repo_root / LEGACY_SCRATCH_DIRECTORY).resolve(),
    )


def add_worktree(repo_root: Path, scratch_root: Path) -> None:
    enclosing = enclosing_checkout(scratch_root.parent)
    if enclosing is not None:
        raise MutationWorkspaceError(
            f"refusing to create mutation worktree inside the clone {enclosing}: {scratch_root}"
        )
    scratch_root.parent.mkdir(parents=True, exist_ok=True)
    with _serialized_worktree_state(repo_root):
        pruned = run_git(repo_root, "worktree", "prune")
        if pruned.returncode != 0:
            raise MutationWorkspaceError(
                f"git worktree prune failed: {pruned.stderr.strip()}"
            )
        result = run_git(
            repo_root,
            "worktree",
            "add",
            "--detach",
            str(scratch_root),
            "HEAD",
        )
    if result.returncode != 0:
        raise MutationWorkspaceError(
            f"git worktree add failed for {scratch_root}: {result.stderr.strip()}"
        )


def _require_scratch_path(repo_root: Path, scratch_root: Path, action: str) -> Path:
    scratch = scratch_root.resolve()
    allowed_roots = allowed_scratch_roots(repo_root)
    if not any(scratch != root and scratch.is_relative_to(root) for root in allowed_roots):
        raise MutationWorkspaceError(
            f"refusing to {action} mutation worktree outside {allowed_roots[0]}: {scratch}"
        )
    return scratch


def _unlock_hint(stderr: str, scratch: Path) -> str:
    if "locked" not in stderr:
        return ""
    return f" (if no process holds it, run `git worktree unlock {scratch}`)"


def remove_worktree(repo_root: Path, scratch_root: Path) -> None:
    scratch = _require_scratch_path(repo_root, scratch_root, "remove")

    with _serialized_worktree_state(repo_root):
        registered = _registered_worktrees_unlocked(repo_root)
        if scratch in registered:
            result = run_git(repo_root, "worktree", "remove", "--force", str(scratch))
            if result.returncode != 0:
                raise MutationWorkspaceError(
                    f"git worktree remove failed for {scratch}: {result.stderr.strip()}"
                    f"{_unlock_hint(result.stderr, scratch)}"
                )
        elif scratch.exists():
            shutil.rmtree(scratch)

        if scratch.exists() or scratch in _registered_worktrees_unlocked(repo_root):
            raise MutationWorkspaceError(
                f"mutation worktree cleanup is incomplete: {scratch}"
            )
        with suppress(OSError):
            scratch.parent.rmdir()


def _lock_reason_unlocked(repo_root: Path, scratch: Path) -> str | None:
    result = run_git(repo_root, "worktree", "list", "--porcelain", "-z")
    if result.returncode != 0:
        raise MutationWorkspaceError(
            f"cannot list registered worktrees: {result.stderr.strip()}"
        )
    current: Path | None = None
    for field in result.stdout.split("\0"):
        if field.startswith("worktree "):
            current = Path(field.removeprefix("worktree ")).resolve()
        elif field.startswith("locked") and current == scratch:
            return field.removeprefix("locked").strip()
    return None


def unlock_stale_worktree(repo_root: Path, scratch_root: Path) -> bool:
    """Unlock a scratch worktree that an interrupted ``git worktree add`` left locked.

    Git holds the lock with reason ``initializing`` while it populates a new
    worktree and clears it on success, so the reason persists only after the
    process died mid-setup. Any other lock, or a path outside the harness's
    scratch roots, is left alone. Returns True when a lock was cleared.
    """
    scratch = _require_scratch_path(repo_root, scratch_root, "unlock")
    with _serialized_worktree_state(repo_root):
        if _lock_reason_unlocked(repo_root, scratch) != STALE_LOCK_REASON:
            return False
        result = run_git(repo_root, "worktree", "unlock", str(scratch))
        if result.returncode != 0:
            raise MutationWorkspaceError(
                f"git worktree unlock failed for {scratch}: {result.stderr.strip()}"
            )
    return True


def registered_worktrees(repo_root: Path) -> set[Path]:
    with _serialized_worktree_state(repo_root):
        return _registered_worktrees_unlocked(repo_root)


def _registered_worktrees_unlocked(repo_root: Path) -> set[Path]:
    result = run_git(repo_root, "worktree", "list", "--porcelain", "-z")
    if result.returncode != 0:
        raise MutationWorkspaceError(
            f"cannot list registered worktrees: {result.stderr.strip()}"
        )
    prefix = "worktree "
    return {
        Path(field.removeprefix(prefix)).resolve()
        for field in result.stdout.split("\0")
        if field.startswith(prefix)
    }
