"""What the filesystem actually says about a path.

``Path.is_file`` swallows every ``OSError`` and answers ``False``, so a
permission denial, a dead symlink chain, and a genuinely absent file all look
identical. Reading the first two as absence is what let a worktree holding the
only copy of a commit be listed for removal, so these helpers separate "not
there" from "could not ask".
"""

from __future__ import annotations

import stat
from pathlib import Path


def regular_file(path: Path) -> bool | None:
    """Is ``path`` a regular file? ``None`` when the question could not be asked.

    ``Path.is_file`` swallows every ``OSError`` and answers ``False``, so a
    permission denial, a dead symlink chain, and a genuinely absent file all
    look identical. The first two are unknowns. Reporting them as "the file is
    not there, so nothing is at risk" is the same silent all-clear that let a
    worktree holding the only copy of a commit be listed for removal.

    ``False`` is reserved for genuine absence, which means no directory entry
    at that path at all. ``stat`` cannot establish that on its own: it follows
    symlinks, so a link to a missing target raises the same
    ``FileNotFoundError`` as nothing being there, and it raises
    ``NotADirectoryError`` when a parent component is a regular file, which is
    a corrupt admin record rather than an empty one. Both were being reported
    as absence. ``lstat`` answers the narrower question of whether anything
    occupies the path, so only that decides ``False``.

    Something present but not a regular file, a directory or a socket where an
    index or a reflog belongs, is a state this probe does not understand, so it
    answers unknown rather than treating a corrupt admin record as an empty one.
    """
    try:
        mode = path.stat().st_mode
    except (FileNotFoundError, NotADirectoryError):
        return False if nothing_at(path) else None
    except OSError:
        return None
    return True if stat.S_ISREG(mode) else None


def nothing_at(path: Path) -> bool:
    """Is there genuinely no directory entry at ``path``?

    ``lstat`` does not follow the final symlink, so a dangling link reports as
    present, which is the honest answer: something occupies the path and this
    probe cannot read through it. Any other failure means the question itself
    could not be asked, which is not absence either.
    """
    try:
        path.lstat()
    except FileNotFoundError:
        return True
    except OSError:
        return False
    return False
