#!/usr/bin/env python3
"""Canonical, hardened append writer for the /spec metrics tally files.

Issue #1974 / REQ-008 Sec F3: the Step 0 and Step 0.5 metrics tally files
(``.agents/metrics/STEP-0-METRICS.md`` and
``.agents/sessions/STEP-0.5-METRICS.md``) are appended once per ``/spec``
invocation. The append path was previously prose in ``.claude/commands/spec.md``
that told the agent to open and write the file by hand, with no defense against
a hostile filesystem entry at the tally path.

This module is the single safe append point. Two filesystem weaknesses motivate
it:

- CWE-59 (Improper Link Resolution Before File Access, "link following"): if an
  attacker plants a symlink at the tally path pointing at an arbitrary file
  (for example a dotfile, an SSH key, or a tracked source file), a naive
  ``open(path, "a")`` follows the link and appends the tally line to the link
  target, corrupting or disclosing the pointee. ``safe_append_tally`` rejects a
  symlink target via ``Path.is_symlink()`` and, on platforms that support it,
  passes ``os.O_NOFOLLOW`` so the kernel refuses to open a final-component
  symlink even if one is planted after the stat check.
- CWE-367 (Time-of-check Time-of-use, TOCTOU race): a check on the path
  followed by a separate open leaves a window in which the entry can be swapped
  for a symlink. ``O_NOFOLLOW`` closes that window at the syscall boundary: the
  kernel performs the no-follow decision atomically with the open, so a swap
  that lands between the stat and the open still cannot redirect the write. The
  ``Path.is_symlink()`` pre-check remains as a fast, portable first gate and as
  the only gate on platforms lacking ``O_NOFOLLOW``.

The append itself takes an exclusive advisory lock (``fcntl.flock`` LOCK_EX on
POSIX, ``msvcrt.locking`` on Windows) so concurrent ``/spec`` runs serialize and
no tally line is interleaved or lost. The file descriptor is always closed in a
``finally`` block.

Exit codes (ADR-035): 0 = success, 1 = logic/validation error (symlink
rejected, traversal rejected, lock or write failure), 2 = usage error.

Usage:
    metrics_writer.py PATH LINE      # append LINE (one tally record) to PATH
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Cross-platform exclusive file locking. POSIX uses fcntl.flock; Windows uses
# msvcrt.locking on byte 0 (a fixed contention point for append-mode files).
if sys.platform == "win32":  # pragma: no cover - exercised only on Windows
    import msvcrt

    def _lock(fd: int) -> None:
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_LOCK, 1)

    def _unlock(fd: int) -> None:
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
else:
    import fcntl

    def _lock(fd: int) -> None:
        fcntl.flock(fd, fcntl.LOCK_EX)

    def _unlock(fd: int) -> None:
        fcntl.flock(fd, fcntl.LOCK_UN)

# os.O_NOFOLLOW is absent on some platforms (notably Windows). Fall back to 0 so
# the open flags compose; the Path.is_symlink() pre-check still guards there.
_O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_OPEN_FLAGS = os.O_WRONLY | os.O_APPEND | os.O_CREAT | _O_NOFOLLOW


class MetricsWriteError(Exception):
    """A tally append was rejected or failed.

    Raised for a symlink target (CWE-59), a parent-dir traversal escape, or an
    underlying lock/write failure. Callers translate this into exit code 1.
    """


def _reject_symlink(target: Path) -> None:
    """Raise if ``target`` is a symlink (the portable first TOCTOU gate)."""
    if target.is_symlink():
        raise MetricsWriteError(
            f"refusing to append to symlink (CWE-59 link following): {target}"
        )


def _resolve_under(target: Path, base: Path) -> Path:
    """Return ``target`` resolved, confirming it stays under ``base``.

    Rejects ``..`` traversal that would escape the allowed base directory. The
    base itself is resolved so a symlinked base does not produce a false escape.
    """
    resolved_base = base.resolve()
    # Resolve the parent (which must exist or be creatable) and re-attach the
    # final component, so a not-yet-existing tally file still resolves cleanly.
    resolved_parent = target.parent.resolve()
    candidate = resolved_parent / target.name
    if resolved_base not in candidate.parents and candidate != resolved_base:
        raise MetricsWriteError(
            f"refusing to append outside base directory (CWE-23 traversal): "
            f"{candidate} not under {resolved_base}"
        )
    return candidate


def safe_append_tally(
    path: str | os.PathLike[str],
    line: str,
    *,
    base_dir: str | os.PathLike[str] | None = None,
) -> Path:
    """Append one tally ``line`` to ``path``, hardened against symlink/TOCTOU.

    The target's parent directory is created lazily if absent. A symlink at the
    final path component is rejected (CWE-59) both by a ``Path.is_symlink()``
    pre-check and by opening with ``os.O_NOFOLLOW`` where supported, which also
    closes the check-then-open TOCTOU window (CWE-367). The append holds an
    exclusive advisory lock so concurrent writers serialize.

    ``line`` is written as a single record; a trailing newline is added if the
    caller did not supply one. When ``base_dir`` is given, the resolved target
    must stay under it or the write is rejected as a traversal escape.

    Returns the resolved path written. Raises ``MetricsWriteError`` on any
    rejection or failure.
    """
    target = Path(path)
    if base_dir is not None:
        target = _resolve_under(target, Path(base_dir))

    target.parent.mkdir(parents=True, exist_ok=True)

    # Pre-check: reject an already-present symlink before we touch the path.
    _reject_symlink(target)

    record = line if line.endswith("\n") else line + "\n"

    try:
        fd = os.open(target, _OPEN_FLAGS, 0o644)
    except OSError as exc:
        # ELOOP (or EMLINK on some kernels) is the O_NOFOLLOW refusal of a
        # symlink that was swapped in after the pre-check: report it as the
        # link-following rejection it is, not a generic write failure.
        raise MetricsWriteError(
            f"cannot open tally file {target} (symlink or open failure, "
            f"CWE-59/CWE-367): {exc}"
        ) from exc

    try:
        _lock(fd)
        try:
            os.write(fd, record.encode("utf-8"))
        finally:
            _unlock(fd)
    except OSError as exc:
        raise MetricsWriteError(f"failed to append tally to {target}: {exc}") from exc
    finally:
        os.close(fd)

    return target


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 2:
        print("usage: metrics_writer.py PATH LINE", file=sys.stderr)
        return 2
    path, line = args
    try:
        safe_append_tally(path, line)
    except MetricsWriteError as exc:
        print(f"metrics_writer: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover - thin entrypoint
    sys.exit(main())
