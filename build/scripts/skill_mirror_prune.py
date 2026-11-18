#!/usr/bin/env python3
"""Remove mirror skill files that have no counterpart in the source skill.

Companion to ``skill_support_mirror.py``, whose :class:`SkillSupportSyncError`
this module raises.
``_copy_skill_tree`` walks source files forward only, so a support file deleted
or renamed in ``src/claude/skills/<name>/`` used to leave its old copy in every
mirror tree. This module is the reverse walk.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from atomic_write import find_repo_root, is_redirecting  # noqa: E402
from binplace_manifest import is_bytecode_artifact  # noqa: E402
from regen_guard import detect_reason_strict as regen_detect_reason_strict  # noqa: E402
from skill_copy_compare import SKILL_MD, tree_sources  # noqa: E402
from skill_support_mirror import SkillSupportSyncError  # noqa: E402


def _raise_unreadable(exc: OSError) -> None:
    raise SkillSupportSyncError(
        f"{exc.filename}: unreadable source directory, refusing to prune: {exc.strerror}"
    ) from exc


def _require_readable_source(source: Path) -> None:
    """Raise when any directory under ``source`` cannot be listed.

    ``skill_copy_compare.tree_sources`` (``Path.rglob``) skips a directory it
    cannot read, so its files would be missing from the owned set and the prune
    would delete their mirror copies. This walk raises instead. It is stricter
    than the copy, which tolerates the same gap: the prune is the destructive
    half and fails closed.
    """
    for _ in os.walk(source, onerror=_raise_unreadable):
        pass


def mirror_owned_rels(
    source: Path, skip_filenames: frozenset[Path] = frozenset()
) -> frozenset[Path]:
    """Return every skill-relative path the mirror of ``source`` may hold.

    The set comes from the same enumeration the copy loop walks
    (:func:`skill_copy_compare.tree_sources`, minus directories and bytecode),
    so the copy and the orphan check cannot disagree about what counts as
    owned. Two kinds of path have no ``source`` file yet belong in the mirror:
    ``SKILL.md`` (a new templated skill has none until binplace writes it; the
    mirror renders it from the plugin tree) and ``skip_filenames`` (files
    another generator renders into the mirror, such as
    ``lib_mirror.lib_owned_support_files``).
    """
    _require_readable_source(source)
    owned = {SKILL_MD, *skip_filenames}
    for path in tree_sources(source, None):
        if path.is_dir():
            continue
        rel = path.relative_to(source)
        if not is_bytecode_artifact(rel):
            owned.add(rel)
    return frozenset(owned)


_SIDECAR_SUFFIX = ".noregen"


def _is_kept_sidecar(path: Path) -> bool:
    """Return whether ``path`` is the ``.noregen`` sidecar of a file that exists."""
    if not path.name.endswith(_SIDECAR_SUFFIX) or path.name == _SIDECAR_SUFFIX:
        return False
    return path.with_name(path.name[: -len(_SIDECAR_SUFFIX)]).exists()


def _redirects(path: Path) -> bool:
    """Return whether ``path`` is a symlink or a Windows junction (no-follow stat).

    ``Path.is_symlink`` misses a junction, and ``os.walk(followlinks=False)``
    still descends into one, so every link decision here goes through
    ``atomic_write.is_redirecting``. A path that cannot be examined raises: an
    entry that vanished or is unreadable is not known to be safe.
    """
    try:
        redirects: bool = is_redirecting(path.lstat())
        return redirects
    except OSError as exc:
        raise SkillSupportSyncError(f"{path}: cannot examine for links, refused: {exc}") from exc


def _redirecting_ancestor(root: Path, path: Path) -> Path | None:
    """Return the first ancestor of ``path`` below ``root`` that is a link or junction.

    Stricter than ``atomic_write.reject_symlinked_ancestors``, which tests
    ``Path.is_symlink`` and so misses a junction. A missing ancestor is fine.
    """
    try:
        parts = path.relative_to(root).parts
    except ValueError:
        return None
    current = root
    for part in parts[:-1]:
        current = current / part
        if os.path.lexists(current) and _redirects(current):
            return current
    return None


def _require_unlinked_target(target: Path) -> None:
    """Raise when ``target`` or an ancestor below the repository root is a link or junction.

    ``target`` is made absolute first, as ``atomic_write._confine_to_repo``
    does: a relative path never lies under the absolute repository root, so
    the ancestor walk would be skipped.

    Outside any checkout (``find_repo_root`` returns ``None``) only ``target``
    itself is checked: there is no root to confine ancestors to, the same
    stance as ``atomic_write._confine_to_repo`` ("a path outside any checkout
    has no root to confine to and is left to the caller"). Skipping is safe
    because ``build_all`` and ``generate_skills`` only reach this with a path
    under the repository they run in, and the prune still never descends into
    a link and unlinks only regular files, so it never deletes through one.
    """
    target = target.absolute()
    if _redirects(target):
        raise SkillSupportSyncError(f"{target}: symlinked mirror skill directory refused")
    root = find_repo_root(target)
    if root is None:
        return
    ancestor = _redirecting_ancestor(root, target / "x")
    if ancestor is not None:
        raise SkillSupportSyncError(
            f"mirror skill directory {target} has a symlinked ancestor directory at {ancestor}"
        )


def _folded(rel: Path) -> str:
    return rel.as_posix().casefold()


def _protection_reason(path: Path) -> str | None:
    """Return the NO-REGEN reason for ``path``, raising when the marker cannot be read.

    ``regen_guard.detect_reason`` answers "unprotected" when the read fails, so
    an unreadable hand-maintained file would be deleted. The strict form lets
    the ``OSError`` through and this turns it into a refusal.
    """
    try:
        reason: str | None = regen_detect_reason_strict(path)
        return reason
    except OSError as exc:
        raise SkillSupportSyncError(
            f"{path}: cannot read to check for a NO-REGEN marker, refusing to prune: {exc}"
        ) from exc


def _is_orphan_file(
    path: Path, rel: Path, owned: frozenset[Path], owned_folded: frozenset[str]
) -> bool:
    """Return whether the regular file ``path`` is an unprotected orphan.

    Bytecode and owned paths are not orphans. A path that differs from an owned
    path only by case is kept with a notice and left to the copy: on a
    case-insensitive filesystem (macOS APFS default) a case-only rename makes
    the old name and the new name one file, so deleting the "orphan" would
    remove the only copy. The cost is that on a case-sensitive filesystem a
    stale case variant survives until removed by hand. A ``NO-REGEN`` file or
    the ``.noregen`` sidecar of an existing file is also kept with a notice.
    """
    if rel in owned or is_bytecode_artifact(rel):
        return False
    if _folded(rel) in owned_folded:
        print(f"  NOTICE: kept {path} (differs from a source path only by case)")
        return False
    if _protection_reason(path) is not None or _is_kept_sidecar(path):
        print(f"  NOTICE: kept {path} (NO-REGEN, no source counterpart)")
        return False
    return True


def _symlink_problem(
    path: Path, rel: Path, owned: frozenset[Path], owned_dirs: set[Path]
) -> str | None:
    """Return why the symlink ``path`` is refused, or ``None`` when the copy replaces it."""
    if rel in owned_dirs:
        return f"{path}: symlink at an owned directory path refused (CWE-59)"
    if rel not in owned:
        return f"{path}: symlink with no source counterpart refused"
    return None


def _find_mirror_orphans(target: Path, owned: frozenset[Path]) -> list[Path]:
    """Return the files under ``target`` that the source does not own.

    Walks without following links and finishes before the caller deletes
    anything. A symlink at a path the source does not own is an error, not an
    orphan: it may point outside the mirror (CWE-22/59), so nothing is removed
    until a human looks. A symlink at an owned directory path is an error too:
    the copy would write through it to wherever it points (CWE-59), and
    ``--check`` would compare through it. A symlink at an owned file path is
    left for the copy, which replaces the link itself. Bytecode, a ``NO-REGEN``
    file, and a ``.noregen`` sidecar of an existing file are never orphans.
    """
    _require_unlinked_target(target)
    owned_dirs = {parent for rel in owned for parent in rel.parents}
    owned_folded = frozenset(_folded(rel) for rel in owned)
    orphans: list[Path] = []
    links: list[str] = []
    for dirpath, dirnames, filenames in os.walk(target, followlinks=False):
        base = Path(dirpath)
        linked = {name for name in [*dirnames, *filenames] if _redirects(base / name)}
        # os.walk skips a symlinked directory but descends into a junction.
        dirnames[:] = [name for name in dirnames if name not in linked]
        for name in sorted(linked):
            problem = _symlink_problem(
                base / name, (base / name).relative_to(target), owned, owned_dirs
            )
            if problem is not None:
                links.append(problem)
        for name in sorted(set(filenames) - linked):
            path = base / name
            if _is_orphan_file(path, path.relative_to(target), owned, owned_folded):
                orphans.append(path)
    if links:
        raise SkillSupportSyncError("; ".join(links))
    return orphans


def _remove_orphan(path: Path, target: Path) -> None:
    """Delete one orphan file, then each parent directory it emptied below ``target``."""
    if _redirects(path):
        raise SkillSupportSyncError(f"{path}: became a symlink before removal, refused")
    try:
        path.unlink()
    except OSError as exc:
        raise SkillSupportSyncError(f"{path}: could not remove orphan mirror file: {exc}") from exc
    for parent in path.parents:
        if parent == target:
            return
        try:
            parent.rmdir()
        except OSError:
            return


def prune_mirror_orphans(
    source: Path,
    target: Path,
    *,
    skip_filenames: frozenset[Path] = frozenset(),
    what_if: bool = False,
    check: bool = False,
) -> int:
    """Remove files in the mirror skill directory ``target`` that ``source`` lacks.

    :func:`_copy_skill_tree` only walks source files forward, so a support file
    deleted or renamed in ``src/claude/skills/<name>/`` left its old copy in
    every mirror tree, and the staleness gate passed.

    Ownership: a mirror file is owned when :func:`mirror_owned_rels`
    lists it, that is every non-bytecode source file, ``SKILL.md``, and
    ``skip_filenames``. Everything else under ``target`` is an orphan. Only
    ``target`` is ever touched, and only its regular files: a symlink or
    junction, a linked ``target`` or ancestor, or a file that is protected by
    NO-REGEN is never deleted. Directories this call empties are removed; others stay.

    ``check`` and ``what_if`` delete nothing and report each orphan (``check``
    as DRIFT, which wins when both are set). Returns the orphan count, removed
    or reported. Raises :class:`SkillSupportSyncError` before any file is
    deleted when the walk finds a symlink or junction, a linked ``target`` or
    ancestor, an unreadable source directory, or an orphan whose NO-REGEN marker
    cannot be read; a path that becomes a link, cannot be examined (``lstat``
    fails in ``_redirects``), or fails to unlink during removal also raises, and
    the orphans removed before it stay removed.
    """
    if not (target.is_dir() or target.is_symlink()):
        return 0
    orphans = _find_mirror_orphans(target, mirror_owned_rels(source, skip_filenames))
    for path in orphans:
        if check:
            print(f"  DRIFT: {path} has no counterpart in {source}")
        elif what_if:
            print(f"  Would remove: {path} (no counterpart in {source})")
    if check or what_if:
        return len(orphans)
    for path in orphans:
        print(f"  Removed orphan: {path}")
        _remove_orphan(path, target)
    return len(orphans)
