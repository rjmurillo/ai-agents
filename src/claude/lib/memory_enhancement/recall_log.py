"""One-line stderr notes for recall (issue #7493, ADR-109 amendment 2026-11-20).

Recall reports only when it cuts work: a deadline, a timeout, a candidate cap,
a rejected directory. A normal run prints nothing. Notes carry counts and
paths, never prompt text or memory content.
"""

from __future__ import annotations

import sys

_PREFIX = "memory-recall:"
_seen: set[str] = set()


def note(message: str) -> None:
    """Print one ``memory-recall:`` line to stderr."""
    print(f"{_PREFIX} {message}", file=sys.stderr)


def note_once(key: str, message: str) -> None:
    """Print *message* the first time *key* is seen in this process."""
    if key in _seen:
        return
    _seen.add(key)
    note(message)
