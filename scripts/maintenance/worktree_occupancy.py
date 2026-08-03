#!/usr/bin/env python3
"""Which worktrees hold a live process, read from ``/proc``.

Kept apart from the git logic in ``gc_worktrees.py`` because this asks the
kernel about processes and knows nothing about worktrees or branches. The
containment predicate is the only place the two ideas meet.
"""

from __future__ import annotations

import errno
import os
import pathlib
from typing import NamedTuple


class Occupancy(NamedTuple):
    """Live-process working directories, plus the size of the blind spot.

    ``unreadable`` counts processes this scan could not resolve but could not
    rule out either. It is reported so the gap is visible instead of silently
    counted as vacancy.

    ``proc_available`` is False when there is no ``/proc`` to read at all. That
    is a different blind spot from ``unreadable``: not some processes unknown,
    but every process unknown, and ``unreadable`` cannot express it because a
    scan that never ran counts nothing. Without this field an empty ``cwds``
    from a missing ``/proc`` is indistinguishable from a genuinely idle
    machine, and every worktree reads as vacant with nothing disclosed.
    """

    cwds: frozenset[str]
    unreadable: int
    proc_available: bool = True


#: ``/proc/<pid>`` entries that disappear mid-scan are genuinely gone, so their
#: working directory cannot hold a worktree. Every other failure means the
#: process is alive and its directory is unknown.
_PROCESS_GONE = frozenset({errno.ENOENT, errno.ESRCH})


def occupied_paths() -> Occupancy:
    """Working directories of live processes, read from ``/proc``.

    A worktree can be fully merged, fully pushed and clean while an agent is
    still sitting in it. Removing it pulls the directory out from under that
    process.

    Two failure kinds are not the same and are not treated the same. A
    ``/proc/<pid>`` entry that vanishes mid-scan belongs to a process that has
    exited, so it cannot hold a worktree and is ignored. A cwd that cannot be
    read while the process is still alive is unknown, not vacant, and is
    counted in ``Occupancy.unreadable``.

    Known residual risk. Only unreadable processes owned by this user are
    counted, because the guard exists to protect this user's own agent shells
    and a process owned by another user does not chdir into their worktrees.
    Measured on the development machine this was written for: 332 readable
    cwds, 691 permission denied, of which 3 were owned by this user, and all
    three were hardened session daemons (a password-manager helper, the user
    ``systemd``, and ``sd-pam``) that never enter a worktree. Failing closed on
    that set would refuse every removal forever, so the gap is disclosed rather
    than escalated. An interactive shell or agent process is always readable by
    its own owner, which is the case this guard is for.

    Where ``/proc`` is unavailable the scan cannot see any process, so the
    result carries ``proc_available=False`` and the caller discloses that no
    occupancy check ran. Reporting an empty ``cwds`` alone would read as an
    idle machine and mark every worktree vacant.
    """
    proc = pathlib.Path("/proc")
    if not proc.is_dir():
        return Occupancy(frozenset(), 0, proc_available=False)
    uid = os.getuid()
    found: set[str] = set()
    unreadable = 0
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            found.add(os.readlink(entry / "cwd"))
            continue
        except OSError as exc:
            if exc.errno in _PROCESS_GONE:
                continue
        try:
            owned_by_us = entry.stat().st_uid == uid
        except OSError:
            continue
        if owned_by_us:
            unreadable += 1
    return Occupancy(frozenset(found), unreadable)


def is_occupied(path: str, cwds: frozenset[str]) -> bool:
    """True when a live process sits in ``path`` or below it.

    ``path`` is normalized once so a caller that passes a trailing slash gets
    the same answer as one that does not. Comparing an unstripped ``path``
    against a ``/proc`` cwd, which never carries a trailing slash, misses a
    process sitting exactly at the worktree root and reports it vacant.
    """
    base = path.rstrip("/")
    return any(cwd == base or cwd.startswith(base + "/") for cwd in cwds)
