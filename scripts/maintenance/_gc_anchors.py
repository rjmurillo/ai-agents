"""What a worktree's admin directory names, and nothing else.

``git worktree remove`` deletes the whole admin directory. Two kinds of anchor
live in there, and both die with it: the worktree's reflogs under ``logs/``,
and its own refs under ``refs/``. Neither is visible to a ref query run in the
main repository, so the ordinary reachability question answers "reachable" for
a commit only one of them holds.

Every reader here is three-valued. An anchor it cannot parse or cannot open
answers "unknown" rather than "nothing at risk", because reading an unreadable
anchor as empty is the silent all-clear these probes exist to prevent.
"""

from __future__ import annotations

import os
import re
import stat
from pathlib import Path

from scripts.maintenance._gc_files import nothing_at, regular_file

_OID = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")
_NULL_OID = re.compile(r"0{40}|0{64}")


def reflog_oids(admin: Path) -> list[str] | None:
    """Every non-null object id named in this worktree's reflogs, oldest first.

    ``logs/HEAD`` is the reflog every worktree has, but it is not the only one
    the removal deletes. ``update-ref --create-reflog`` on a per-worktree ref
    writes ``logs/refs/worktree/<name>``, and that file goes on naming a commit
    after the ref itself has moved off it. Verified against real git 2.43.0: a
    commit named only by such a reflog survives ``gc --prune=now`` while the
    worktree exists and is gone after the worktree is removed.

    A file that holds text but yields no recognizable object id at all was not
    understood, so it answers "unknown" rather than "nothing at risk". Reading
    a truncated or unexpectedly encoded reflog as empty is the same silent
    all-clear the rest of this probe is built to avoid. Lines that parse and
    name only the null id are understood and carry no risk, which is why the
    test is "did any field look like an id" rather than "did any survive".
    """
    logs = walk_files(admin / "logs")
    if logs is None:
        return None
    seen: dict[str, None] = {}
    for log in logs:
        present = regular_file(log)
        if present is None:
            return None
        if not present:
            continue
        try:
            text = log.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None
        understood = False
        for line in text.splitlines():
            for field in line.split(" ")[:2]:
                if not _OID.fullmatch(field):
                    continue
                understood = True
                if _NULL_OID.fullmatch(field):
                    continue
                seen[field] = None
        if text.strip() and not understood:
            return None
    return list(seen)


def walk_files(root: Path) -> list[Path] | None:
    """Every regular file under ``root``, or ``None`` when the walk is untrustworthy.

    Absence of ``root`` is the only answer that yields an empty list, and it is
    settled the way ``regular_file`` settles it: ``stat`` cannot tell a missing
    directory from a corrupt admin record whose parent component is a regular
    file, so ``nothing_at`` decides. Something present where a directory
    belongs is a state this probe does not understand.

    The walk is explicit rather than ``Path.rglob`` because ``rglob`` swallows
    the ``PermissionError`` from an unreadable subdirectory and yields nothing,
    which reads as "no anchors here". ``os.scandir`` raises, so the refusal
    reaches the caller. A directory symlink answers "unknown" for the mirror
    reason: git resolves refs through one, ``rglob`` never enters it, and a
    walk that skipped the subtree would clear anchors it never opened. Sorted
    so the caller reads in a stable order.
    """
    try:
        mode = root.stat().st_mode
    except (FileNotFoundError, NotADirectoryError):
        return [] if nothing_at(root) else None
    except OSError:
        return None
    if not stat.S_ISDIR(mode):
        return None
    found: list[Path] = []
    pending = [root]
    while pending:
        try:
            entries = list(os.scandir(pending.pop()))
        except OSError:
            return None
        for entry in entries:
            try:
                if entry.is_symlink() and entry.is_dir():
                    return None
                if entry.is_dir():
                    pending.append(Path(entry.path))
                elif entry.is_file():
                    found.append(Path(entry.path))
            except OSError:
                return None
    return sorted(found)


def worktree_ref_oids(admin: Path) -> list[str] | None:
    """Every object id named by a ref stored under this worktree's admin dir.

    ``git worktree remove`` deletes the admin directory, and these refs go with
    it. Nothing in the main repository names them, so the ordinary reachability
    question answers "reachable" for a commit only one of them holds.

    A symbolic ref names another ref rather than an object, so it anchors
    nothing on its own and contributes no candidate. A ref file that holds text
    this cannot parse answers "unknown", the same way the reflog reader does:
    reading an unparsed anchor as empty is the silent all-clear this probe
    exists to prevent.
    """
    entries = walk_files(admin / "refs")
    if entries is None:
        return None
    seen: dict[str, None] = {}
    for entry in entries:
        try:
            text = entry.read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            return None
        if not text or text.startswith("ref:"):
            continue
        field = text.split()[0]
        if not _OID.fullmatch(field):
            return None
        if not _NULL_OID.fullmatch(field):
            seen[field] = None
    return list(seen)
