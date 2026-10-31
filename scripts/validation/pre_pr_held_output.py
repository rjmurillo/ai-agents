#!/usr/bin/env python3
"""Hold one gate's stdout so ``pre_pr.py --compact`` prints only what failed.

Under ``--compact`` (the pre-push hook, issue #6734) a gate that proves its
contract prints nothing. :class:`HeldOutput` holds one gate's stdout so the
runner can drop it on PASS or an already-run SKIP and release it, file and line
included, when the gate fails.
"""

from __future__ import annotations

import contextlib
import io
import sys
import threading
from types import TracebackType

#: Seconds a held gate may run before its name is printed anyway.
SLOW_AFTER_SECONDS = 30.0


class HeldOutput:
    """Hold stdout written inside a ``with`` block until :meth:`release` is called.

    With ``enabled`` False the block writes straight through and
    :meth:`release` does nothing. Output a child process writes to the inherited
    file descriptor is not held. That keeps failure text, never hides it, but a
    failing gate's child output can print above the ``=== name ===`` header
    that :meth:`release` writes later. An exception leaving the block releases
    what was held.

    Lefthook kills a job at its timeout with SIGKILL, which no handler can
    catch, so held output dies with it and a hung gate would leave no name in
    the log. A gate still running after ``SLOW_AFTER_SECONDS`` therefore prints
    one ``[SLOW]`` line naming ``label`` straight to the real stdout.
    """

    def __init__(self, enabled: bool, label: str = "") -> None:
        self._label = label
        self._stdout = sys.stdout
        self._buffer = io.StringIO() if enabled else None
        self._redirect = (
            contextlib.redirect_stdout(self._buffer) if self._buffer is not None else None
        )
        self._timer: threading.Timer | None = None

    def _announce_slow(self) -> None:
        self._stdout.write(f"[SLOW] {self._label} still running after {SLOW_AFTER_SECONDS:g}s\n")
        self._stdout.flush()

    def __enter__(self) -> HeldOutput:
        if self._redirect is not None:
            self._redirect.__enter__()
            self._timer = threading.Timer(SLOW_AFTER_SECONDS, self._announce_slow)
            self._timer.daemon = True
            self._timer.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._timer is not None:
            self._timer.cancel()
            self._timer.join()
        if self._redirect is not None:
            self._redirect.__exit__(exc_type, exc, traceback)
        if exc_type is not None:
            # A gate that exits the process (SystemExit) or is interrupted never
            # reaches the caller's release, so its output is written here.
            self.release()

    def release(self) -> None:
        """Write everything held to the real stdout."""
        if self._buffer is not None:
            self._stdout.write(self._buffer.getvalue())
