"""Defer cancellation signals while ``run(group=True)`` creates its child (ADR-127).

A grouped child runs in its own session, so a signal sent to the script never
reaches it; ``run`` must kill the child's process group when one arrives. A
handler that raises is unsafe while the child is being created: the exception
can leave ``Popen.__init__`` after the fork, or the gap between ``__enter__``
and the ``try`` that owns the cleanup, and the child would outlive the push
lock. It is also unsafe while the cleanup runs: a second signal that raised
before ``os.killpg`` would skip the kill (CWE-364).

``Cancellation`` has two modes:

* recording, from ``__enter__``: a handler records the first signal number and
  returns;
* raising, from ``arm(child)``, which ``run`` calls inside the cleanup scope. A
  handler first switches every handler back to recording, then kills the child's
  process group, then raises: KeyboardInterrupt for SIGINT, ``SystemExit(128 + n)``
  for the others. The child is dead before any exception exists, and a further
  signal is recorded, never raised. A signal recorded earlier takes the same path
  at once.

A signal the caller set to SIG_IGN stays ignored (``nohup``). ``__exit__``
restores every handler, then raises a signal recorded but never raised, so an
early return or a Popen failure cannot swallow it. When an exception is already
propagating, ``__exit__`` keeps it and drops the recorded signal. Handlers, not
a signal mask: a mask survives exec into the child, while a caught handler
resets to default.

Stdlib only, Python 3.10 floor. SIGHUP and SIGQUIT do not exist on Windows, so
they are looked up by name, and ``run`` builds a ``Cancellation`` only for a
grouped call, which is POSIX only.
"""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
from types import FrameType, TracebackType
from typing import Any

_CANCEL_SIGNALS = ("SIGINT", "SIGTERM", "SIGHUP", "SIGQUIT")


class Cancellation:
    """Context manager that makes a cancelling signal safe across child creation."""

    def __init__(self) -> None:
        self._saved: dict[int, Any] = {}
        self._pending: int | None = None
        self._child: subprocess.Popen[str] | None = None

    def __enter__(self) -> Cancellation:
        for name in _CANCEL_SIGNALS:
            signum = getattr(signal, name, None)
            if signum is None or signal.getsignal(signum) is signal.SIG_IGN:
                continue
            self._saved[signum] = signal.signal(signum, self._record)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        _exc: BaseException | None,
        _tb: TracebackType | None,
    ) -> None:
        for signum, handler in self._saved.items():
            signal.signal(signum, signal.SIG_DFL if handler is None else handler)
        if exc_type is None:
            self.raise_pending()

    def _record(self, signum: int, _frame: FrameType | None) -> None:
        if self._pending is None:
            self._pending = signum

    def defer(self) -> None:
        """Record, never raise, any further cancelling signal."""
        for signum in self._saved:
            signal.signal(signum, self._record)

    def arm(self, child: subprocess.Popen[str]) -> None:
        """Switch to raising mode for ``child``, then cancel on a signal recorded while recording."""
        self._child = child
        for signum in self._saved:
            signal.signal(signum, self._cancel)
        pending, self._pending = self._pending, None
        if pending is not None:
            self._cancel(pending, None)

    def _cancel(self, signum: int, _frame: FrameType | None) -> None:
        """Stop recording, kill a running child's group, then raise: no signal can skip the kill."""
        self.defer()
        child = self._child
        if child is not None and child.returncode is None:
            kill_child(child, self)
        _raise(signum)

    def raise_pending(self) -> None:
        """Raise the recorded signal once: KeyboardInterrupt for SIGINT, else SystemExit."""
        signum, self._pending = self._pending, None
        if signum is not None:
            _raise(signum)


def _raise(signum: int) -> None:
    if signum == signal.SIGINT:
        raise KeyboardInterrupt
    raise SystemExit(128 + signum)


def kill_child(child: subprocess.Popen[str], cancel: Cancellation | None) -> None:
    """Kill ``child``; when ``cancel`` is set, record any signal first and kill its whole process group."""
    if cancel is not None:
        cancel.defer()
        with contextlib.suppress(OSError):  # ESRCH: gone; EPERM: only zombies left
            os.killpg(child.pid, signal.SIGKILL)
    child.kill()
    if os.name == "nt":  # pragma: no cover - join the reader threads, as subprocess.run does
        child.communicate()
