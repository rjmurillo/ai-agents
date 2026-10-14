#!/usr/bin/env python3
"""Subprocess wrapper shared by the pre-PR validation check modules.

Split out of ``checks_common`` (issue #4955) so the timeout path can preserve
the partial stdout and stderr Python leaves on ``TimeoutExpired``. Discarding
that output hid the ratchet or validator result that ran just before a
merge-tree timeout (issue #4876): the maintainer saw the timeout but not the
diagnostic that explained where the child stopped.

``checks_common`` re-exports :func:`_run_subprocess`, so every existing
``from checks_common import _run_subprocess`` keeps resolving.

On timeout the whole process group dies, not only the direct child (issue
#6412). ``subprocess.run(timeout=)`` kills just the direct child, so a
``gh act`` grandchild kept its ports bound after the gate that started it had
already failed. The group gets SIGTERM, a short grace window, then SIGKILL. A
descendant that started its own session is outside the group, so the child that
started it must forward the stop itself (``run_workflow_local_test`` does).
While a child runs on the main thread, a SIGTERM to this process becomes
``SystemExit`` so the same cleanup stops the child's group.

Every child runs in a new session, so it has no controlling terminal. A child
that prompts through ``/dev/tty`` (ssh passphrase, git credential prompt, gpg
pinentry) fails instead of prompting. The callers here run unattended gates.
"""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import sys
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Protocol

from scripts.cli_exec import resolve_executable

# Reason codes for the typed evidence contract (issue #5635).
from scripts.validation.evidence import (
    REASON_PROCESS_SIGNALED,
    REASON_TIMEOUT,
    REASON_TOOL_ABSENT,
)

# The exit code :func:`_run_subprocess` returns when the child never produced
# one of its own: a timeout or a missing executable. Any other non-zero value
# came from the child itself.
_SENTINEL_EXIT = -1

# True where ``os.killpg`` exists. Where it does not (Windows), the child gets
# no session of its own and a timeout kills the direct child only.
_SUPPORTS_PGROUP = hasattr(os, "killpg")

# Seconds to wait for the pipes to close after the kill. A grandchild that
# started its own session survives the group kill and keeps the pipe open, so
# an unbounded read would hang the gate this wrapper exists to bound.
_DRAIN_TIMEOUT = 5

# Seconds the group leader gets between SIGTERM and SIGKILL to stop children
# that live in sessions of their own. It must outlast the 3 second window that
# run_workflow_local_test gives gh act, plus time to send its SIGKILL. A shorter
# window ends the wrapper mid-cleanup and gh act survives (issue #6412).
_TERM_GRACE = 5.0


def _decode_stream(data: bytes | str | None) -> str:
    """Decode a captured subprocess stream with UTF-8 replacement semantics.

    ``subprocess.run(encoding="utf-8", errors="replace")`` returns ``str`` on
    the happy path, but a timeout raises inside ``Popen`` before the decode
    step, so ``TimeoutExpired.stdout`` and ``.stderr`` arrive as raw ``bytes``
    on POSIX and as already-decoded ``str`` on the Windows
    kill-then-communicate path. Match the happy-path ``errors="replace"``
    decode and treat a missing stream as empty.
    """
    if data is None:
        return ""
    if isinstance(data, bytes):
        return data.decode("utf-8", errors="replace")
    return data


class _Child(Protocol):
    """The slice of ``subprocess.Popen`` that :func:`_terminate` uses."""

    @property
    def pid(self) -> int: ...

    def wait(self, timeout: float | None = None) -> int: ...

    def kill(self) -> None: ...


def _signal_group(pgid: int, sig: int) -> None:
    """Send ``sig`` to process group ``pgid``. A group that is already gone is ignored.

    The ``sys.platform`` checks in this module exist for mypy: it cannot read a
    ``hasattr`` guard, and ``os.killpg``, ``os.getpgid`` and ``signal.SIGKILL``
    are absent on Windows.
    """
    if sys.platform == "win32":
        return
    try:
        os.killpg(pgid, sig)
    except OSError:
        pass


def _own_group(pid: int) -> int | None:
    """Return the process group led by ``pid``, or None when signalling it is unsafe.

    A reaped pid has no group. The caller's own group is excluded too, because
    that is where a child that never reached ``setsid`` still lives.
    """
    if sys.platform == "win32":
        return None
    try:
        pgid = os.getpgid(pid)
    except OSError:
        return None
    return None if pgid == os.getpgid(0) else pgid


def _terminate(proc: _Child) -> None:
    """Stop the child's process group, or the child alone where groups are absent.

    SIGTERM goes first and the group leader gets ``_TERM_GRACE`` seconds to run
    its handlers. A wrapper such as ``run_workflow_local_test`` uses that window
    to stop a ``gh act`` it started in a session of its own, which a group kill
    from here cannot reach (issue #6412). SIGKILL then ends whatever is left.
    """
    if sys.platform == "win32" or not _SUPPORTS_PGROUP:
        proc.kill()
        return
    pgid = _own_group(proc.pid)
    if pgid is None:
        # No group of its own to signal. Kill the direct child, or the caller's
        # untimed wait on it never returns. Popen.kill skips a reaped child.
        proc.kill()
        return
    _signal_group(pgid, signal.SIGTERM)
    try:
        proc.wait(timeout=_TERM_GRACE)
    except subprocess.TimeoutExpired:
        pass
    finally:
        # Ctrl-C or a forwarded SIGTERM can end the wait early. SIGKILL still
        # goes out, or a child that ignores SIGTERM keeps running.
        _signal_group(pgid, signal.SIGKILL)


@contextlib.contextmanager
def _sigterm_raises() -> Iterator[None]:
    """Turn SIGTERM into ``SystemExit`` while a child runs, then restore the default.

    The child runs in a session of its own, so a SIGTERM aimed at this process,
    or at its process group, never reaches the child. Under the default action
    this process would die at once and the child would keep running, holding
    any ports it bound. ``SystemExit`` unwinds through the ``BaseException``
    branch of :func:`_run_in_group`, which stops the child's group.

    Only the default action is replaced: a caller that installed its own
    handler keeps it. ``signal.signal`` works only on the main thread, so a
    worker thread runs without the handler.
    """
    if (
        not _SUPPORTS_PGROUP
        or threading.current_thread() is not threading.main_thread()
        or signal.getsignal(signal.SIGTERM) is not signal.SIG_DFL
    ):
        yield
        return

    def _stop(_signum: int, _frame: object) -> None:
        raise SystemExit(128 + signal.SIGTERM)

    signal.signal(signal.SIGTERM, _stop)
    try:
        yield
    finally:
        signal.signal(signal.SIGTERM, signal.SIG_DFL)


def _reap_timed_out(
    proc: subprocess.Popen[str], timed_out: subprocess.TimeoutExpired
) -> tuple[str, str]:
    """Kill a timed-out child's tree and return the stdout and stderr it wrote.

    The post-kill read holds everything the child flushed, including what the
    first ``communicate`` already consumed. If a grandchild outside the group
    keeps the pipe open the read times out too, and the partial output from
    that attempt (or from the first) is returned instead of blocking.
    """
    _terminate(proc)
    drained: tuple[bytes | str | None, bytes | str | None]
    try:
        drained = proc.communicate(timeout=_DRAIN_TIMEOUT)
    except subprocess.TimeoutExpired as still_open:
        drained = (still_open.stdout, still_open.stderr)
    stdout = _decode_stream(drained[0]) or _decode_stream(timed_out.stdout)
    stderr = _decode_stream(drained[1]) or _decode_stream(timed_out.stderr)
    return stdout, stderr


def _run_in_group(
    command: list[str],
    timeout: int,
    cwd: Path | str | None,
    env: dict[str, str] | None,
) -> tuple[int, str, str]:
    """Run ``command`` in its own session so a timeout can kill its whole tree."""
    with (
        _sigterm_raises(),
        subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
            errors="replace",
            cwd=cwd,
            env=env,
            start_new_session=_SUPPORTS_PGROUP,
        ) as proc,
    ):
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired as timed_out:
            partial_stdout, partial_stderr = _reap_timed_out(proc, timed_out)
            marker = f"Command timed out after {timeout}s"
            combined = f"{partial_stderr}\n{marker}" if partial_stderr else marker
            return _SENTINEL_EXIT, partial_stdout, combined
        except BaseException:
            _terminate(proc)
            raise
    return proc.returncode, stdout, stderr


def _run_subprocess(
    args: list[str],
    timeout: int = 300,
    cwd: Path | str | None = None,
    env: dict[str, str] | None = None,
) -> tuple[int, str, str]:
    """Run a subprocess after resolving its executable for the target platform.

    When ``env`` is provided it replaces the child environment entirely, so
    callers that only want to add a variable should merge it with
    ``os.environ`` themselves before passing it in.

    On a timeout the child's whole process group is killed, so a grandchild
    such as the ``gh-act`` artifact server does not survive to hold its ports
    (issue #6412). The partial stdout and stderr the child flushed before the
    timeout are preserved (issue #4955) instead of being discarded. The timeout
    stays a failure: the exit code is ``-1`` and the ``Command timed out after
    Ns`` marker stays in the returned stderr, after any partial stderr the
    child produced.
    """
    try:
        executable = args[0] if os.path.dirname(args[0]) else resolve_executable(args[0], env=env)
        return _run_in_group([executable, *args[1:]], timeout, cwd, env)
    except FileNotFoundError:
        return -1, "", f"Command not found: {args[0]}"


def classify_subprocess_failure(exit_code: int, stderr: str, *, default: str) -> str:
    """Return the evidence reason code for a failed :func:`_run_subprocess` call.

    A timed-out child and a child that ran and exited non-zero are different
    findings with different remedies, and ``_run_subprocess`` reports both as
    exit ``-1`` versus a real code. Collapsing them into one reason costs the
    reader the first diagnostic step, which is the defect
    ``.claude/rules/ci-scripts.md`` MUST 14 records for the count ratchets and
    the reason ``evidence.py`` keeps BLOCKED and UNKNOWN apart.

    The two markers are :func:`_run_subprocess`'s documented contract,
    quoted verbatim from the source above:

        marker = f"Command timed out after {timeout}s"
        return -1, "", f"Command not found: {args[0]}"

    A negative return code that matches neither marker is a child killed by a
    signal: :func:`subprocess.run` reports that as the negated signal number,
    so ``-9`` is SIGKILL and ``-15`` is SIGTERM. Those are not verdicts, and
    before issue #5653 they fell through to ``default`` and were read as the
    child's own findings exit: an actionlint killed by the OOM killer became
    workflow violations that do not exist, and a killed yamllint became a
    tolerated-findings PASS.

    A bare ``-1`` with no marker belongs in that class too. This wrapper always
    writes a marker when it returns ``-1`` itself, so a markerless ``-1`` is not
    the sentinel, it is SIGHUP.

    The rule is therefore the sign, not the sentinel: a negative code means the
    child did not choose its own exit, so it cannot carry a finding.

    ``default`` is the caller's own reason for an ordinary non-zero exit, since
    only the caller knows what its child was doing (issue #5635).
    """
    if exit_code == _SENTINEL_EXIT:
        if "Command timed out after" in stderr:
            return REASON_TIMEOUT
        if "Command not found:" in stderr:
            return REASON_TOOL_ABSENT
    if exit_code < 0:
        return REASON_PROCESS_SIGNALED
    return default
