"""Isolate mutation harness edits in disposable git worktrees.

The active worktree is never mutated. A marker in the worktree-specific git
directory records the scratch worktree and every affected tracked path. Normal
completion, exceptions, timeouts, SIGINT, and SIGTERM remove the scratch
worktree and marker. SIGKILL leaves the marker so pre-push can fail before
running validators from an unverified tree.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import uuid
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from types import FrameType
from typing import Any, TextIO

EXIT_OK = 0
EXIT_BLOCKED = 1
EXIT_CONFIG_ERROR = 2
EXIT_EXTERNAL_ERROR = 3
MARKER_SCHEMA_VERSION = 1
MARKER_DIRECTORY_NAME = "mutation-active"
SCRATCH_DIRECTORY = Path(".pytest_cache") / "mutation-worktrees"


class MutationWorkspaceError(RuntimeError):
    """Raised when mutation isolation or cleanup cannot be proven."""


class MutationInterrupted(SystemExit):
    """Raised on a catchable termination signal so cleanup can run."""


@dataclass(frozen=True, slots=True)
class TargetSnapshot:
    """Hash of one active-worktree path before the mutation run."""

    path: str
    sha256: str


@dataclass(frozen=True, slots=True)
class MutationWorkspace:
    """Scratch worktree and durable marker for one mutation run."""

    root: Path
    marker_path: Path
    targets: tuple[TargetSnapshot, ...]


def _run_git(repo_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def _git_root(path: Path) -> Path:
    result = _run_git(path, "rev-parse", "--show-toplevel")
    if result.returncode != 0 or not result.stdout.strip():
        raise MutationWorkspaceError(
            f"cannot find git worktree root from {path}: {result.stderr.strip()}"
        )
    return Path(result.stdout.strip()).resolve()


def marker_directory(repo_root: Path) -> Path:
    """Return the worktree-specific mutation marker directory."""
    root = _git_root(repo_root)
    result = _run_git(root, "rev-parse", "--git-path", MARKER_DIRECTORY_NAME)
    if result.returncode != 0 or not result.stdout.strip():
        raise MutationWorkspaceError(
            f"cannot locate git marker directory: {result.stderr.strip()}"
        )
    path = Path(result.stdout.strip())
    if not path.is_absolute():
        path = root / path
    return path.resolve()


def tracked_repository_path(path: Path) -> tuple[Path, Path] | None:
    """Return ``(repo_root, relative_path)`` when ``path`` is tracked by git."""
    resolved = path.resolve()
    result = _run_git(resolved.parent, "rev-parse", "--show-toplevel")
    if result.returncode != 0 or not result.stdout.strip():
        return None
    repo_root = Path(result.stdout.strip()).resolve()
    if not resolved.is_relative_to(repo_root):
        return None
    relative = resolved.relative_to(repo_root)
    tracked = _run_git(
        repo_root,
        "ls-files",
        "--error-unmatch",
        "--",
        relative.as_posix(),
    )
    if tracked.returncode != 0:
        return None
    return repo_root, relative


def _relative_target(repo_root: Path, target: Path | str) -> Path:
    candidate = Path(target)
    if not candidate.is_absolute():
        candidate = repo_root / candidate
    resolved = candidate.resolve()
    if not resolved.is_relative_to(repo_root):
        raise MutationWorkspaceError(f"mutation target escapes repository: {target}")
    if not resolved.is_file():
        raise MutationWorkspaceError(f"mutation target is not a file: {resolved}")
    return resolved.relative_to(repo_root)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def purge_bytecode(root: Path) -> None:
    """Delete Python bytecode caches below an isolated worktree path."""
    for pycache in sorted(root.rglob("__pycache__"), reverse=True):
        if pycache.is_dir():
            shutil.rmtree(pycache)


def _snapshot_targets(
    repo_root: Path, targets: Sequence[Path | str]
) -> tuple[TargetSnapshot, ...]:
    if not targets:
        raise MutationWorkspaceError("at least one mutation target is required")
    relative_paths = sorted({_relative_target(repo_root, target) for target in targets})
    return tuple(
        TargetSnapshot(path=path.as_posix(), sha256=_sha256(repo_root / path))
        for path in relative_paths
    )


def _marker_payload(
    repo_root: Path,
    scratch_root: Path,
    targets: Sequence[TargetSnapshot],
) -> dict[str, Any]:
    return {
        "schema_version": MARKER_SCHEMA_VERSION,
        "pid": os.getpid(),
        "repo_root": str(repo_root),
        "scratch_worktree": str(scratch_root),
        "targets": [
            {"path": target.path, "sha256": target.sha256} for target in targets
        ],
    }


def _write_marker(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def _add_worktree(repo_root: Path, scratch_root: Path) -> None:
    scratch_root.parent.mkdir(parents=True, exist_ok=True)
    result = _run_git(
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


def _remove_worktree(repo_root: Path, scratch_root: Path) -> None:
    result = _run_git(repo_root, "worktree", "remove", "--force", str(scratch_root))
    if result.returncode != 0:
        raise MutationWorkspaceError(
            f"git worktree remove failed for {scratch_root}: {result.stderr.strip()}"
        )


def _validate_active_targets(
    repo_root: Path, targets: Sequence[TargetSnapshot]
) -> list[tuple[str, str]]:
    states: list[tuple[str, str]] = []
    for target in targets:
        path = repo_root / target.path
        if not path.is_file():
            states.append((target.path, "MISSING"))
        elif _sha256(path) != target.sha256:
            states.append((target.path, "MODIFIED"))
        else:
            states.append((target.path, "UNCHANGED"))
    return states


def _require_active_targets_unchanged(
    repo_root: Path, targets: Sequence[TargetSnapshot]
) -> None:
    changed = [
        f"{path} [{state}]"
        for path, state in _validate_active_targets(repo_root, targets)
        if state != "UNCHANGED"
    ]
    if changed:
        joined = ", ".join(changed)
        raise MutationWorkspaceError(
            f"active mutation targets changed during isolated run: {joined}"
        )


def _raise_for_signal(signum: int, _frame: FrameType | None) -> None:
    raise MutationInterrupted(128 + signum)


def _install_signal_handlers() -> dict[int, Any]:
    previous: dict[int, Any] = {}
    for signum in (signal.SIGINT, signal.SIGTERM):
        try:
            previous[signum] = signal.getsignal(signum)
            signal.signal(signum, _raise_for_signal)
        except ValueError:
            return {}
    return previous


def _restore_signal_handlers(previous: dict[int, Any]) -> None:
    for signum, handler in previous.items():
        signal.signal(signum, handler)


@contextmanager
def isolated_mutation_worktree(
    repo_root: Path,
    targets: Sequence[Path | str],
) -> Iterator[MutationWorkspace]:
    """Yield a detached worktree where mutation targets can be changed safely."""
    root = _git_root(repo_root)
    snapshots = _snapshot_targets(root, targets)
    run_id = uuid.uuid4().hex
    scratch_root = root / SCRATCH_DIRECTORY / run_id
    marker_path = marker_directory(root) / f"{run_id}.json"
    workspace = MutationWorkspace(
        root=scratch_root,
        marker_path=marker_path,
        targets=snapshots,
    )
    payload = _marker_payload(root, scratch_root, snapshots)

    _write_marker(marker_path, payload)
    try:
        _add_worktree(root, scratch_root)
    except BaseException:
        marker_path.unlink(missing_ok=True)
        raise

    previous_handlers = _install_signal_handlers()
    try:
        yield workspace
    finally:
        _restore_signal_handlers(previous_handlers)
        _require_active_targets_unchanged(root, snapshots)
        _remove_worktree(root, scratch_root)
        marker_path.unlink()


def _read_marker(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MutationWorkspaceError(f"cannot read marker {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise MutationWorkspaceError(f"marker is not a JSON object: {path}")
    if payload.get("schema_version") != MARKER_SCHEMA_VERSION:
        raise MutationWorkspaceError(f"unsupported marker schema: {path}")
    return payload


def _read_target_snapshots(payload: dict[str, Any], marker: Path) -> tuple[TargetSnapshot, ...]:
    raw_targets = payload.get("targets")
    if not isinstance(raw_targets, list) or not raw_targets:
        raise MutationWorkspaceError(f"marker has no targets: {marker}")

    targets: list[TargetSnapshot] = []
    for raw in raw_targets:
        if not isinstance(raw, dict):
            raise MutationWorkspaceError(f"marker target is not an object: {marker}")
        path = raw.get("path")
        digest = raw.get("sha256")
        if not isinstance(path, str) or not path:
            raise MutationWorkspaceError(f"marker target path is invalid: {marker}")
        if not isinstance(digest, str) or len(digest) != 64:
            raise MutationWorkspaceError(f"marker target hash is invalid: {marker}")
        relative = Path(path)
        if relative.is_absolute() or ".." in relative.parts:
            raise MutationWorkspaceError(f"marker target escapes repository: {path}")
        targets.append(TargetSnapshot(path=relative.as_posix(), sha256=digest))
    return tuple(targets)


def _marker_files(repo_root: Path) -> list[Path]:
    directory = marker_directory(repo_root)
    if not directory.exists():
        return []
    return sorted(path for path in directory.iterdir() if path.is_file())


def _pid_is_running(raw_pid: object) -> bool:
    if isinstance(raw_pid, bool) or not isinstance(raw_pid, int) or raw_pid <= 0:
        return False
    try:
        os.kill(raw_pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _print_marker(
    repo_root: Path,
    marker: Path,
    payload: dict[str, Any],
    stream: TextIO,
) -> None:
    targets = _read_target_snapshots(payload, marker)
    process_state = "running" if _pid_is_running(payload.get("pid")) else "not running"
    print(f"marker: {marker}", file=stream)
    print(f"process: {payload.get('pid')} ({process_state})", file=stream)
    print(f"scratch worktree: {payload.get('scratch_worktree')}", file=stream)
    print("affected tracked paths:", file=stream)
    for path, state in _validate_active_targets(repo_root, targets):
        print(f"  - {path} [{state}]", file=stream)


def check_markers(repo_root: Path, stream: TextIO | None = None) -> int:
    """Fail closed when any mutation workspace marker remains."""
    output = stream or sys.stderr
    root = _git_root(repo_root)
    markers = _marker_files(root)
    if not markers:
        return EXIT_OK

    print("ERROR: incomplete mutation harness state; push blocked.", file=output)
    for marker in markers:
        try:
            payload = _read_marker(marker)
            _print_marker(root, marker, payload, output)
        except MutationWorkspaceError as exc:
            print(f"marker: {marker} [INVALID: {exc}]", file=output)
    print(
        "Run `uv run --frozen python -m scripts.testing.mutation_workspace recover` "
        "after the mutation process stops.",
        file=output,
    )
    return EXIT_BLOCKED


def _scratch_root_from_marker(repo_root: Path, payload: dict[str, Any], marker: Path) -> Path:
    raw_path = payload.get("scratch_worktree")
    if not isinstance(raw_path, str) or not raw_path:
        raise MutationWorkspaceError(f"marker scratch worktree is invalid: {marker}")
    scratch = Path(raw_path).resolve()
    allowed_root = (repo_root / SCRATCH_DIRECTORY).resolve()
    if not scratch.is_relative_to(allowed_root):
        raise MutationWorkspaceError(
            f"marker scratch worktree is outside {allowed_root}: {scratch}"
        )
    return scratch


def recover_markers(repo_root: Path, stream: TextIO | None = None) -> int:
    """Remove stale scratch worktrees after verifying active targets."""
    output = stream or sys.stderr
    root = _git_root(repo_root)
    markers = _marker_files(root)
    failures = False
    for marker in markers:
        try:
            payload = _read_marker(marker)
            if _pid_is_running(payload.get("pid")):
                raise MutationWorkspaceError(
                    f"mutation process {payload.get('pid')} is still running"
                )
            targets = _read_target_snapshots(payload, marker)
            _require_active_targets_unchanged(root, targets)
            scratch = _scratch_root_from_marker(root, payload, marker)
            if scratch.exists():
                _remove_worktree(root, scratch)
            else:
                _run_git(root, "worktree", "prune")
            marker.unlink()
            print(f"recovered mutation workspace: {scratch}", file=output)
        except (MutationWorkspaceError, OSError) as exc:
            failures = True
            print(f"ERROR: cannot recover {marker}: {exc}", file=output)
    return EXIT_BLOCKED if failures else EXIT_OK


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("check", "recover"), nargs="?", default="check")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "recover":
            return recover_markers(args.repo_root)
        return check_markers(args.repo_root)
    except MutationWorkspaceError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_EXTERNAL_ERROR


if __name__ == "__main__":
    sys.exit(main())
