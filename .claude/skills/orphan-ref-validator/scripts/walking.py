#!/usr/bin/env python3
"""orphan-ref-validator file walking + secret denylist.

Owns the recursive-walk policy for ``scan.py``: which directory names to
prune, which file suffixes to scan, which file-name patterns are secrets,
and the per-file size cap. Symlink-followed directories that escape the
repository root are skipped here so the upstream ``scan_file`` path never
sees them.

Per ``.claude/rules/canonical-source-mirror.md``, the prune set mirrors
``build/scripts/validate_marketplace_counts.py:_EXCLUDED_DIRS`` plus the
two skill-reference subtrees that are progressive disclosure docs
(``references/``, ``templates/``). The canonical contract is:

    _EXCLUDED_DIRS = {
        "node_modules", ".git", "worktrees", "cache", "__pycache__",
    }

Stricter/looser/different than canonical: same five names; this module
adds ``references`` and ``templates`` for skill-progressive-disclosure
directories that legitimately cite external entities and would produce
high-noise findings.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Iterable

LOGGER = logging.getLogger("orphan_ref_validator")

SCAN_FILE_SUFFIXES: tuple[str, ...] = (".md", ".json", ".yaml", ".yml")

# Mirrors validate_marketplace_counts.py:_EXCLUDED_DIRS plus two
# skill-progressive-disclosure subtrees. Frozen for safety.
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


def walk_targets(target: Path, repo_root: Path) -> Iterable[Path]:
    """Yield candidate files under ``target`` (or just the target if it is a file).

    Recurses with ``iterdir`` and prunes ``EXCLUDE_DIR_NAMES`` at the
    directory level rather than ``rglob('*')`` + post-filter, so excluded
    subtrees (``node_modules``, ``.git``, ``worktrees``, ``cache``,
    ``__pycache__``, ``references``, ``templates``) are never entered.

    Symlink directories that resolve outside the repository root are
    skipped (CWE-22 / CWE-59 hardening).
    """
    if target.is_file():
        if is_secret_path(target):
            return
        try:
            size = target.stat().st_size
        except OSError as exc:
            LOGGER.warning("could not stat %s: %s", target, exc)
            return
        if size > MAX_FILE_BYTES:
            LOGGER.warning("skipping %s: exceeds %d bytes", target, MAX_FILE_BYTES)
            return
        yield target
        return
    yield from _iter_dir_pruned(target, repo_root)


def _iter_dir_pruned(directory: Path, repo_root: Path) -> Iterable[Path]:
    """Walk ``directory`` recursively, pruning excluded directory names
    and refusing to follow symlinks that escape ``repo_root``."""
    try:
        entries = list(directory.iterdir())
    except (OSError, PermissionError) as exc:
        LOGGER.warning("could not iterate %s: %s", directory, exc)
        return
    for entry in entries:
        yield from _iter_entry(entry, repo_root)


def _iter_entry(entry: Path, repo_root: Path) -> Iterable[Path]:
    """Yield walkable files from a single directory entry."""
    try:
        if entry.is_dir():
            if entry.name in EXCLUDE_DIR_NAMES:
                return
            if not is_safe_subdirectory(entry, repo_root):
                return
            yield from _iter_dir_pruned(entry, repo_root)
            return
    except OSError as exc:
        LOGGER.warning("could not stat %s: %s", entry, exc)
        return
    if not entry.is_file():
        return
    if entry.suffix not in SCAN_FILE_SUFFIXES:
        return
    if is_secret_path(entry):
        return
    if not _within_size_cap(entry):
        return
    yield entry


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
