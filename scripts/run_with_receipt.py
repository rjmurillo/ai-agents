#!/usr/bin/env python3
"""Run a command and keep its bulk output out of model context (issue #5851).

Opt-in wrapper. No tool-use hook may intercept output (rule-tool-use-hook-bar.md,
ADR-097), so agents and skills call this explicitly for commands known to be
large (full test runs, builds, log dumps, wide greps).

Usage:
    run_with_receipt.py run [--max-inline-bytes N] [--timeout-seconds N]
                            [--out-dir DIR] -- CMD [ARG...]
    run_with_receipt.py read ARTIFACT [--offset N] [--length N] [--out-dir DIR]

``run`` executes CMD as an argv list (never through a shell), captures stdout
and stderr in arrival order, and redacts secrets in memory with
``redact_secrets.redact_ci_sink`` before any byte reaches disk or a terminal.

* Output at or below ``--max-inline-bytes`` (default 16384) passes through to the
  same streams, redacted, with no receipt and no artifact.
* Larger output is saved in full (redacted) to a file under the output dir
  (default ``.project-toolkit/temp/tool-output``, gitignored) and a bounded
  receipt is printed: command, exit code, duration, total bytes, exposed bytes,
  truncated flag, artifact path, and, on nonzero exit, a stderr tail.

``--timeout-seconds`` accepts a positive integer no larger than 4,294,967.
That bound keeps the millisecond timeout inside the Windows unsigned 32-bit
wait argument on every platform. When it is present the child command gets at
most that many seconds after launch. A wrapper-enforced timeout
returns 124, and a large-output receipt for one adds ``timeout: true``. A child
that exits 124 on its own is indistinguishable without that receipt line. Where
the platform has POSIX process groups, a timed child starts in a new session and
the wrapper stops the whole group, not only the leader. The stop sends SIGTERM
to the group, gives every group member a 1 second grace period (the wrapper
reaps the leader inside it, and the period ends early once the group is empty),
then sends SIGKILL to any member still left. Elsewhere the direct child is
killed.

On POSIX no member of a timed child's group is left running when the wrapper
returns. The group id is captured at spawn and the same stop runs on every exit
path: the deadline, a leader that exits early (its exit code is still the
result, and a background process it left behind is stopped), and a cancelled
wrapper. Cancelling means Ctrl-C, SIGTERM (exits 143), or SIGHUP (exits 129),
unless the caller installed its own SIGTERM or SIGHUP handler. A cancel that
arrives while the child is being spawned is held until the stop can run, then
acts as it would have otherwise. Ctrl-C is held that way only while Python's
default Ctrl-C handler is in place, and that handler is put back afterwards.
SIGKILL of the wrapper cannot be caught by any handler, so it leaves a timed
child tree running.

The deadline bounds the child command. The wrapper stops the child and its group
within the deadline plus 6 seconds in the worst case: 1 second of SIGTERM grace,
1 second to reap the leader, and up to 2 seconds for each of the two output pipe
drains when a process outside the group holds a pipe open. Redaction and artifact
writing run after that stop and take extra time in proportion to the output size.
The wrapper as a whole can therefore return later than that bound. A caller that
sets an outer timeout must allow for it, or the receipt and artifact are lost.

The shared validation runner is not reused here because it decodes through
text-mode ``communicate``; this wrapper needs byte streams so invalid UTF-8,
redaction, and line assembly keep their existing behavior. Its signal handler
is not imported from that runner either: ``scripts.validation`` is importable
only inside the project environment, and this script also runs under a plain
``python3``. The local copy is a separate function, not a mirror.

``read`` pages through a saved artifact by byte range. The artifact holds the
redacted bytes. Unredacted bytes are never written, so a retrieval cannot
return a secret the run did not already redact.

Exit codes: the wrapper returns the child's exit code (a signal death becomes
128 + signal), so a child exit of 2 or 3 cannot be told apart from the
wrapper's own codes without a receipt. Wrapper failures use the AGENTS.md
scheme: 2 = usage error, 3 = external failure (cannot launch the command, cannot
write or read the artifact). ``read`` returns 0 or 2/3 on those same terms.
"""

from __future__ import annotations

import argparse
import contextlib
import os
import re
import shlex
import signal
import subprocess
import sys
import threading
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from io import BufferedReader
from pathlib import Path
from typing import Protocol

from redact_secrets import redact_ci_sink

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_EXTERNAL = 3
EXIT_TIMEOUT = 124

DEFAULT_MAX_INLINE_BYTES = 16384
HEAD_BYTES = 2048
TAIL_BYTES = 2048
FAILURE_EXCERPT_BYTES = 2048
DEFAULT_READ_LENGTH = 8192
MAX_READ_LENGTH = 65536
READ_CHUNK = 65536
DEFAULT_OUT_SUBDIR = Path(".project-toolkit") / "temp" / "tool-output"
OUT_DIR_ENV = "TOOL_OUTPUT_DIR"

_SECRET_ENV_NAME = re.compile(
    r"(?i)(token|secret|passw(or)?d|passphrase|key|auth|cookie|credential|connection|dsn|(^|_)pat$)"
)
_MIN_SECRET_LENGTH = 4
_SECRET_FLAG = re.compile(r"^-{1,2}[\w-]+$")
_MASK = "***"
_ARTIFACT_NAME = re.compile(r"^\d{8}T\d{6}-[0-9a-f]{8}\.log$")
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


@dataclass(frozen=True, slots=True)
class Receipt:
    """Facts printed for a contained run. Text fields are already redacted."""

    command: str
    exit_code: int
    duration_s: float
    total_bytes: int
    exposed_bytes: int
    truncated: bool
    artifact: str
    head: str
    tail: str
    failure_excerpt: str
    timed_out: bool


def _secret_values() -> list[str]:
    return [
        value
        for name, value in os.environ.items()
        if _SECRET_ENV_NAME.search(name) and len(value) >= _MIN_SECRET_LENGTH
    ]


def _scrub(text: str) -> str:
    """Redact `text` with token shapes plus exact secret values from the env."""
    for value in sorted(_secret_values(), key=len, reverse=True):
        text = text.replace(value, _MASK)
    return str(redact_ci_sink(text).text)


def _is_secret_flag(flag: str) -> bool:
    """Match a `--flag` whose name hits the same pattern as secret env names."""
    if not _SECRET_FLAG.match(flag):
        return False
    return bool(_SECRET_ENV_NAME.search(flag.lstrip("-").replace("-", "_")))


def _mask_argv(argv: list[str]) -> list[str]:
    """Mask values that follow or join a secret-named flag, for the command echo."""
    masked: list[str] = []
    hide_next = False
    for arg in argv:
        if hide_next:
            masked.append(_MASK)
            hide_next = False
            continue
        flag, sep, _ = arg.partition("=")
        if sep and _SECRET_ENV_NAME.search(flag) and not flag.startswith("-"):
            masked.append(f"{flag}={_MASK}")
            continue
        if _is_secret_flag(flag):
            masked.append(f"{flag}={_MASK}" if sep else arg)
            hide_next = not sep
            continue
        masked.append(arg)
    return masked


def _decode(data: bytes) -> str:
    return data.decode("utf-8", errors="replace")


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


def _timeout_validation_error(timeout_seconds: int) -> str | None:
    if timeout_seconds < 1:
        return "--timeout-seconds must be a positive integer"
    if timeout_seconds > MAX_TIMEOUT_SECONDS:
        return "--timeout-seconds is too large"
    return None


def _validate_timeout_seconds(timeout_seconds: int | None) -> None:
    if timeout_seconds is None:
        return
    validation_error = _timeout_validation_error(timeout_seconds)
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


def _run_child(argv: list[str], timeout_seconds: int | None = None) -> tuple[int, Capture, bool]:
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
            _pump(proc.stdout, "out", capture)

    def pump_stderr() -> None:
        pipes_ready.wait()
        if not pumps_cancelled.is_set():
            _pump(proc.stderr, "err", capture)

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


def _find_repo_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (candidate / ".git").exists():
            return candidate
    return start


def resolve_out_dir(explicit: str | None) -> Path:
    chosen = explicit or os.environ.get(OUT_DIR_ENV)
    if chosen:
        return Path(chosen).expanduser().resolve()
    return _find_repo_root(Path.cwd().resolve()) / DEFAULT_OUT_SUBDIR


def _write_artifact(out_dir: Path, text: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = out_dir / f"{time.strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:8]}.log"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)
    return path


def _clip_bytes(text: str, limit: int, *, keep: str) -> str:
    """Return at most `limit` UTF-8 bytes from the head or tail of `text`."""
    data = text.encode("utf-8")
    if len(data) <= limit:
        return text
    piece = data[:limit] if keep == "head" else data[-limit:]
    return piece.decode("utf-8", errors="ignore")


def build_receipt(
    argv: list[str],
    exit_code: int,
    duration_s: float,
    capture: Capture,
    artifact: Path,
    redacted_merged: str,
    timed_out: bool,
) -> Receipt:
    total = len(capture.merged_bytes())
    head = _clip_bytes(redacted_merged, HEAD_BYTES, keep="head")
    tail = _clip_bytes(redacted_merged, TAIL_BYTES, keep="tail")
    fits = len(head.encode("utf-8")) + len(tail.encode("utf-8")) >= len(
        redacted_merged.encode("utf-8")
    )
    if fits:
        head, tail = redacted_merged, ""
    failure = ""
    if exit_code != 0:
        failure = _clip_bytes(
            _scrub(_decode(capture.stream_bytes("err"))), FAILURE_EXCERPT_BYTES, keep="tail"
        )
    exposed = sum(len(part.encode("utf-8")) for part in (head, tail, failure))
    return Receipt(
        command=_scrub(shlex.join(_mask_argv(argv))),
        exit_code=exit_code,
        duration_s=duration_s,
        total_bytes=total,
        exposed_bytes=exposed,
        truncated=not fits,
        artifact=str(artifact),
        head=head,
        tail=tail,
        failure_excerpt=failure,
        timed_out=timed_out,
    )


def format_receipt(receipt: Receipt) -> str:
    lines = [
        "[output contained: full output saved, excerpts below]",
        f"command: {receipt.command}",
        f"exit_code: {receipt.exit_code}",
    ]
    if receipt.timed_out:
        lines.append("timeout: true")
    lines += [
        f"duration_s: {receipt.duration_s:.2f}",
        f"total_bytes: {receipt.total_bytes}",
        f"exposed_bytes: {receipt.exposed_bytes}",
        f"truncated: {str(receipt.truncated).lower()}",
        f"artifact: {receipt.artifact}",
        "retrieve: run_with_receipt.py read <artifact> --offset N --length N",
        "--- output head ---",
        receipt.head,
    ]
    if receipt.tail:
        lines += ["--- output tail ---", receipt.tail]
    if receipt.failure_excerpt:
        lines += ["--- stderr tail (nonzero exit) ---", receipt.failure_excerpt]
    return "\n".join(lines).rstrip("\n") + "\n"


def _passthrough(capture: Capture) -> None:
    sys.stdout.write(_scrub(_decode(capture.stream_bytes("out"))))
    sys.stdout.flush()
    sys.stderr.write(_scrub(_decode(capture.stream_bytes("err"))))
    sys.stderr.flush()


def run_command(
    argv: list[str],
    max_inline_bytes: int,
    out_dir: Path,
    timeout_seconds: int | None = None,
) -> int:
    started = time.monotonic()
    try:
        exit_code, capture, timed_out = _run_child(argv, timeout_seconds)
    except OSError as exc:
        print(_scrub(f"run_with_receipt: cannot launch {argv[0]!r}: {exc}"), file=sys.stderr)
        return EXIT_EXTERNAL
    duration = time.monotonic() - started
    if len(capture.merged_bytes()) <= max_inline_bytes:
        _passthrough(capture)
        return exit_code
    redacted = _scrub(_decode(capture.merged_bytes()))
    try:
        artifact = _write_artifact(out_dir, redacted)
    except OSError as exc:
        print(f"run_with_receipt: cannot write artifact: {exc}", file=sys.stderr)
        return EXIT_EXTERNAL
    receipt = build_receipt(argv, exit_code, duration, capture, artifact, redacted, timed_out)
    sys.stdout.write(format_receipt(receipt))
    sys.stdout.flush()
    return exit_code


def _is_inside(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def read_artifact(artifact: str, offset: int, length: int, out_dir: Path) -> int:
    """Print `length` bytes of a saved artifact from `offset` (CWE-22 guarded)."""
    path = Path(artifact).expanduser().resolve()
    if not _is_inside(path, out_dir) or not _ARTIFACT_NAME.match(path.name):
        print("run_with_receipt: not a saved artifact under the output dir", file=sys.stderr)
        return EXIT_USAGE
    if offset < 0 or length < 1:
        print("run_with_receipt: offset must be >= 0 and length >= 1", file=sys.stderr)
        return EXIT_USAGE
    length = min(length, MAX_READ_LENGTH)
    try:
        size = path.stat().st_size
        with path.open("rb") as handle:
            handle.seek(offset)
            data = handle.read(length)
    except OSError as exc:
        print(f"run_with_receipt: cannot read artifact: {exc}", file=sys.stderr)
        return EXIT_EXTERNAL
    sys.stdout.write(_scrub(_decode(data)))
    sys.stdout.flush()
    end = offset + len(data)
    more = f" next_offset={end}" if end < size else " end_of_artifact"
    print(f"\n[range {offset}-{end} of {size} bytes;{more}]", file=sys.stderr)
    return EXIT_OK


def _split_command(argv: list[str]) -> tuple[list[str], list[str]]:
    if "--" not in argv:
        return argv, []
    index = argv.index("--")
    return argv[:index], argv[index + 1 :]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="run_with_receipt.py", description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="mode", required=True)
    run = sub.add_parser("run", help="run CMD after `--`, contain large output")
    run.add_argument("--max-inline-bytes", type=int, default=DEFAULT_MAX_INLINE_BYTES)
    run.add_argument(
        "--timeout-seconds",
        type=int,
        default=None,
        metavar="N",
        help=(
            "stop CMD after N seconds and return 124. On POSIX the whole process group "
            "is stopped on every exit, including SIGTERM and SIGHUP to this wrapper; "
            "SIGKILL of this wrapper cannot be caught and leaves the group running"
        ),
    )
    run.add_argument("--out-dir", default=None)
    read = sub.add_parser("read", help="page through a saved artifact by byte range")
    read.add_argument("artifact")
    read.add_argument("--offset", type=int, default=0)
    read.add_argument("--length", type=int, default=DEFAULT_READ_LENGTH)
    read.add_argument("--out-dir", default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    own, command = _split_command(raw)
    try:
        args = _build_parser().parse_args(own)
    except SystemExit as exc:
        return EXIT_OK if exc.code in (0, None) else EXIT_USAGE
    out_dir = resolve_out_dir(args.out_dir)
    if args.mode == "read":
        return read_artifact(args.artifact, args.offset, args.length, out_dir)
    if args.timeout_seconds is not None:
        validation_error = _timeout_validation_error(args.timeout_seconds)
        if validation_error is not None:
            print(f"run_with_receipt: {validation_error}", file=sys.stderr)
            return EXIT_USAGE
    if not command or args.max_inline_bytes < 0:
        print("usage: run_with_receipt.py run [options] -- CMD [ARG...]", file=sys.stderr)
        return EXIT_USAGE
    return run_command(command, args.max_inline_bytes, out_dir, args.timeout_seconds)


if __name__ == "__main__":
    sys.exit(main())
