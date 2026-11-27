"""Child launch, output capture, and deadline enforcement for run_with_receipt.py.

This module owns one concern: start a command without a shell, collect its byte
streams, and make sure a timed child and its process group cannot outlive the
deadline or a cancelled wrapper. ``run_with_receipt.py`` documents the
user-visible contract (exit 124, the stop sequence, the worst-case bound) and
owns redaction, receipts, artifacts, and the CLI.

Stdlib only: the wrapper also runs under a plain ``python3`` outside the
project environment, and finds this module beside it on ``sys.path``.
"""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from io import BufferedReader
from typing import Protocol, cast

EXIT_TIMEOUT = 124
READ_CHUNK = 65536
_PIPE_DRAIN_GRACE_S = 2.0
_TERM_GRACE_S = 1.0
_GROUP_POLL_S = 0.05
_REAP_GRACE_S = 1.0
MAX_TIMEOUT_SECONDS = (2**32 - 1) // 1000
_SUPPORTS_PGROUP = sys.platform != "win32" and hasattr(os, "killpg")


class _ChildProcess(Protocol):
    @property
    def pid(self) -> int: ...

    def wait(self, timeout: float | None = None) -> int: ...

    def kill(self) -> None: ...


@dataclass(slots=True)
class Capture:
    """Child output as per-stream buffers plus a line-assembled merged view.

    The merged view orders whole lines by completion time. A line is emitted
    only once its newline arrives (or at ``finish``), so a secret written in
    pieces with the other stream's output in between is rejoined before
    redaction instead of being split by the interleave.
    """

    streams: dict[str, bytearray] = field(
        default_factory=lambda: {"out": bytearray(), "err": bytearray()}
    )
    partial: dict[str, bytearray] = field(
        default_factory=lambda: {"out": bytearray(), "err": bytearray()}
    )
    lines: list[bytes] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def add(self, stream: str, data: bytes) -> None:
        with self.lock:
            self.streams[stream] += data
            buffer = self.partial[stream]
            buffer += data
            while (index := buffer.find(b"\n")) >= 0:
                self.lines.append(bytes(buffer[: index + 1]))
                del buffer[: index + 1]

    def finish(self) -> None:
        """Flush unterminated trailing lines, stdout first."""
        with self.lock:
            for stream in ("out", "err"):
                if self.partial[stream]:
                    self.lines.append(bytes(self.partial[stream]))
                    self.partial[stream].clear()

    def stream_bytes(self, stream: str) -> bytes:
        return bytes(self.streams[stream])

    def merged_bytes(self) -> bytes:
        return b"".join(self.lines)


def _pump(pipe: BufferedReader, stream: str, capture: Capture) -> None:
    while True:
        data = pipe.read1(READ_CHUNK)
        if not data:
            return
        capture.add(stream, data)


def _signal_group(pgid: int, sig: int) -> None:
    """Signal a process group, ignoring a group that no longer exists."""
    if sys.platform == "win32":
        return
    try:
        os.killpg(pgid, sig)
    except OSError:
        pass


def _own_group(pid: int) -> int | None:
    """Return a safe child-led process group, or None when none is available."""
    if sys.platform == "win32":
        return None
    try:
        pgid = os.getpgid(pid)
    except OSError:
        return None
    return None if pgid == os.getpgid(0) else pgid


def _terminate_child(proc: _ChildProcess, pgid: int | None = None) -> None:
    """Stop a timed child's process group, or the child where groups are absent.

    `pgid` is the group id captured at spawn. The leader's pid cannot find the
    group once the leader is reaped, so a caller that may stop the group after
    that passes the captured id. Without one, the group is looked up here.
    """
    if sys.platform == "win32" or not _SUPPORTS_PGROUP:
        proc.kill()
        return
    if pgid is None:
        pgid = _own_group(proc.pid)
    if pgid is None:
        proc.kill()
        return
    _signal_group(pgid, signal.SIGTERM)
    deadline = time.monotonic() + _TERM_GRACE_S
    try:
        # Reaping the leader ends its zombie but not the window: other group
        # members keep the rest of it for their own SIGTERM handlers.
        proc.wait(timeout=_TERM_GRACE_S)
        while _group_alive(pgid) and (left := deadline - time.monotonic()) > 0:
            time.sleep(min(left, _GROUP_POLL_S))
    except subprocess.TimeoutExpired:
        pass
    finally:
        # A group that is already empty has no member to kill, and its id may be
        # reused by an unrelated group once the leader is reaped.
        if _group_alive(pgid):
            _signal_group(pgid, signal.SIGKILL)


def _group_alive(pgid: int) -> bool:
    """True while any process is still in group `pgid`."""
    if sys.platform == "win32":
        return False
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True
    return True


def _reap_stopped_child(proc: _ChildProcess) -> None:
    try:
        proc.wait(timeout=_REAP_GRACE_S)
    except subprocess.TimeoutExpired:
        pass


def _cancel_signals() -> list[int]:
    """Signals that cancel a timed run: SIGTERM, plus SIGHUP where it exists."""
    names = ("SIGTERM", "SIGHUP")
    return [getattr(signal, name) for name in names if hasattr(signal, name)]


def timeout_validation_error(timeout_seconds: int) -> str | None:
    if timeout_seconds < 1:
        return "--timeout-seconds must be a positive integer"
    if timeout_seconds > MAX_TIMEOUT_SECONDS:
        return "--timeout-seconds is too large"
    return None


def _validate_timeout_seconds(timeout_seconds: int | None) -> None:
    if timeout_seconds is None:
        return
    validation_error = timeout_validation_error(timeout_seconds)
    if validation_error is not None:
        raise ValueError(validation_error)


class _SpawnWindow:
    """Hold cancel signals while a timed child is being spawned.

    ``Popen`` forks the child and then keeps running Python code before it
    returns. A handler that raises in that stretch unwinds ``Popen`` after the
    child exists but before this module holds a handle to it, and ``Popen`` does
    not kill a child it fails to return. While the window is open, SIGTERM and
    SIGHUP (and Ctrl-C, when Python's default handler owns it) are recorded here
    instead, and ``raise_pending`` delivers the first one once the guard that
    stops the child's group is in place. No signal mask is used: a blocked mask
    would be inherited by the child across exec. Once a cancel has been
    delivered, later SIGTERM and SIGHUP instances are recorded here too: a
    repeat cancel must not unwind the cleanup before the child's group is
    stopped.
    """

    __slots__ = ("_sigint_held", "delivered", "is_open", "pending")

    def __init__(self) -> None:
        self.is_open = False
        self.delivered = False
        self.pending: int | None = None
        self._sigint_held = False

    def record(self, signum: int, _frame: object = None) -> None:
        if self.pending is None:
            self.pending = signum

    def open(self) -> None:
        self.is_open = True
        if signal.getsignal(signal.SIGINT) is signal.default_int_handler:
            signal.signal(signal.SIGINT, self.record)
            self._sigint_held = True

    def close(self) -> None:
        """Stop holding signals. Safe to call more than once, on any path."""
        if self._sigint_held:
            self._sigint_held = False
            signal.signal(signal.SIGINT, signal.default_int_handler)
        self.is_open = False

    def raise_pending(self) -> None:
        """Deliver a held signal the way its handler would have, if one is held."""
        signum, self.pending = self.pending, None
        if signum is None:
            return
        self.delivered = True
        if signum == signal.SIGINT:
            raise KeyboardInterrupt
        raise SystemExit(128 + signum)


@contextlib.contextmanager
def _cancel_signals_raise() -> Iterator[_SpawnWindow | None]:
    """Turn SIGTERM and SIGHUP into ``SystemExit`` while a timed child runs.

    A timed child lives in its own session, so a SIGTERM or a terminal hangup
    sent to this process never reaches it, and the default action would end this
    process with the child still running. ``SystemExit`` instead unwinds through
    ``_spawn_and_collect``, which stops the child's group. Each signal is judged
    alone: only a default action is replaced, and it is restored to the default
    on every exit path. Nothing is replaced off the main thread, where
    ``signal.signal`` fails. SIGKILL cannot be handled, so it is not covered.

    The yielded ``_SpawnWindow`` holds those signals, and Ctrl-C, while the child
    is being spawned. It is None where no handler is installed. A handler the
    caller installed is never replaced or held.
    """
    if not _SUPPORTS_PGROUP or threading.current_thread() is not threading.main_thread():
        yield None
        return

    window = _SpawnWindow()

    restoring = False

    def _stop(signum: int, _frame: object) -> None:
        if window.is_open or restoring or window.delivered:
            window.record(signum)
            return
        window.delivered = True
        raise SystemExit(128 + signum)

    installed: list[int] = []
    try:
        for sig in _cancel_signals():
            if signal.getsignal(sig) is signal.SIG_DFL:
                installed.append(sig)
                signal.signal(sig, _stop)
        yield window
    finally:
        restoring = True
        try:
            window.close()
            for sig in installed:
                signal.signal(sig, signal.SIG_DFL)
        finally:
            restoring = False
        window.raise_pending()


def run_child(argv: list[str], timeout_seconds: int | None = None) -> tuple[int, Capture, bool]:
    """Run argv without a shell and return the exit code, output, and timeout state."""
    if timeout_seconds is None:
        return _spawn_and_collect(argv, None)
    with _cancel_signals_raise() as window:
        return _spawn_and_collect(argv, timeout_seconds, window)


def _launch_with_pumps(
    argv: list[str],
    timeout_seconds: int | None,
    window: _SpawnWindow | None,
    threads: list[threading.Thread],
    pipes_ready: threading.Event,
    pumps_cancelled: threading.Event,
) -> subprocess.Popen[bytes]:
    # A cancel that lands inside Popen is held, not raised: Popen would unwind
    # with the child already forked and no handle to stop it. The pump threads
    # are inside the window too, so their startup cannot become a gap between
    # launch and deadline enforcement.
    if window is not None:
        window.open()
    try:
        for thread in threads:
            thread.start()
        if timeout_seconds is None:
            return subprocess.Popen(
                argv,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,
            )
        return subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            start_new_session=_SUPPORTS_PGROUP,
        )
    except BaseException:
        pumps_cancelled.set()
        pipes_ready.set()
        # No child exists. A held cancel replaces the launch error, as the
        # handler would have raised in its place.
        if window is not None:
            window.close()
            window.raise_pending()
        raise


def _spawn_and_collect(
    argv: list[str], timeout_seconds: int | None, window: _SpawnWindow | None = None
) -> tuple[int, Capture, bool]:
    _validate_timeout_seconds(timeout_seconds)

    capture: Capture
    pipes_ready = threading.Event()
    pumps_cancelled = threading.Event()

    def pump_stdout() -> None:
        pipes_ready.wait()
        if not pumps_cancelled.is_set():
            _pump(cast(BufferedReader, proc.stdout), "out", capture)

    def pump_stderr() -> None:
        pipes_ready.wait()
        if not pumps_cancelled.is_set():
            _pump(cast(BufferedReader, proc.stderr), "err", capture)

    threads = [
        threading.Thread(target=pump_stdout, daemon=True),
        threading.Thread(target=pump_stderr, daemon=True),
    ]

    proc = _launch_with_pumps(argv, timeout_seconds, window, threads, pipes_ready, pumps_cancelled)
    # The guard opens right after Popen returns: a cancel that lands later in this
    # function must still stop a timed child that lives in its own session. A new
    # session makes the leader's pid its group id, so no lookup can lose it to
    # auto-reaping.
    wait_deadline = None if timeout_seconds is None else time.monotonic() + timeout_seconds
    pgid = proc.pid if timeout_seconds is not None and _SUPPORTS_PGROUP else None
    group_stopped = False
    timed_out = False
    try:
        if window is not None:
            # Signals held since before the spawn are raised here, inside the
            # guard, so the unwind below stops the child's group.
            window.close()
            window.raise_pending()
        try:
            capture = Capture()
            pipes_ready.set()
            wait_timeout = None
            if wait_deadline is not None:
                wait_timeout = max(0.0, wait_deadline - time.monotonic())
            code = proc.wait(timeout=wait_timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            _terminate_child(proc, pgid)
            group_stopped = True
            _reap_stopped_child(proc)
            code = EXIT_TIMEOUT
        else:
            # The leader exited by itself. Its group can still hold members that
            # outlive it, and the deadline must bound those too.
            if pgid is not None and _group_alive(pgid):
                _terminate_child(proc, pgid)
            # The group is now stopped or was empty. With the leader reaped, its
            # pid and group id are free for reuse, so nothing signals them again.
            group_stopped = True
        # A grandchild can keep a pipe open after the child exits; do not wait on it.
        for thread in threads:
            thread.join(timeout=_PIPE_DRAIN_GRACE_S)
    except BaseException:
        # Ctrl-C, a forwarded SIGTERM or SIGHUP, or any other unwind must not
        # leave a timed child running in its own session. An untimed child keeps
        # the caller's process group, so the caller's signal already reaches it.
        # A group that is already stopped or found empty is not signalled again.
        pumps_cancelled.set()
        pipes_ready.set()
        if timeout_seconds is not None and not group_stopped:
            _terminate_child(proc, pgid)
            _reap_stopped_child(proc)
        raise
    capture.finish()
    return (128 - code if code < 0 else code), capture, timed_out
