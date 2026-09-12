#!/usr/bin/env python3
"""No-symlink-follow read/write primitives shared by ``build_all.py`` and
``binplace_manifest.py``.

Split out of ``build/scripts/build_all.py`` (ADR-109, DESIGN-025) so
``binplace_manifest.py``'s ``binplace()`` can reuse the same CWE-59 defenses
``build_all.py``'s snapshot/restore machinery already relies on, without a
circular import: ``build_all.py`` imports ``binplace_manifest`` at module
load time, so ``binplace_manifest`` cannot import back from ``build_all``.
This module has no dependency on either, so both import it instead.

Every function here is unchanged from its original ``build_all.py`` body;
only the module boundary moved. ``build_all.py`` re-imports each name so its
own ~10 call sites keep reading ``_is_redirecting(...)``,
``_write_bytes_no_redirect(...)``, etc. unchanged.

Public names:
    ``MOUNT_POINT_REPARSE_TAG`` -- the Windows junction reparse tag.
    ``O_BINARY``, ``O_NOFOLLOW`` -- platform-guarded ``os.open`` flags.
    ``is_redirecting(metadata) -> bool``
    ``read_bytes_no_redirect(path) -> bytes``
    ``write_bytes_no_redirect(path, content, *, mode=None) -> None``
    ``publish_bytes_atomically(path, content, *, mode=None) -> None``
"""

from __future__ import annotations

import errno
import os
import stat
from pathlib import Path

# A Windows directory junction is reported as a directory carrying this
# reparse tag, so it passes every symlink test and is then traversed, the
# same escape a symlink gives. See `_is_redirecting_link` in
# scripts/validation/portability_baseline.py, which draws the same line.
MOUNT_POINT_REPARSE_TAG = 0xA0000003

# Force binary mode on Windows, where os.open() without O_BINARY inherits the
# C runtime's text-mode default: CRLF translation and truncation at a 0x1A
# byte, either of which would corrupt a snapshot read or a restored write.
# The flag does not exist off Windows, so getattr's fallback of 0 is a no-op
# there. os.O_NOFOLLOW is POSIX-only for the same reason; a Windows junction
# is caught by the fstat check in read_bytes_no_redirect instead.
O_BINARY = getattr(os, "O_BINARY", 0)
O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)


def is_redirecting(metadata: os.stat_result) -> bool:
    """Return whether a no-follow stat names a link or a Windows junction.

    ``S_ISLNK`` alone is not enough; see ``MOUNT_POINT_REPARSE_TAG``'s
    comment. This reads the tag off an lstat result the caller already has,
    rather than calling ``Path.is_junction()``, which swallows ``OSError``
    and answers False -- a fail-open this check exists to remove.
    """
    if stat.S_ISLNK(metadata.st_mode):
        return True
    return getattr(metadata, "st_reparse_tag", 0) == MOUNT_POINT_REPARSE_TAG


def read_bytes_no_redirect(path: Path) -> bytes:
    """Read ``path``'s bytes, refusing at open time if it currently redirects.

    ``os.O_NOFOLLOW`` makes the ``os.open`` call itself fail (``ELOOP``) on a
    symlinked final path component; the ``fstat`` check right after open
    covers the other redirect shape (a Windows junction) on every platform.
    """
    fd = os.open(path, os.O_RDONLY | O_BINARY | O_NOFOLLOW)
    try:
        metadata = os.fstat(fd)
        if is_redirecting(metadata):
            raise OSError(
                errno.ELOOP,
                f"{path} redirects (symlink or junction) at open time",
            )
        with os.fdopen(fd, "rb", closefd=False) as handle:
            return handle.read()
    finally:
        os.close(fd)


def write_bytes_no_redirect(path: Path, content: bytes, *, mode: int | None = None) -> None:
    """Create ``path`` fresh and write ``content``, refusing a raced redirect.

    Callers must have already removed whatever was at ``path``; this call is
    always meant to create a brand new inode. ``os.O_EXCL`` makes the open
    fail if anything, a real file or a symlink, already exists at ``path``,
    closing the classic unlink-then-recreate race. Always creates with
    ``0o600`` (owner read-write only; CodeQL CWE-732), then ``fchmod``s to
    ``mode`` when given, so a restored file ends up matching its captured
    pre-run permission bits rather than a fixed literal.
    """
    fd = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | O_BINARY | O_NOFOLLOW,
        0o600,
    )
    try:
        if mode is not None and hasattr(os, "fchmod"):
            os.fchmod(fd, mode)
        with os.fdopen(fd, "wb", closefd=False) as handle:
            handle.write(content)
    finally:
        os.close(fd)


def publish_bytes_atomically(path: Path, content: bytes, *, mode: int | None = None) -> None:
    """Put ``content`` at ``path`` in one step, via a sibling temp file.

    ``os.replace`` swaps one directory entry, so a concurrent reader opens
    either the old inode or the new one and never a partial or missing
    state, and a symlink at ``path`` is unlinked and swapped for a regular
    file rather than written through (CWE-59). Any ``OSError`` (including the
    ``FileExistsError`` a raced temp-name collision would raise) propagates
    to the caller, which turns it into a per-path ``WARN`` and moves on.
    """
    temporary = path.parent / f".{path.name}.{os.urandom(8).hex()}.tmp"
    try:
        write_bytes_no_redirect(temporary, content, mode=mode)
        os.replace(temporary, path)
    except BaseException:
        try:
            temporary.unlink()
        except OSError:
            pass
        raise
