"""An interrupt must not leave ``Popen.__exit__`` closing a pipe a reader holds.

CWE-667: on Windows, closing a pipe object while a reader thread is blocked in
a synchronous read can block the closing thread. The timeout path already
abandons live streams first. These tests drive the interrupt path with a fake
whose ``__exit__`` records what stream state ``Popen.__exit__`` would see.
"""

from __future__ import annotations

import threading
from typing import Any, cast

import pytest

from scripts.validation import subprocess_runner
from scripts.validation.subprocess_runner import _run_in_group
from scripts.validation.windows_pipes import _PIPE_STATE_ATTR, _PipeReader


class _InterruptedPopen:
    """Fake child whose ``communicate`` is interrupted, as Ctrl-C would."""

    pid = 4242
    returncode = -9

    def __init__(self, readers: dict[str, _PipeReader] | None) -> None:
        self.stdout: object | None = object()
        self.stderr: object | None = object()
        self.seen_at_exit: tuple[object | None, object | None] | None = None
        self.kills = 0
        if readers is not None:
            setattr(self, _PIPE_STATE_ATTR, readers)

    def communicate(self, timeout: float | None = None) -> tuple[str, str]:
        raise KeyboardInterrupt

    def kill(self) -> None:
        self.kills += 1

    def wait(self, timeout: float | None = None) -> int:
        return self.returncode

    def __enter__(self) -> _InterruptedPopen:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.seen_at_exit = (self.stdout, self.stderr)


class _Job:
    def __init__(self, *, terminate_error: Exception | None = None) -> None:
        self.events: list[str] = []
        self._terminate_error = terminate_error

    def terminate(self) -> None:
        self.events.append("terminate")
        if self._terminate_error is not None:
            raise self._terminate_error

    def close(self) -> None:
        self.events.append("close")


def _live_reader(release: threading.Event) -> _PipeReader:
    thread = threading.Thread(target=release.wait, daemon=True)
    thread.start()
    return _PipeReader([], thread)


def _finished_reader() -> _PipeReader:
    thread = threading.Thread(target=lambda: None)
    thread.start()
    thread.join()
    return _PipeReader([], thread)


def _install(monkeypatch: pytest.MonkeyPatch, proc: _InterruptedPopen, job: _Job | None) -> None:
    monkeypatch.setattr(subprocess_runner.os, "name", "nt")
    monkeypatch.setattr(subprocess_runner.sys, "platform", "win32")
    monkeypatch.setattr(subprocess_runner, "_SUPPORTS_PGROUP", False)
    monkeypatch.setattr(subprocess_runner.subprocess, "Popen", lambda *_a, **_k: proc)
    monkeypatch.setattr(subprocess_runner, "_windows_creation_flags", lambda: 0)
    if job is not None:
        started = cast(Any, job)
        started.resume = lambda _proc: None
        monkeypatch.setattr(subprocess_runner, "_WindowsJob", lambda _proc: started)


def test_interrupt_abandons_a_stream_whose_reader_thread_is_alive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release = threading.Event()
    proc = _InterruptedPopen({"stdout": _live_reader(release), "stderr": _finished_reader()})
    job = _Job()
    _install(monkeypatch, proc, job)
    try:
        with pytest.raises(KeyboardInterrupt):
            _run_in_group(["tool"], 5, None, None)
    finally:
        release.set()

    assert proc.seen_at_exit is not None
    assert proc.seen_at_exit[0] is None, "a live reader's stdout was left for Popen.__exit__"
    assert proc.seen_at_exit[1] is not None, "a finished reader's stderr must stay closable"
    assert job.events == ["terminate", "close"]


def test_interrupt_keeps_streams_whose_readers_have_finished(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proc = _InterruptedPopen({"stdout": _finished_reader(), "stderr": _finished_reader()})
    job = _Job()
    _install(monkeypatch, proc, job)

    with pytest.raises(KeyboardInterrupt):
        _run_in_group(["tool"], 5, None, None)

    assert proc.seen_at_exit is not None
    assert proc.seen_at_exit[0] is not None
    assert proc.seen_at_exit[1] is not None
    assert job.events == ["terminate", "close"]


def test_interrupt_without_reader_state_is_a_no_op_for_the_streams(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proc = _InterruptedPopen(None)
    job = _Job()
    _install(monkeypatch, proc, job)

    with pytest.raises(KeyboardInterrupt):
        _run_in_group(["tool"], 5, None, None)

    assert proc.seen_at_exit is not None
    assert proc.seen_at_exit[0] is not None
    assert proc.seen_at_exit[1] is not None


def test_abandon_still_runs_when_terminating_the_job_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failing ``_terminate`` must not skip the stream release."""
    release = threading.Event()
    proc = _InterruptedPopen({"stdout": _live_reader(release), "stderr": _live_reader(release)})
    job = _Job(terminate_error=RuntimeError("job gone"))
    _install(monkeypatch, proc, job)
    monkeypatch.setattr(
        subprocess_runner,
        "_terminate",
        lambda _proc, _job=None: (_ for _ in ()).throw(RuntimeError("terminate failed")),
    )
    try:
        with pytest.raises(RuntimeError, match="terminate failed"):
            _run_in_group(["tool"], 5, None, None)
    finally:
        release.set()

    assert proc.seen_at_exit == (None, None)
    assert job.events == ["close"]
