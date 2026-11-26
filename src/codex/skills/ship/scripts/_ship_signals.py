"""Defer cancellation signals while ``run(group=True)`` creates its child (ADR-127).

A grouped child runs in its own session, so a signal sent to the script never
reaches it; ``run`` must kill the child's process group when one arrives. A
handler that raises is unsafe while the child is being created: the exception
can leave ``Popen.__init__`` after the fork, or the gap between ``__enter__``
and the ``try`` that owns the cleanup, and the child would outlive the push
lock.

``Cancellation`` has two modes:

* deferring, from ``__enter__``: a handler records the first signal number and
  returns;
* raising, from ``arm``, which ``run`` calls inside the cleanup scope: SIGINT
  raises KeyboardInterrupt and the others raise ``SystemExit(128 + n)``. A
  signal recorded earlier is raised at once, so ``kill_child`` runs.

A signal the caller set to SIG_IGN stays ignored (``nohup``). ``__exit__``
restores every handler, then raises a signal recorded but never raised, so an
early return or a Popen failure cannot swallow it. Handlers, not a signal mask:
a mask survives exec into the child, while a caught handler resets to default.

Stdlib only, Python 3.10 floor. SIGHUP and SIGQUIT do not exist on Windows, so
they are looked up by name, and ``run`` builds a ``Cancellation`` only for a
grouped call, which is POSIX only.
"""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
from types import FrameType
from typing import Any

_CANCEL_SIGNALS = ("SIGINT", "SIGTERM", "SIGHUP", "SIGQUIT")


def _exit_on_signal(signum: int, _frame: FrameType | None) -> None:
    raise SystemExit(128 + signum)


class Cancellation:
    """Context manager that makes a cancelling signal safe across child creation."""

    def __init__(self) -> None:
        self._saved: dict[int, Any] = {}
        self._pending: int | None = None

    def __enter__(self) -> Cancellation:
        for name in _CANCEL_SIGNALS:
            signum = getattr(signal, name, None)
            if signum is None or signal.getsignal(signum) is signal.SIG_IGN:
                continue
            self._saved[signum] = signal.signal(signum, self._record)
        return self

    def __exit__(self, *_exc: object) -> None:
        for signum, handler in self._saved.items():
            signal.signal(signum, signal.SIG_DFL if handler is None else handler)
        self.raise_pending()

    def _record(self, signum: int, _frame: FrameType | None) -> None:
        if self._pending is None:
            self._pending = signum

    def arm(self) -> None:
        """Switch to raising mode, then raise a signal recorded while deferring."""
        for signum in self._saved:
            raising = signal.default_int_handler if signum == signal.SIGINT else _exit_on_signal
            signal.signal(signum, raising)
        self.raise_pending()

    def raise_pending(self) -> None:
        """Raise the recorded signal once: KeyboardInterrupt for SIGINT, else SystemExit."""
        signum, self._pending = self._pending, None
        if signum is None:
            return
        if signum == signal.SIGINT:
            raise KeyboardInterrupt
        raise SystemExit(128 + signum)


def kill_child(child: subprocess.Popen[str], group: bool) -> None:
    """Kill ``child``, and with ``group`` its whole process group."""
    if group:
        with contextlib.suppress(OSError):  # ESRCH: gone; EPERM: only zombies left
            os.killpg(child.pid, signal.SIGKILL)
    child.kill()
    if os.name == "nt":  # pragma: no cover - join the reader threads, as subprocess.run does
        child.communicate()
