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
import sys
import uuid
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from types import FrameType
from typing import Any, TextIO

from scripts.testing import mutation_workspace_git

SCRATCH_DIRECTORY = mutation_workspace_git.SCRATCH_DIRECTORY
MutationWorkspaceError = mutation_workspace_git.MutationWorkspaceError
marker_directory = mutation_workspace_git.marker_directory
tracked_repository_path = mutation_workspace_git.tracked_repository_path
_add_worktree = mutation_workspace_git.add_worktree
_git_root = mutation_workspace_git.git_root
_relative_target = mutation_workspace_git.relative_target
_remove_worktree = mutation_workspace_git.remove_worktree
_require_git_stdout = mutation_workspace_git.require_git_stdout
_run_git = mutation_workspace_git.run_git

EXIT_OK = 0
EXIT_BLOCKED = 1
EXIT_EXTERNAL_ERROR = 3
MARKER_SCHEMA_VERSION = 1


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


@dataclass(slots=True)
class _SignalState:
    cleaning_up: bool = False
    pending_signal: int | None = None


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


def _require_targets_match_head(
    repo_root: Path, targets: Sequence[TargetSnapshot]
) -> None:
    for target in targets:
        status = _run_git(
            repo_root,
            "status",
            "--porcelain=v1",
            "--untracked-files=no",
            "--",
            target.path,
        )
        if status.returncode != 0:
            raise MutationWorkspaceError(
                f"cannot inspect mutation target state {target.path}: "
                f"{status.stderr.strip()}"
            )
        if status.stdout:
            raise MutationWorkspaceError(
                f"mutation target has uncommitted changes: {target.path}. "
                "Commit or stash it before running the harness."
            )
        head_object = _require_git_stdout(
            repo_root,
            "rev-parse",
            f"HEAD:{target.path}",
            error=f"cannot read mutation target from HEAD {target.path}",
        )
        active_object = _require_git_stdout(
            repo_root,
            "hash-object",
            "--",
            target.path,
            error=f"cannot hash active mutation target {target.path}",
        )
        if active_object != head_object:
            raise MutationWorkspaceError(
                f"mutation target has uncommitted changes: {target.path}. "
                "Commit or stash it before running the harness."
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


def _mark_run_finished(path: Path, payload: dict[str, Any]) -> None:
    finished_payload = {**payload, "pid": None}
    replacement = path.with_name(f".{path.name}.{uuid.uuid4().hex}.finished")
    _write_marker(replacement, finished_payload)
    os.replace(replacement, path)


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


def _install_signal_handlers(state: _SignalState) -> dict[int, Any]:
    def handle_signal(signum: int, _frame: FrameType | None) -> None:
        if state.cleaning_up:
            state.pending_signal = signum
            return
        state.cleaning_up = True
        raise MutationInterrupted(128 + signum)

    previous: dict[int, Any] = {}
    for signum in (signal.SIGINT, signal.SIGTERM):
        try:
            previous[signum] = signal.getsignal(signum)
            signal.signal(signum, handle_signal)
        except ValueError:
            return {}
    return previous


def _restore_signal_handlers(previous: dict[int, Any]) -> None:
    for signum, handler in previous.items():
        signal.signal(signum, handler)


def _cleanup_workspace(
    repo_root: Path,
    scratch_root: Path,
    marker_path: Path,
    snapshots: Sequence[TargetSnapshot],
    payload: dict[str, Any],
    signal_state: _SignalState,
    body_error: BaseException | None,
) -> None:
    signal_state.cleaning_up = True
    cleanup_errors: list[str] = []
    try:
        _remove_worktree(repo_root, scratch_root)
    except (MutationWorkspaceError, OSError) as exc:
        cleanup_errors.append(str(exc))
    try:
        _require_active_targets_unchanged(repo_root, snapshots)
    except (MutationWorkspaceError, OSError) as exc:
        cleanup_errors.append(str(exc))

    if not cleanup_errors:
        try:
            marker_path.unlink(missing_ok=True)
        except OSError as exc:
            cleanup_errors.append(f"cannot remove mutation marker: {exc}")

    if cleanup_errors:
        try:
            _mark_run_finished(marker_path, payload)
        except OSError as exc:
            cleanup_errors.append(f"cannot mark mutation run finished: {exc}")
        if body_error is None:
            if signal_state.pending_signal is not None:
                raise MutationInterrupted(128 + signal_state.pending_signal)
            raise MutationWorkspaceError("; ".join(cleanup_errors))
    if body_error is None and signal_state.pending_signal is not None:
        raise MutationInterrupted(128 + signal_state.pending_signal)


@contextmanager
def isolated_mutation_worktree(
    repo_root: Path,
    targets: Sequence[Path | str],
) -> Iterator[MutationWorkspace]:
    """Yield a detached worktree where mutation targets can be changed safely."""
    root = _git_root(repo_root)
    snapshots = _snapshot_targets(root, targets)
    _require_targets_match_head(root, snapshots)
    run_id = uuid.uuid4().hex
    scratch_parent = (root / SCRATCH_DIRECTORY).resolve()
    if not scratch_parent.is_relative_to(root):
        raise MutationWorkspaceError(
            f"mutation scratch directory escapes repository: {scratch_parent}"
        )
    scratch_root = scratch_parent / run_id
    marker_path = marker_directory(root) / f"{run_id}.json"
    workspace = MutationWorkspace(
        root=scratch_root,
        marker_path=marker_path,
        targets=snapshots,
    )
    payload = _marker_payload(root, scratch_root, snapshots)

    signal_state = _SignalState()
    previous_handlers = _install_signal_handlers(signal_state)
    body_error: BaseException | None = None
    cleanup_completed = False
    try:
        try:
            _write_marker(marker_path, payload)
            _add_worktree(root, scratch_root)
            yield workspace
        except BaseException as exc:
            body_error = exc
            raise
        finally:
            _cleanup_workspace(
                root,
                scratch_root,
                marker_path,
                snapshots,
                payload,
                signal_state,
                body_error,
            )
            cleanup_completed = True
    except MutationInterrupted as exc:
        if not cleanup_completed:
            _cleanup_workspace(
                root,
                scratch_root,
                marker_path,
                snapshots,
                payload,
                signal_state,
                exc,
            )
        raise
    finally:
        _restore_signal_handlers(previous_handlers)


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
    try:
        return sorted(directory.iterdir())
    except FileNotFoundError:
        return []
    except OSError as exc:
        raise MutationWorkspaceError(
            f"cannot inspect mutation marker directory {directory}: {exc}"
        ) from exc


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


def recover_marker(
    repo_root: Path,
    marker: Path,
    stream: TextIO | None = None,
) -> int:
    """Recover one stale marker after verifying active targets."""
    output = stream or sys.stderr
    root = _git_root(repo_root)
    marker_root = marker_directory(root)
    resolved_marker = marker.resolve()
    if resolved_marker.parent != marker_root:
        print(f"ERROR: marker is outside {marker_root}: {marker}", file=output)
        return EXIT_BLOCKED
    try:
        payload = _read_marker(resolved_marker)
        if _pid_is_running(payload.get("pid")):
            raise MutationWorkspaceError(
                f"mutation process {payload.get('pid')} is still running"
            )
        targets = _read_target_snapshots(payload, resolved_marker)
        _require_active_targets_unchanged(root, targets)
        scratch = _scratch_root_from_marker(root, payload, resolved_marker)
        _remove_worktree(root, scratch)
        resolved_marker.unlink(missing_ok=True)
        print(f"recovered mutation workspace: {scratch}", file=output)
    except (MutationWorkspaceError, OSError) as exc:
        print(f"ERROR: cannot recover {resolved_marker}: {exc}", file=output)
        return EXIT_BLOCKED
    return EXIT_OK


def recover_markers(repo_root: Path, stream: TextIO | None = None) -> int:
    """Remove stale scratch worktrees after verifying active targets."""
    output = stream or sys.stderr
    failures = [
        marker
        for marker in _marker_files(_git_root(repo_root))
        if recover_marker(repo_root, marker, output) != EXIT_OK
    ]
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
