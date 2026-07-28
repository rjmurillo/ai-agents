#!/usr/bin/env python3
"""orphan-ref-validator file walking + secret denylist.

Owns the recursive-walk policy for ``scan.py``: which directory names to
prune, which file suffixes to scan, which file-name patterns are secrets,
and the per-file size cap. Symlink-followed directories that escape the
repository root are skipped here so the upstream ``scan_file`` path never
sees them.

``EXCLUDE_DIR_NAMES`` prunes five vendor/VCS directory names
(``node_modules``, ``.git``, ``worktrees``, ``cache``, ``__pycache__``)
plus ``references`` and ``templates`` (skill-progressive-disclosure
subtrees that legitimately cite external entities and would otherwise
produce high-noise findings).
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

LOGGER = logging.getLogger("orphan_ref_validator")

SCAN_FILE_SUFFIXES: tuple[str, ...] = (".md", ".json", ".yaml", ".yml")

# Five vendor/VCS names plus two skill-progressive-disclosure subtrees.
# Frozen for safety.
EXCLUDE_DIR_NAMES: frozenset[str] = frozenset({
    "node_modules", ".git", "worktrees", "cache", "__pycache__",
    "references", "templates",
})

# Filename patterns that match secrets and credentials. Filenames matching
# any pattern are skipped by the walker.
SECRET_DENYLIST_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^\.env"),
    re.compile(r"^secrets\."),
    re.compile(r"\.key$"),
    re.compile(r"\.pem$"),
    re.compile(r"\.pfx$"),
    re.compile(r"\.p12$"),
    re.compile(r"^id_rsa($|\.pub$)"),
    re.compile(r"^id_ed25519($|\.pub$)"),
    re.compile(r"^id_ecdsa($|\.pub$)"),
    re.compile(r"^id_dsa($|\.pub$)"),
    re.compile(r"^\.netrc$"),
    re.compile(r"^\.npmrc$"),
    re.compile(r"^\.pypirc$"),
    re.compile(r"^credentials$"),
)

MAX_FILE_BYTES: int = 5 * 1024 * 1024


@dataclass(frozen=True)
class WalkProblem:
    target: Path
    reason: str
    error_type: str = "config"


def is_secret_path(path: Path) -> bool:
    """Return True if a file's name matches any secret denylist pattern."""
    name = path.name
    return any(p.search(name) for p in SECRET_DENYLIST_PATTERNS)


def is_safe_subdirectory(entry: Path, repo_root: Path) -> bool:
    """Return True if ``entry`` (a directory) is safe to recurse into.

    Skips entries whose resolved path falls outside ``repo_root``. This
    prevents a symlink under an allowed target from leading the walker
    into ``/etc``, ``$HOME``, or any other tree the developer did not
    intend to scan. Skips by reporting False; the caller logs and
    continues. CWE-22 / CWE-59 hardening.
    """
    if entry.is_symlink():
        try:
            resolved = entry.resolve()
        except (OSError, RuntimeError) as exc:
            LOGGER.warning("could not resolve symlink %s: %s", entry, exc)
            return False
        try:
            resolved.relative_to(repo_root.resolve())
        except ValueError:
            LOGGER.warning(
                "skipping %s: symlink resolves outside repo root", entry
            )
            return False
    return True


def collect_walk_targets(target: Path, repo_root: Path) -> tuple[list[Path], list[WalkProblem]]:
    """Return candidate files plus incomplete-scan problems under ``target``."""
    if target.is_symlink():
        problem = _unsafe_symlink_problem(target, repo_root)
        if problem is not None:
            return [], [problem]
    try:
        target.resolve().relative_to(repo_root.resolve())
    except (OSError, ValueError) as exc:
        reason = f"target outside repo root ({exc})"
        LOGGER.warning("skipping %s: %s", target, reason)
        return [], [WalkProblem(target, reason)]
    if target.is_file():
        return _maybe_collect_file(target, repo_root, strict=True)
    files: list[Path] = []
    problems: list[WalkProblem] = []
    visited: set[Path] = set()
    _collect_dir_pruned(target, repo_root, visited, files, problems)
    return files, problems


def walk_targets(target: Path, repo_root: Path) -> Iterable[Path]:
    """Yield candidate files under ``target`` (or just the target if it is a file).

    Defense in depth: ``scan()`` already verifies repo-root containment
    for every expanded target, but ``walk_targets`` is also a public
    entry point. Reject any target whose canonical path resolves outside
    ``repo_root`` here too so a direct programmatic call cannot bypass
    the containment check.

    Recurses with ``iterdir`` and prunes ``EXCLUDE_DIR_NAMES`` at the
    directory level rather than ``rglob('*')`` + post-filter, so excluded
    subtrees (``node_modules``, ``.git``, ``worktrees``, ``cache``,
    ``__pycache__``, ``references``, ``templates``) are never entered.

    Symlink targets (file or directory) are checked against ``repo_root``
    after ``resolve()``; entries that escape the repository root are
    skipped (CWE-22 / CWE-59 hardening). The walker also tracks visited
    canonical paths to defend against in-repo symlink cycles.
    """
    files, _problems = collect_walk_targets(target, repo_root)
    yield from files


def _iter_dir_pruned(
    directory: Path, repo_root: Path, visited: set[Path]
) -> Iterable[Path]:
    """Walk ``directory`` recursively, pruning excluded directory names,
    refusing to follow symlinks that escape ``repo_root``, and stopping
    at any directory whose canonical path was already visited (cycle
    guard for in-repo symlink loops)."""
    try:
        canonical = directory.resolve()
    except (OSError, RuntimeError) as exc:
        LOGGER.warning("could not resolve %s: %s", directory, exc)
        return
    if canonical in visited:
        LOGGER.warning("skipping %s: symlink cycle detected", directory)
        return
    visited.add(canonical)
    try:
        entries = sorted(directory.iterdir(), key=lambda p: str(p))
    except (OSError, PermissionError) as exc:
        LOGGER.warning("could not iterate %s: %s", directory, exc)
        return
    for entry in entries:
        yield from _iter_entry(entry, repo_root, visited)


def _collect_dir_pruned(
    directory: Path,
    repo_root: Path,
    visited: set[Path],
    files: list[Path],
    problems: list[WalkProblem],
) -> None:
    try:
        canonical = directory.resolve()
    except (OSError, RuntimeError) as exc:
        reason = f"could not resolve directory: {exc}"
        LOGGER.warning("could not resolve %s: %s", directory, exc)
        problems.append(WalkProblem(directory, reason))
        return
    if canonical in visited:
        reason = "symlink cycle detected"
        LOGGER.warning("skipping %s: %s", directory, reason)
        problems.append(WalkProblem(directory, reason))
        return
    visited.add(canonical)
    try:
        entries = sorted(directory.iterdir(), key=lambda p: str(p))
    except (OSError, PermissionError) as exc:
        reason = f"could not iterate directory: {exc}"
        LOGGER.warning("could not iterate %s: %s", directory, exc)
        problems.append(WalkProblem(directory, reason, _error_type(exc)))
        return
    for entry in entries:
        _collect_entry(entry, repo_root, visited, files, problems)


def _collect_entry(
    entry: Path,
    repo_root: Path,
    visited: set[Path],
    files: list[Path],
    problems: list[WalkProblem],
) -> None:
    try:
        if entry.is_symlink():
            problem = _unsafe_symlink_problem(entry, repo_root)
            if problem is not None:
                LOGGER.warning("skipping %s: %s", entry, problem.reason)
                problems.append(problem)
                return
        if entry.is_dir():
            if entry.name in EXCLUDE_DIR_NAMES:
                return
            _collect_dir_pruned(entry, repo_root, visited, files, problems)
            return
    except OSError as exc:
        reason = f"could not stat entry: {exc}"
        LOGGER.warning("could not stat %s: %s", entry, exc)
        problems.append(WalkProblem(entry, reason))
        return
    try:
        is_file = entry.is_file()
    except OSError as exc:
        reason = f"could not stat entry: {exc}"
        LOGGER.warning("could not stat %s: %s", entry, exc)
        problems.append(WalkProblem(entry, reason))
        return
    if not is_file:
        return
    collected, entry_problems = _maybe_collect_file(entry, repo_root, strict=False)
    files.extend(collected)
    problems.extend(entry_problems)


def _unsafe_symlink_problem(entry: Path, repo_root: Path) -> WalkProblem | None:
    try:
        resolved = entry.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        return WalkProblem(entry, f"could not resolve symlink: {exc}", _error_type(exc))
    try:
        resolved.relative_to(repo_root.resolve())
    except ValueError:
        return WalkProblem(entry, "symlink resolves outside repo root", "config")
    return None


def _iter_entry(
    entry: Path, repo_root: Path, visited: set[Path]
) -> Iterable[Path]:
    """Yield walkable files from a single directory entry."""
    try:
        if entry.is_dir():
            if entry.name in EXCLUDE_DIR_NAMES:
                return
            if not is_safe_subdirectory(entry, repo_root):
                return
            yield from _iter_dir_pruned(entry, repo_root, visited)
            return
    except OSError as exc:
        LOGGER.warning("could not stat %s: %s", entry, exc)
        return
    if not entry.is_file():
        return
    if entry.suffix not in SCAN_FILE_SUFFIXES:
        return
    yield from _maybe_yield_file(entry, repo_root)


def _maybe_collect_file(
    entry: Path, repo_root: Path, strict: bool
) -> tuple[list[Path], list[WalkProblem]]:
    """Return a candidate file or an incomplete-scan problem."""
    if is_secret_path(entry):
        return [], []
    if entry.suffix not in SCAN_FILE_SUFFIXES:
        if strict:
            reason = f"unsupported file suffix {entry.suffix or '<none>'}"
            LOGGER.warning("skipping %s: %s", entry, reason)
            return [], [WalkProblem(entry, reason)]
        return [], []
    problem = _unsafe_file_problem(entry, repo_root)
    if problem is not None:
        LOGGER.warning("skipping %s: %s", entry, problem.reason)
        return [], [problem]
    size_problem = _size_problem(entry)
    if size_problem is not None:
        LOGGER.warning("skipping %s: %s", entry, size_problem.reason)
        return [], [size_problem]
    return [entry], []


def _maybe_yield_file(entry: Path, repo_root: Path) -> Iterable[Path]:
    """Apply secret denylist, size cap, suffix filter, and post-resolution
    repo-root containment to a candidate file."""
    if is_secret_path(entry):
        return
    if entry.suffix not in SCAN_FILE_SUFFIXES:
        return
    if not _is_safe_file(entry, repo_root):
        return
    if not _within_size_cap(entry):
        return
    yield entry


def _unsafe_file_problem(entry: Path, repo_root: Path) -> WalkProblem | None:
    if not entry.is_symlink():
        return None
    try:
        resolved = entry.resolve()
    except (OSError, RuntimeError) as exc:
        return WalkProblem(entry, f"could not resolve symlink: {exc}")
    try:
        resolved.relative_to(repo_root.resolve())
    except ValueError:
        return WalkProblem(entry, "symlink resolves outside repo root")
    return None


def _is_safe_file(entry: Path, repo_root: Path) -> bool:
    """Return True if ``entry`` resolves under ``repo_root``. A file
    symlink whose target escapes the repo is rejected (CWE-22 / CWE-59)."""
    if not entry.is_symlink():
        return True
    try:
        resolved = entry.resolve()
    except (OSError, RuntimeError) as exc:
        LOGGER.warning("could not resolve symlink %s: %s", entry, exc)
        return False
    try:
        resolved.relative_to(repo_root.resolve())
    except ValueError:
        LOGGER.warning("skipping %s: symlink resolves outside repo root", entry)
        return False
    return True


def _size_problem(entry: Path) -> WalkProblem | None:
    try:
        size = entry.stat().st_size
    except OSError as exc:
        return WalkProblem(entry, f"could not stat file: {exc}", _error_type(exc))
    if size > MAX_FILE_BYTES:
        return WalkProblem(entry, f"exceeds {MAX_FILE_BYTES} bytes", "config")
    return None


def _error_type(exc: BaseException) -> str:
    if isinstance(exc, PermissionError):
        return "auth"
    return "config"


def _within_size_cap(entry: Path) -> bool:
    """Return True if the file is within the 5 MB scan cap."""
    try:
        size = entry.stat().st_size
    except OSError as exc:
        LOGGER.warning("could not stat %s: %s", entry, exc)
        return False
    if size > MAX_FILE_BYTES:
        LOGGER.warning("skipping %s: exceeds %d bytes", entry, MAX_FILE_BYTES)
        return False
    return True
