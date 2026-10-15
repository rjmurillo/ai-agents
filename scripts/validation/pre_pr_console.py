#!/usr/bin/env python3
"""Console helpers for the pre-PR runner: line buffering and once-per-run notes.

Python block-buffers stdout when it is a pipe or a file. A maintainer who ran
``pre_pr.py > log`` or piped it through ``tee`` saw a log stuck near 120 lines
for minutes, because the gate results sat in an 8 KiB buffer until it filled.
:func:`enable_line_buffering` flushes on every newline so a redirected log
tracks the run.

The base-ref resolvers run once per gate, and each gate asks again. Their
``[base-ref] selected ...`` note repeated about 900 times in one run.
:func:`note_once` prints a given note once per run; ``pre_pr.main`` clears the
record through ``checks_common._reset_gh_base_cache``.
"""

from __future__ import annotations

import sys

# Notes already printed this run.
_noted: set[str] = set()


def enable_line_buffering() -> None:
    """Make stdout and stderr flush on every newline, even when redirected.

    A stream without ``reconfigure`` (a test capture object) or one that
    rejects the call is left alone: buffering is a convenience, never a gate.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(line_buffering=True)
        except (OSError, ValueError):
            continue


def note_once(message: str) -> None:
    """Print ``message`` to stderr unless this run already printed it."""
    if message in _noted:
        return
    _noted.add(message)
    print(message, file=sys.stderr)


def reset_noted() -> None:
    """Forget every printed note so the next run prints them again."""
    _noted.clear()
