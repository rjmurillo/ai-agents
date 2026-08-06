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
    all-clear the rest of this probe is built to avoid.
    """
    logs = walk_files(admin / "logs")
    if logs is None:
        return None
    seen: dict[str, None] = {}
    for log in logs:
        text = _reflog_text(log)
        if text is None:
            return None
        if not _collect_reflog_oids(text, seen):
            return None
    return list(seen)


def _reflog_text(log: Path) -> str | None:
    """The reflog's contents, or ``None`` when it could not be read.

    ``log`` came from a walk that already saw it, so a file that is absent now
    is one that went away underneath us, not one that was never there. Reading
    that as an empty reflog would clear a worktree using a snapshot the probe
    knows is stale.
    """
    if not regular_file(log):
        return None
    try:
        return log.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _collect_reflog_oids(text: str, seen: dict[str, None]) -> bool:
    """Add every non-null id in ``text`` to ``seen``. ``False`` if a line made no sense.

    Every line git writes to a reflog opens with the old and the new object id,
    so a non-blank line that does not is a line this reader does not
    understand: a truncated final write, a different encoding, or not a reflog
    at all. Judging the file as a whole would let one good line vouch for the
    rest and hand back a partial list, which reads downstream as "these are the
    only ids at risk". A line naming only the null id is understood and carries
    no risk, which is why the test is the shape of the fields rather than what
    survives.
    """
    for line in text.splitlines():
        if not line.strip():
            continue
        fields = line.split(" ")[:2]
        if len(fields) < 2 or not all(_OID.fullmatch(f) for f in fields):
            return False
        for field in fields:
            if not _NULL_OID.fullmatch(field):
                seen[field] = None
    return True


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
        if not _route_entries(entries, pending, found):
            return None
    return sorted(found)


def _route_entries(entries: list[os.DirEntry[str]], pending: list[Path], found: list[Path]) -> bool:
    """Send each entry to the walk queue or the results. ``False`` if one is opaque."""
    for entry in entries:
        try:
            if entry.is_symlink() and entry.is_dir():
                return False
            if entry.is_dir():
                pending.append(Path(entry.path))
            elif entry.is_file():
                found.append(Path(entry.path))
        except OSError:
            return False
    return True


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
