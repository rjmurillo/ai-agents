"""Fast, fail-closed lookup for Git's sorted ``packed-refs`` file.

``conftest.py`` runs ``_guard_real_repo_head`` before and after every pytest
item. On a linked worktree whose checked-out branch has been packed by
``git gc`` or ``git maintenance run --auto`` (the common state for multi-
worktree checkouts), the loose ref file under ``refs/heads/`` no longer exists
and the branch lives only in ``packed-refs``. Falling back to
``git rev-parse HEAD`` on every packed branch spawns two Git subprocesses per
test across the full suite.

This module resolves a single ref directly from a sorted ``packed-refs`` file
in O(log N) seeks with zero caching (so concurrent atomic replacements or
in-place test overwrites are never stale) and fails closed by raising
``PackedRefsUnresolvedError`` on any unsorted, malformed, non-regular, or
unreadable file so the caller can fall back to ``git rev-parse HEAD``.
"""

from __future__ import annotations

import os
import re
import stat
from pathlib import Path
from typing import BinaryIO

_PACKED_REFS_HEADER = b"# pack-refs with:"
_OBJECT_ID_BYTES_PATTERN = re.compile(rb"^[0-9a-f]{40}$|^[0-9a-f]{64}$")
_LINEAR_SCAN_THRESHOLD = 4096


class PackedRefsUnresolvedError(Exception):
    """Raised when ``packed-refs`` cannot be proven; caller must fall back to Git."""


def _parse_packed_ref_line(line: bytes) -> tuple[bytes, bytes]:
    """Parse one ``<oid> <refname>`` line or raise ``PackedRefsUnresolvedError``."""
    stripped = line.rstrip(b"\r\n")
    space = stripped.find(b" ")
    if space <= 0:
        raise PackedRefsUnresolvedError("malformed packed-refs line")
    oid = stripped[:space]
    name = stripped[space + 1 :]
    if (
        not name
        or b"\r" in name
        or b" " in name
        or b"\t" in name
        or _OBJECT_ID_BYTES_PATTERN.match(oid) is None
    ):
        raise PackedRefsUnresolvedError("malformed packed-refs line")
    return oid, name


def _has_sorted_header(header: bytes) -> bool:
    """Return True iff ``header`` declares Git's sorted ``packed-refs`` trait."""
    stripped = header.rstrip(b"\r\n")
    if b"\r" in stripped or not stripped.startswith(_PACKED_REFS_HEADER):
        return False
    traits = stripped[len(_PACKED_REFS_HEADER) :].split()
    return b"sorted" in traits


def _read_next_ref_line(handle: BinaryIO, hi: int) -> bytes:
    """Read the next non-comment, non-peeled line starting before ``hi``."""
    while handle.tell() < hi:
        candidate = handle.readline()
        if not candidate:
            raise PackedRefsUnresolvedError("packed-refs truncated during read")
        if candidate.startswith((b"#", b"^")):
            continue
        return candidate
    return b""


def _linear_scan_packed_refs(
    handle: BinaryIO,
    lo: int,
    hi: int,
    ref_bytes: bytes,
    *,
    lo_name: bytes | None = None,
    hi_name: bytes | None = None,
) -> str | None:
    """Scan sorted ``packed-refs`` lines in ``[lo, hi)`` for ``ref_bytes``."""
    handle.seek(lo)
    prev_name = lo_name
    while handle.tell() < hi:
        line = handle.readline()
        if not line:
            raise PackedRefsUnresolvedError("packed-refs truncated during read")
        if line.startswith((b"#", b"^")):
            continue
        oid, name = _parse_packed_ref_line(line)
        if prev_name is not None and name <= prev_name:
            raise PackedRefsUnresolvedError("packed-refs entries are not strictly sorted")
        if hi_name is not None and name >= hi_name:
            raise PackedRefsUnresolvedError("packed-refs entries are not strictly sorted")
        prev_name = name
        if name == ref_bytes:
            return oid.decode("ascii")
        if name > ref_bytes:
            return None
    return None


def _binary_search_packed_refs(handle: BinaryIO, lo: int, hi: int, ref_bytes: bytes) -> str | None:
    """Narrow ``[lo, hi)`` in O(log N) seeks and finish with a bounded linear scan."""
    lo_name: bytes | None = None
    hi_name: bytes | None = None
    while hi - lo > _LINEAR_SCAN_THRESHOLD:
        mid = (lo + hi) // 2
        handle.seek(mid)
        if not handle.readline():  # advance past the partial line straddling mid
            raise PackedRefsUnresolvedError("packed-refs truncated during read")
        first_line_after_mid = handle.tell()
        if first_line_after_mid >= hi:
            break

        line = _read_next_ref_line(handle, hi)
        if not line:
            hi = first_line_after_mid
            continue

        oid, name = _parse_packed_ref_line(line)
        if (lo_name is not None and name <= lo_name) or (hi_name is not None and name >= hi_name):
            raise PackedRefsUnresolvedError("packed-refs entries are not strictly sorted")
        if name == ref_bytes:
            return oid.decode("ascii")
        if name < ref_bytes:
            lo = handle.tell()
            lo_name = name
        else:
            hi = first_line_after_mid
            hi_name = name

    return _linear_scan_packed_refs(handle, lo, hi, ref_bytes, lo_name=lo_name, hi_name=hi_name)


def _open_regular_packed_refs(packed_refs_path: Path) -> BinaryIO | None:
    """Open ``packed_refs_path`` without blocking on FIFOs, returning None if absent."""
    flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)
    try:
        fd = os.open(packed_refs_path, flags)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise PackedRefsUnresolvedError("packed-refs unreadable") from exc

    try:
        file_stat = os.fstat(fd)
        if not stat.S_ISREG(file_stat.st_mode):
            raise PackedRefsUnresolvedError("packed-refs is not a regular file")
        return os.fdopen(fd, "rb")
    except PackedRefsUnresolvedError:
        os.close(fd)
        raise
    except OSError as exc:
        os.close(fd)
        raise PackedRefsUnresolvedError("packed-refs unreadable") from exc


def lookup_packed_ref(packed_refs_path: Path, ref_name: str) -> str | None:
    """Resolve ``ref_name`` from a sorted ``packed-refs`` file, or ``None`` if absent.

    Returns ``None`` when ``packed_refs_path`` does not exist or when the sorted
    file provably does not contain ``ref_name``. Raises
    ``PackedRefsUnresolvedError`` for any state that cannot be proved safely
    (unsorted file, malformed line, non-regular file, truncation, or read error).
    """
    try:
        ref_bytes = ref_name.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise PackedRefsUnresolvedError("ref name is not valid UTF-8") from exc

    handle = _open_regular_packed_refs(packed_refs_path)
    if handle is None:
        return None
    try:
        with handle:
            if not _has_sorted_header(handle.readline()):
                raise PackedRefsUnresolvedError("packed-refs is not sorted")
            lo = handle.tell()
            handle.seek(0, os.SEEK_END)
            hi = handle.tell()
            return _binary_search_packed_refs(handle, lo, hi, ref_bytes)
    except OSError as exc:
        raise PackedRefsUnresolvedError("packed-refs unreadable") from exc
