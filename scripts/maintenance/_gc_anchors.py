"""Object ids an admin directory names but ``rev-list --not --all`` misses.

``--all`` walks the shared ref namespace. A worktree's own reflog and its
``refs/worktree/`` refs live under its admin directory and never appear there,
so a commit only they name reads as unreachable. Removing that worktree hands
the commit to the next ``gc``.
"""

from __future__ import annotations

import re
from pathlib import Path

from scripts.maintenance._gc_files import regular_file

_OID = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")
_NULL_OID = re.compile(r"0{40}|0{64}")


def reflog_oids(admin: Path) -> list[str] | None:
    """Every non-null object id named in the admin reflog, oldest first.

    A file that holds text but yields no recognizable object id at all was not
    understood, so it answers "unknown" rather than "nothing at risk". Reading
    a truncated or unexpectedly encoded reflog as empty is the same silent
    all-clear the rest of this probe is built to avoid. Lines that parse and
    name only the null id are understood and carry no risk, which is why the
    test is "did any field look like an id" rather than "did any survive".
    """
    log = admin / "logs" / "HEAD"
    present = regular_file(log)
    if present is None:
        return None
    if not present:
        return []
    try:
        text = log.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    seen: dict[str, None] = {}
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
    root = admin / "refs"
    try:
        if not root.is_dir():
            return []
        entries = [entry for entry in root.rglob("*") if entry.is_file()]
    except OSError:
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
