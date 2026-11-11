#!/usr/bin/env python3
"""Prune and report orphaned skill and agent output (issue #7224).

The scan half lives in ``orphan_outputs.py``: it finds entries that no template
owns. This module decides what a plain build may delete and prints the result.

Modes
-----

``check``
    Read-only. Every orphan is reported and the result is a failure. This is the
    ``build_all.py --check`` behavior.
write
    Same detection, then the build prunes what it can prove safe, the way
    ``generate_rules.py``, ``agent_tree_copy.py`` and ``hermes_packs.py`` already
    prune stale output. An entry is pruned only when all of these hold:

    1. Git shows its template existed (at ``HEAD`` or in ``HEAD`` history) and is
       gone now. A name that never had a template is never pruned.
    2. No file below it is untracked, ignored, or edited since ``HEAD``, and none
       carries a ``NO-REGEN`` sentinel.
    3. For a skill directory in ``src/claude/skills`` or a repo-local
       ``.claude/skills`` directory, ``SKILL.md`` is the only file. Other files
       there are hand-maintained (``src/AGENTS.md``), so they are reported, not
       deleted.
    4. A mirror directory (``src/codex``, ``src/copilot-cli``, ``src/cursor``,
       ``src/muse``, Hermes packs) is pruned only after its source directory in
       ``src/claude/skills`` is gone, because the mirror step would copy it back.

    Symlinks in the install trees (the ``install_tree`` of each skills and
    agents row in ``binplace.yaml``) are never removed here. Once their plugin
    target is gone they dangle, and ``binplace_links`` sweeps them.

Anything left over is a failure in both modes.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from orphan_outputs import (  # noqa: E402
    KIND_AGENT,
    ROLE_MIRROR,
    ROLE_SOURCE,
    Orphan,
    OrphanScan,
    relative_posix,
)
from regen_guard import detect_reason as regen_detect_reason  # noqa: E402
from skill_support_mirror import prune_repo_local_vendor_copies  # noqa: E402

_SKILL_MD = "SKILL.md"
_GIT_LOCATION_ENV_VARS = ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE")


@dataclass
class PruneResult:
    """Result of :func:`prune`."""

    pruned: list[Path] = field(default_factory=list)
    swept_by_binplace: list[Path] = field(default_factory=list)
    unresolved: list[tuple[Orphan, str]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


# --- Git evidence ------------------------------------------------------------


def _git(repo_root: Path, *args: str) -> subprocess.CompletedProcess[bytes] | None:
    env = {k: v for k, v in os.environ.items() if k not in _GIT_LOCATION_ENV_VARS}
    try:
        return subprocess.run(
            ["git", "-C", str(repo_root), *args],
            capture_output=True,
            check=False,
            env=env,
        )
    except OSError:
        return None


def template_removal_proven(repo_root: Path, template_rels: Iterable[str]) -> bool:
    """Return True when git shows one of these templates existed and is gone now.

    Reads ``HEAD`` only (a named ref): the path is in the ``HEAD`` tree (deleted in
    the working tree, not yet committed) or ``HEAD`` history holds a deletion of it.
    A failed git call proves nothing.
    """
    rels = list(template_rels)
    tree = _git(repo_root, "ls-tree", "-r", "--name-only", "-z", "HEAD", "--", *rels)
    if tree is not None and tree.returncode == 0 and tree.stdout.strip(b"\0"):
        return True
    log = _git(repo_root, "log", "HEAD", "-n", "1", "--diff-filter=D", "--format=%H", "--", *rels)
    return log is not None and log.returncode == 0 and bool(log.stdout.strip())


def _git_lists(repo_root: Path, path: Path, *flags: str) -> list[str] | None:
    rel = path.relative_to(repo_root).as_posix()
    done = _git(repo_root, "ls-files", "-z", *flags, "--", rel)
    if done is None or done.returncode != 0:
        return None
    return [p for p in done.stdout.decode("utf-8", "surrogateescape").split("\0") if p]


# --- Prune -------------------------------------------------------------------


def _files_below(directory: Path) -> list[Path]:
    return sorted(p for p in directory.rglob("*") if not p.is_dir())


def _local_change(repo_root: Path, path: Path) -> str | None:
    """Return why ``path`` holds work git cannot restore, or ``None`` when it is clean.

    ``git status --ignored`` lists three kinds of local state that deleting the
    path would lose: unstaged edits to tracked files, untracked files, and
    ignored files (``ls-files --others --exclude-standard`` omits the last). A
    bytecode cache is regenerated, so it never protects a path.
    """
    rel = path.relative_to(repo_root).as_posix()
    done = _git(
        repo_root, "status", "--porcelain=v1", "-z", "--ignored", "--untracked-files=all", "--", rel
    )
    if done is None or done.returncode != 0:
        return "git could not be read"
    for entry in done.stdout.decode("utf-8", "surrogateescape").split("\0"):
        status, changed = entry[:2], entry[3:]
        # "??" untracked, "!!" ignored, or a second column other than blank: the
        # working file differs from the index. A staged-only change lives in the
        # index, so deleting the working file loses nothing.
        if not changed or "__pycache__" in Path(changed).parts:
            continue
        if status[0] in "?!" or status[1] != " ":
            return f"holds uncommitted, untracked, or ignored file {changed}"
    return None


def _agent_blocker(repo_root: Path, path: Path) -> str | None:
    if not _git_lists(repo_root, path):
        return "file is untracked or git could not be read"
    return _local_change(repo_root, path)


def _content_blocker(path: Path) -> str | None:
    """Return why a file below a skill directory protects it, or ``None``."""
    for file in _files_below(path):
        rel = file.relative_to(path).as_posix()
        if file.is_symlink():
            return f"holds symlink {rel}"
        if regen_detect_reason(file) is not None:
            return f"{rel} carries a NO-REGEN sentinel"
    return None


def _hand_maintained_blocker(path: Path) -> str | None:
    for file in _files_below(path):
        rel = file.relative_to(path).as_posix()
        if rel != _SKILL_MD and "__pycache__" not in file.parts:
            return f"holds hand-maintained file {rel}; remove the directory with git rm -r"
    return None


def _skill_blocker(repo_root: Path, orphan: Orphan, removed_sources: set[str]) -> str | None:
    reason = _content_blocker(orphan.path) or _local_change(repo_root, orphan.path)
    if reason is not None:
        return reason
    if orphan.role == ROLE_SOURCE:
        return _hand_maintained_blocker(orphan.path)
    if orphan.role == ROLE_MIRROR and orphan.name not in removed_sources:
        if (repo_root / "src" / "claude" / "skills" / orphan.name).exists():
            return "src/claude/skills still holds the source, so the mirror step would copy it back"
    return None


def _blocker(repo_root: Path, orphan: Orphan, removed_sources: set[str]) -> str | None:
    """Return why ``orphan`` must not be deleted, or ``None`` when pruning is safe."""
    if not template_removal_proven(repo_root, orphan.template_rels):
        return "no git record that its template was deleted, so its owner is unknown"
    if orphan.kind == KIND_AGENT:
        return _agent_blocker(repo_root, orphan.path)
    return _skill_blocker(repo_root, orphan, removed_sources)


def _delete(orphan: Orphan) -> list[str]:
    """Delete one orphan; return error messages, empty on success."""
    if orphan.kind == KIND_AGENT:
        try:
            orphan.path.unlink()
        except OSError as exc:
            return [f"{orphan.path}: could not remove orphan: {exc}"]
        return []
    _, errors = prune_repo_local_vendor_copies(
        orphan.path.parent, frozenset({orphan.name}), check=False, what_if=False
    )
    if errors or orphan.path.exists():
        return errors or [f"{orphan.path}: directory not emptied"]
    return []


def _plugin_tree_exists(link: Path) -> bool:
    """Return whether the directory the link points into exists.

    ``binplace_links`` sweeps a dangling install link only for a plugin tree
    that is a directory. A tree that is gone leaves the link for a human.
    """
    pointed = Path(os.path.normpath(link.parent / os.readlink(link)))
    return pointed.parent.is_dir()


def _classify_links(links: Iterable[Orphan], result: PruneResult) -> None:
    for orphan in links:
        if not os.path.lexists(orphan.path) or orphan.path.exists():
            result.unresolved.append((orphan, "link target still exists"))
        elif _plugin_tree_exists(orphan.path):
            result.swept_by_binplace.append(orphan.path)
        else:
            result.unresolved.append(
                (orphan, "its plugin tree is gone, so binplace will not sweep it; git rm the link")
            )


def prune(repo_root: Path, orphans: Iterable[Orphan], *, what_if: bool = False) -> PruneResult:
    """Delete every orphan that :func:`_blocker` clears; list the rest as unresolved."""
    repo_root = repo_root.resolve()
    result = PruneResult()
    removed_sources: set[str] = set()
    ordered = sorted(orphans, key=lambda o: (o.role != ROLE_SOURCE, str(o.path)))
    for orphan in (o for o in ordered if not o.is_link):
        reason = _blocker(repo_root, orphan, removed_sources)
        if reason is not None:
            result.unresolved.append((orphan, reason))
            continue
        errors = [] if what_if else _delete(orphan)
        if errors:
            result.errors.extend(errors)
            continue
        result.pruned.append(orphan.path)
        if orphan.role == ROLE_SOURCE:
            removed_sources.add(orphan.name)
    _classify_links((o for o in ordered if o.is_link), result)
    return result


# --- Reporting ---------------------------------------------------------------


def report_scan(repo_root: Path, found: OrphanScan, *, check: bool) -> None:
    """Print the examined and orphan counts, then each orphan in check mode."""
    repo_root = repo_root.resolve()
    print(
        f"Orphan scan: examined {found.examined} skill and agent entries in "
        f"{found.trees} trees, {len(found.orphans)} orphan(s)"
    )
    if not check:
        return
    for orphan in found.orphans:
        where = relative_posix(repo_root, orphan.path)
        print(
            f"ORPHANED OUTPUT: {where} has no {orphan.kind} template "
            f"({' or '.join(orphan.template_rels)})",
            file=sys.stderr,
        )


def report_prune(repo_root: Path, done: PruneResult) -> None:
    """Print what the write-mode prune removed, left to binplace, or could not resolve."""
    repo_root = repo_root.resolve()
    for path in done.pruned:
        print(f"  PRUNED orphan: {relative_posix(repo_root, path)}")
    for path in done.swept_by_binplace:
        print(f"  Dangling install link, binplace sweeps it: {relative_posix(repo_root, path)}")
    for orphan, reason in done.unresolved:
        print(
            f"ORPHANED OUTPUT kept: {relative_posix(repo_root, orphan.path)}: {reason}",
            file=sys.stderr,
        )
    for error in done.errors:
        print(f"Error: {error}", file=sys.stderr)


def exit_code(found: OrphanScan, done: PruneResult | None) -> int:
    """Return 0 when no orphan remains, else 2 (the staleness code ``--check`` uses)."""
    if done is None:
        return 2 if found.orphans else 0
    return 2 if done.unresolved or done.errors else 0
