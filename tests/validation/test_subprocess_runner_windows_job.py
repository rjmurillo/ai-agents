"""Windows job-object tests for the shared subprocess wrapper."""

from __future__ import annotations

import subprocess
from types import SimpleNamespace

import pytest

from scripts.validation import subprocess_runner
from scripts.validation.subprocess_runner import _run_subprocess
from tests.validation.subprocess_runner_timeout_helpers import _fake_popen, _TimedOutPopen

# ---------------------------------------------------------------------------
# _run_subprocess: Windows children join a job before they can spawn a tree
# ---------------------------------------------------------------------------


class TestRunSubprocessWindowsJob:
    def _simulate_windows(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(subprocess_runner.os, "name", "nt")
        monkeypatch.setattr(subprocess_runner.sys, "platform", "win32")
        monkeypatch.setattr(subprocess_runner, "_SUPPORTS_PGROUP", False)

    def test_child_starts_suspended_and_joins_the_job_before_it_runs(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        events: list[object] = []

        class _InstantPopen:
            pid = 123
            returncode = 0

            def communicate(self, timeout: float | None = None) -> tuple[str, str]:
                events.append("communicate")
                return "out", "err"

            def kill(self) -> None:
                events.append("kill")

            def wait(self, timeout: float | None = None) -> int:
                return self.returncode

            def __enter__(self) -> _InstantPopen:
                return self

            def __exit__(self, *_exc: object) -> None:
                return None

        proc = _InstantPopen()

        def popen_factory(*_args: object, **kwargs: object) -> _InstantPopen:
            events.append(("spawn", kwargs.get("creationflags"), kwargs.get("start_new_session")))
            return proc

        class _Job:
            def __init__(self, process: object) -> None:
                events.append(("job", getattr(process, "pid", None)))

            def resume(self, _process: object) -> None:
                events.append("resume")

            def terminate(self) -> None:
                events.append("terminate")

            def close(self) -> None:
                events.append("close")

        self._simulate_windows(monkeypatch)
        monkeypatch.setattr(subprocess_runner, "_WindowsJob", _Job, raising=False)
        monkeypatch.setattr(subprocess, "Popen", popen_factory)

        exit_code, stdout, stderr = _run_subprocess(["/fake"], timeout=5)

        assert (exit_code, stdout, stderr) == (0, "out", "err")
        spawn = events[0]
        assert isinstance(spawn, tuple)
        assert spawn[1] & 0x4, "CREATE_SUSPENDED must be set before job assignment"
        assert spawn[1] & 0x200, "CREATE_NEW_PROCESS_GROUP must isolate console events"
        assert spawn[2] is False
        assert events[1:] == [("job", 123), "resume", "communicate", "close"]

    def test_job_setup_failure_kills_the_suspended_child_and_fails_closed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        events: list[str] = []

        class _SuspendedPopen:
            pid = 123
            returncode = -1

            def communicate(self, timeout: float | None = None) -> tuple[str, str]:
                events.append("communicate")
                return "", ""

            def kill(self) -> None:
                events.append("kill")

            def wait(self, timeout: float | None = None) -> int:
                events.append("wait")
                return self.returncode

            def __enter__(self) -> _SuspendedPopen:
                return self

            def __exit__(self, *_exc: object) -> None:
                return None

        def fail_job(_process: object) -> None:
            raise OSError(6, "denied")

        self._simulate_windows(monkeypatch)
        monkeypatch.setattr(subprocess_runner, "_WindowsJob", fail_job, raising=False)
        monkeypatch.setattr(subprocess, "Popen", lambda *_a, **_k: _SuspendedPopen())

        exit_code, stdout, stderr = _run_subprocess(["/fake"], timeout=5)

        assert (exit_code, stdout) == (-1, "")
        assert events == ["kill", "wait"]
        assert "Windows job setup failed" in stderr

    def test_timeout_terminates_the_job_tree_instead_of_only_the_direct_child(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        events: list[str] = []
        proc = _TimedOutPopen(None, None)
        monkeypatch.setattr(subprocess, "Popen", _fake_popen(proc))

        class _Job:
            def __init__(self, _process: object) -> None:
                pass

            def resume(self, _process: object) -> None:
                events.append("resume")

            def terminate(self) -> None:
                events.append("terminate")

            def close(self) -> None:
                events.append("close")

        self._simulate_windows(monkeypatch)
        monkeypatch.setattr(subprocess_runner, "_WindowsJob", _Job, raising=False)

        exit_code, _stdout, stderr = _run_subprocess(["/fake"], timeout=7)

        assert exit_code == -1
        assert events == ["resume", "terminate", "close"]
        assert proc.killed is False
        assert stderr == "Command timed out after 7s"

    def test_access_denied_assignment_resumes_the_child_without_a_job(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A validator inside a UI-limited job can still run without nesting."""
        events: list[str] = []

        class _Child:
            pid = 123
            returncode = 0

            def communicate(self, timeout: float | None = None) -> tuple[str, str]:
                events.append("communicate")
                return "out", ""

            def kill(self) -> None:
                events.append("kill")

            def wait(self, timeout: float | None = None) -> int:
                return self.returncode

            def __enter__(self) -> _Child:
                return self

            def __exit__(self, *_exc: object) -> None:
                return None

        def deny_assignment(_process: object) -> None:
            raise OSError(5, "AssignProcessToJobObject failed")

        self._simulate_windows(monkeypatch)
        monkeypatch.setattr(subprocess_runner, "_WindowsJob", deny_assignment, raising=False)
        monkeypatch.setattr(
            subprocess_runner,
            "_resume_windows_process",
            lambda _process: events.append("resume-process"),
        )
        monkeypatch.setattr(subprocess, "Popen", lambda *_a, **_k: _Child())

        exit_code, stdout, stderr = _run_subprocess(["/fake"], timeout=5)

        assert (exit_code, stdout, stderr) == (0, "out", "")
        assert events == ["resume-process", "communicate"]

    def test_interrupt_during_resume_terminates_the_owned_job(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The caller owns the job before the child can start running."""
        events: list[str] = []
        proc = _TimedOutPopen(None, None)

        class _Job:
            def __init__(self, _process: object) -> None:
                events.append("job")

            def resume(self, _process: object) -> None:
                events.append("resume")
                raise KeyboardInterrupt

            def terminate(self) -> None:
                events.append("terminate")

            def close(self) -> None:
                events.append("close")

        self._simulate_windows(monkeypatch)
        monkeypatch.setattr(subprocess_runner, "_WindowsJob", _Job, raising=False)
        monkeypatch.setattr(subprocess, "Popen", _fake_popen(proc))

        with pytest.raises(KeyboardInterrupt):
            _run_subprocess(["/fake"], timeout=5)

        assert events == ["job", "resume", "terminate", "close"]

    def test_failed_job_termination_kills_the_direct_child(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        events: list[str] = []
        proc = _TimedOutPopen(None, None, drained=None)

        class _Job:
            def __init__(self, _process: object) -> None:
                pass

            def resume(self, _process: object) -> None:
                pass

            def terminate(self) -> None:
                events.append("terminate")
                raise OSError(5, "denied")

            def close(self) -> None:
                events.append("close")

        self._simulate_windows(monkeypatch)
        monkeypatch.setattr(subprocess_runner, "_WindowsJob", _Job, raising=False)
        monkeypatch.setattr(subprocess, "Popen", _fake_popen(proc))

        exit_code, _stdout, stderr = _run_subprocess(["/fake"], timeout=7)

        assert exit_code == -1
        assert proc.killed is True
        assert events == ["terminate", "close"]
        assert stderr == "Command timed out after 7s"

    def test_windows_job_assigns_the_suspended_process_before_resume(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        events: list[str] = []

        def create_job(_security: object, _name: object) -> int:
            events.append("create")
            return 111

        create_job.restype = None  # type: ignore[attr-defined]

        def assign_job(_job: object, _process: object) -> int:
            events.append("assign")
            return 1

        def terminate_job(_job: object, _exit_code: object) -> int:
            events.append("terminate-job")
            return 1

        def close_handle(_handle: object) -> int:
            events.append("close-handle")
            return 1

        def resume_process(_process: object) -> int:
            events.append("resume")
            return 0

        resume_process.restype = None  # type: ignore[attr-defined]

        kernel32 = SimpleNamespace(
            CreateJobObjectW=create_job,
            AssignProcessToJobObject=assign_job,
            TerminateJobObject=terminate_job,
            CloseHandle=close_handle,
        )
        ntdll = SimpleNamespace(NtResumeProcess=resume_process)

        def load_library(name: str, use_last_error: bool = False) -> object:
            assert use_last_error is True
            return {"kernel32": kernel32, "ntdll": ntdll}[name]

        monkeypatch.setattr(subprocess_runner.ctypes, "WinDLL", load_library, raising=False)

        job = subprocess_runner._WindowsJob(SimpleNamespace(_handle=456))
        assert events == ["create", "assign"]
        job.resume(SimpleNamespace(_handle=456))
        job.terminate()
        job.close()

        assert events == ["create", "assign", "resume", "terminate-job", "close-handle"]
