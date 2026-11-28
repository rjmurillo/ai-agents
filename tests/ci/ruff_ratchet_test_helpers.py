"""Shared helpers for the ruff ratchet tests."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.ci import ruff_ratchet


class RunRecorder:
    """Fake for the shared runner ``_run_subprocess``; records each call."""

    def __init__(self, results: list[subprocess.CompletedProcess[str]]) -> None:
        self.results = results
        self.commands: list[list[str]] = []
        self.timeouts: list[int] = []
        self.cwds: list[Path | str | None] = []

    def __call__(
        self,
        args: list[str],
        timeout: int = 300,
        cwd: Path | str | None = None,
        env: dict[str, str] | None = None,
    ) -> tuple[int, str, str]:
        self.commands.append(args)
        self.timeouts.append(timeout)
        self.cwds.append(cwd)
        result = self.results.pop(0)
        return result.returncode, result.stdout, result.stderr


def completed(
    returncode: int, stdout: str = "", stderr: str = ""
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def names(*paths: str) -> str:
    """Render a ``git diff --name-only -z`` payload."""
    return "".join(f"{path}\0" for path in paths)


def finding(
    path: str,
    row: int,
    end_row: int | None = None,
    code: str = "E501",
    message: str = "Line too long",
) -> dict[str, object]:
    return {
        "code": code,
        "message": message,
        "filename": path,
        "location": {"row": row, "column": 1},
        "end_location": {"row": end_row if end_row is not None else row, "column": 2},
    }


def timed_out(seconds: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
    """Render the runner's timeout result, partial stderr first, marker last."""
    marker = f"Command timed out after {seconds}s"
    return completed(-1, stdout, f"{stderr}\n{marker}" if stderr else marker)


def make_changed_file(tmp_path: Path, name: str = "scripts/a.py") -> None:
    target = tmp_path / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("print('ok')\n", encoding="utf-8")


def stub_line_map(monkeypatch: pytest.MonkeyPatch, lines: dict[str, set[int]]) -> None:
    monkeypatch.setattr(ruff_ratchet, "changed_line_map", lambda *_args: lines)


class _HungPopen:
    """``Popen`` stand-in whose first ``communicate`` times out, then drains."""

    pid = 1
    returncode = None
    _handle = 1

    def __init__(self, partial_stdout: bytes, partial_stderr: bytes) -> None:
        self._partial = (partial_stdout, partial_stderr)
        self.timeouts: list[float | None] = []
        self.killed = False

    def __enter__(self) -> _HungPopen:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def communicate(self, timeout: float | None = None) -> tuple[bytes, bytes]:
        self.timeouts.append(timeout)
        if len(self.timeouts) == 1:
            raise subprocess.TimeoutExpired("ruff", timeout or 0, *self._partial)
        return self._partial

    def kill(self) -> None:
        self.killed = True

    def wait(self, timeout: float | None = None) -> int:
        return self.returncode if self.returncode is not None else 0


def _install_noop_windows_job(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep runner-contract fakes out of real Windows job assignment.

    These tests replace ``Popen`` with an object that has no real process
    handle. They exercise timeout and output plumbing, not job assignment, so
    the Windows branch needs the same seam the POSIX tests already get from
    the absent job-object path.
    """
    from scripts.validation import subprocess_runner

    class _NoopJob:
        def __init__(self, _process: object) -> None:
            pass

        def resume(self, _process: object) -> None:
            pass

        def terminate(self) -> None:
            pass

        def close(self) -> None:
            pass

    monkeypatch.setattr(subprocess_runner, "_WindowsJob", _NoopJob)


def _install_hung_popen(
    monkeypatch: pytest.MonkeyPatch, partial_stdout: bytes, partial_stderr: bytes
) -> _HungPopen:
    from scripts.validation import subprocess_runner

    child = _HungPopen(partial_stdout, partial_stderr)
    _install_noop_windows_job(monkeypatch)
    monkeypatch.setattr(subprocess_runner.subprocess, "Popen", lambda *_a, **_k: child)
    # The stand-in has no real pid; never signal a process group for it.
    monkeypatch.setattr(subprocess_runner, "_terminate", lambda _proc, _job=None: None)
    return child
