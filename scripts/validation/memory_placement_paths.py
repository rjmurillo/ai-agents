"""Scope and candidate path resolution for check_memory_placement.py.

Turns caller-supplied paths (positional, ``--path`` walk, or the list a diff
produced) into ``(repo-relative posix path, absolute path)`` pairs. Rejects
anything outside the repository with ``ConfigError`` (exit 2).
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from memory_placement_git import (  # noqa: E402
    ConfigError,
    DiffEntry,
    index_paths,
    merge_base,
    range_entries,
    staged_entries,
)

IndexMap = dict[str, tuple[str, str] | None]


def is_skippable(path: Path) -> bool:
    """True for README.md, any *-index.md, and anything that is not .md."""
    if path.suffix.lower() != ".md":
        return True
    if path.name == "README.md":
        return True
    return path.name.endswith("-index.md")


def walk_directory(directory: Path, repo_root: Path) -> list[Path]:
    """Return every ``.md`` file under ``directory``, which must sit in the repo."""
    base_dir = directory if directory.is_absolute() else repo_root / directory
    base_dir = base_dir.resolve()
    if not base_dir.is_relative_to(repo_root):
        raise ConfigError(f"--path is outside the repository: {directory}")
    if not base_dir.is_dir():
        raise ConfigError(f"--path is not a directory: {directory}")
    return sorted(base_dir.rglob("*.md"))


def _check_staged_entry(relpath: str, raw: Path, index: IndexMap) -> None:
    """Raise ``ConfigError`` unless ``relpath`` is a resolved, non-symlink index entry."""
    if relpath not in index:
        raise ConfigError(f"staged path is not in the index: {raw}")
    entry = index[relpath]
    if entry is None:
        raise ConfigError(f"staged path has unresolved index entries: {raw}")
    if entry[0] == "120000":
        raise ConfigError(f"staged symlink cannot be validated: {raw}")


def _check_tree_file(abspath: Path, raw: Path, repo_root: Path) -> None:
    """Raise ``ConfigError`` unless ``abspath`` is a real file that stays in the repo."""
    if not abspath.is_file():
        # Fail closed. lefthook's {staged_files} never lists deletions
        # (ACMR filter), so a staged memory deletion cannot land here.
        raise ConfigError(f"path is missing or a dangling symlink: {raw}")
    # Lexical path = git entry; resolved target = what read_text opens.
    if not abspath.resolve().is_relative_to(repo_root):
        raise ConfigError(f"symlink target is outside the repository: {raw}")


def resolve_candidates(
    raw_paths: list[Path],
    repo_root: Path,
    index: IndexMap | None,
) -> list[tuple[str, Path]]:
    """Resolve caller-supplied paths to (repo-relative posix path, absolute path).

    Applies the README/``*-index.md``/non-``.md`` skip and rejects (raises
    ``ConfigError``) any path that resolves outside the repository root.
    """
    candidates: list[tuple[str, Path]] = []
    for raw in raw_paths:
        abspath = raw if raw.is_absolute() else repo_root / raw
        # Normalise without following symlinks: the staged path is the one
        # git tracks, and a link's target may sit in the base tree while the
        # link itself is new. resolve() would report the target instead.
        abspath = Path(os.path.normpath(abspath))
        if not abspath.is_relative_to(repo_root):
            raise ConfigError(f"path is outside the repository: {raw}")
        if index is None and abspath.is_dir():
            raise ConfigError(f"positional path is a directory, use --path: {raw}")
        if is_skippable(abspath):
            continue
        relpath = abspath.relative_to(repo_root).as_posix()
        if index is not None:
            _check_staged_entry(relpath, raw, index)
        else:
            _check_tree_file(abspath, raw, repo_root)
        candidates.append((relpath, abspath))
    return candidates


@dataclass(frozen=True, slots=True)
class Scope:
    """What to check and what to compare it with."""

    base: str
    candidates: list[tuple[str, Path]]
    index: dict[str, tuple[str, str] | None] | None
    renames: dict[str, str]


def _raw_paths(args: argparse.Namespace, root: Path, entries: list[DiffEntry]) -> list[Path]:
    """Return the unfiltered paths a caller asked to check."""
    if args.changed_since is not None:
        return [Path(entry.path) for entry in entries]
    if args.path is not None:
        return walk_directory(args.path, root)
    return [Path(p) for p in args.paths]


def build_scope(args: argparse.Namespace, root: Path) -> Scope:
    """Resolve the base, the candidate files, and any rename sources."""
    base = args.base or "HEAD"
    entries: list[DiffEntry] = []
    if args.changed_since is not None:
        base = merge_base(root, args.changed_since)
        entries = range_entries(root, args.changed_since)
    elif args.staged:
        entries = staged_entries(root, base)
    index = index_paths(root) if args.staged else None
    candidates = resolve_candidates(_raw_paths(args, root, entries), root, index)
    renames = {entry.path: entry.old_path for entry in entries if entry.old_path}
    return Scope(base, candidates, index, renames)
