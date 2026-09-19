"""Filesystem and Git index access for context output validation."""

from __future__ import annotations

import subprocess
from pathlib import Path

from path_validation import get_repo_root, validate_path_within_repo


def _resolved_repo_root(repo_root: Path | None) -> Path:
    """Return an absolute repository root for filesystem and Git reads."""
    return (repo_root or get_repo_root()).resolve()


def _repo_relative_path(path: Path, repo_root: Path) -> str:
    """Return a validated path relative to the repository root."""
    return path.resolve().relative_to(repo_root.resolve()).as_posix()


def _read_staged_text(path: Path, repo_root: Path) -> str | None:
    """Read a UTF-8 file from the Git index, returning None when absent."""
    relative_path = _repo_relative_path(path, repo_root)
    try:
        result = subprocess.run(
            ["git", "show", f":{relative_path}"],
            cwd=repo_root,
            capture_output=True,
            check=False,
        )
    except OSError as error:
        raise RuntimeError("Unable to read the Git index") from error
    if result.returncode != 0:
        return None
    try:
        return result.stdout.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f"Git index file is not UTF-8: {path}") from error


def _staged_paths_under(directory: Path, repo_root: Path) -> set[str]:
    """Return index paths below a validated directory."""
    relative_directory = _repo_relative_path(directory, repo_root)
    prefix = "" if relative_directory == "." else f"{relative_directory.rstrip('/')}/"
    try:
        result = subprocess.run(
            ["git", "ls-files", "--cached", "-z", "--", relative_directory],
            cwd=repo_root,
            capture_output=True,
            check=False,
        )
    except OSError as error:
        raise RuntimeError("Unable to list the Git index") from error
    if result.returncode != 0:
        raise RuntimeError("Unable to list the Git index")
    paths: set[str] = set()
    for raw_path in result.stdout.split(b"\0"):
        if not raw_path:
            continue
        path = raw_path.decode("utf-8")
        if not prefix or path.startswith(prefix):
            paths.add(path)
    return paths


def _detail_names(detail_dir: Path, repo_root: Path, staged: bool) -> set[str]:
    """Return direct detail entries from the index or worktree."""
    if staged:
        relative_dir = _repo_relative_path(detail_dir, repo_root)
        prefix = "" if relative_dir == "." else f"{relative_dir.rstrip('/')}/"
        return {
            path[len(prefix) :].split("/", 1)[0]
            for path in _staged_paths_under(detail_dir, repo_root)
            if not prefix or path.startswith(prefix)
        }
    if not detail_dir.exists() or not detail_dir.is_dir():
        return set()
    entries = list(detail_dir.iterdir())
    for entry in entries:
        validate_path_within_repo(entry, repo_root)
    return {entry.name for entry in entries}


def _output_files(output_root: Path, repo_root: Path, staged: bool) -> set[str]:
    """Return all file paths below an output root."""
    if staged:
        return _staged_paths_under(output_root, repo_root)
    if not output_root.exists():
        return set()
    if not output_root.is_dir():
        return {_repo_relative_path(output_root, repo_root)}
    files: set[str] = set()
    for path in output_root.rglob("*"):
        validate_path_within_repo(path, repo_root)
        if not path.is_dir():
            files.add(_repo_relative_path(path, repo_root))
    return files


def _read_text(path: Path, repo_root: Path, staged: bool) -> str | None:
    """Read a UTF-8 file from the index or worktree."""
    if staged:
        return _read_staged_text(path, repo_root)
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8")


def _manifest_path_value(value: object, field: str) -> str:
    """Validate a manifest path value before resolving it."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Manifest field '{field}' must be a non-empty string")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise PermissionError(f"Unsafe manifest path in '{field}': {value}")
    return path.as_posix()
