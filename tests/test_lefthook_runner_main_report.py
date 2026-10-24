"""`lefthook_runner.main` closes a failed hook with the report (issue #6734, item 5).

A fake Lefthook child process stands in for the binary, so each test pins what the
runner does with its output and how it ends the child.

Coverage:

- positive: job output reaches stdout and the report reaches stderr.
- negative: a passing hook prints nothing extra; a caller-set LEFTHOOK_OUTPUT and a
  non-hook command keep Lefthook's own behavior.
- edge: pre-push stdin is replayed with the pushed file list (issue #6884; the
  rest of the list behavior is in test_lefthook_runner_pre_push_files.py), a
  start failure gets the runner diagnosis, and an interrupt ends the child
  without a hang.
"""

from __future__ import annotations

import importlib
import io
import os
import subprocess
from unittest import mock

import pytest

from scripts.validation import lefthook_runner as runner

# The runner imports its sibling by bare name; use the module object it holds.
report_module = importlib.import_module(runner.run_hook_with_report.__module__)

FIGHT = "\U0001f94a"
COMMAND = ["uv", "run", "--frozen", "lefthook"]


def _lefthook_failure(job: str, finding: str) -> str:
    return (
        f"{finding}\n\nexit status 1\n{FIGHT} group (6) (10.23 seconds)\n"
        f"  {FIGHT} {job} (0.03 seconds)\n"
    )


class _Sink(io.BytesIO):
    """A stdin pipe that keeps what was written after it is closed."""

    _written = b""

    def close(self) -> None:
        self._written = self.getvalue()
        super().close()


class _FakeProcess:
    def __init__(self, returncode: int, output: str) -> None:
        self._returncode = returncode
        self.stdout = io.BytesIO(output.encode())
        self.stdin = _Sink()

    def poll(self) -> int | None:
        return self._returncode

    def wait(self) -> int:
        return self._returncode


def _completed(returncode: int, stdout: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.CompletedProcess([], returncode, stdout=stdout.encode())


def test_main_prints_job_output_then_the_report(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(report_module.OUTPUT_ENV, raising=False)
    stdout = _lefthook_failure("python-format", "scripts/a.py:4:1 would reformat")
    with (
        mock.patch.object(runner, "resolve_command", return_value=COMMAND),
        mock.patch.object(
            runner.subprocess, "Popen", return_value=_FakeProcess(1, stdout)
        ) as popen,
    ):
        status = runner.main(["run", "pre-commit"])

    captured = capsys.readouterr()
    assert status == 1
    assert "env" not in popen.call_args.kwargs
    assert "scripts/a.py:4:1 would reformat" in captured.out
    assert FIGHT not in captured.out
    assert "pre-commit FAILED (exit 1)" in captured.err
    assert "run pre-commit --job python-format" in captured.err


def test_main_prints_nothing_extra_when_the_hook_passes(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(report_module.OUTPUT_ENV, raising=False)
    with (
        mock.patch.object(runner, "resolve_command", return_value=COMMAND),
        mock.patch.object(runner.subprocess, "Popen", return_value=_FakeProcess(0, "")),
    ):
        status = runner.main(["run", "pre-commit"])

    captured = capsys.readouterr()
    assert status == 0
    assert captured.out == ""
    assert captured.err == ""


LOCAL_SHA = "a" * 40
ZERO_SHA = "0" * 40
REF_LINE = f"refs/heads/x {LOCAL_SHA} refs/heads/x {ZERO_SHA}\n"


def _pipe_stdin(monkeypatch: pytest.MonkeyPatch, text: str) -> None:
    stdin = mock.Mock(buffer=io.BytesIO(text.encode()))
    stdin.isatty.return_value = False
    monkeypatch.setattr(runner.sys, "stdin", stdin)


def test_main_replays_stdin_to_a_pre_push_child_and_into_the_rerun(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(report_module.OUTPUT_ENV, raising=False)
    process = _FakeProcess(1, _lefthook_failure("a", "boom"))
    _pipe_stdin(monkeypatch, REF_LINE)
    with (
        mock.patch.object(runner, "resolve_command", return_value=COMMAND),
        mock.patch.object(runner, "lefthook_file_args", return_value=["--file=x.py"]) as files,
        mock.patch.object(runner.subprocess, "Popen", return_value=process) as popen,
        mock.patch.object(report_module.threading, "Thread") as thread,
    ):
        runner.main(["run", "pre-push", "origin", "https://u:tok@h/r.git"])

    err = capsys.readouterr().err
    files.assert_called_once_with(REF_LINE.encode(), "origin")
    assert thread.call_args.kwargs["args"][1] == REF_LINE.encode()
    assert popen.call_args.args[0] == [
        *COMMAND,
        "run",
        "pre-push",
        "--file=x.py",
        "--",
        "origin",
        "https://u:tok@h/r.git",
    ]
    assert f"printf '%s\\n' 'refs/heads/x {LOCAL_SHA} refs/heads/x {ZERO_SHA}' |" in err
    # The file list can be long, so the printed rerun leaves it out and goes
    # through the runner, which rebuilds it. Raw Lefthook would skip every job
    # when HEAD is level with its push base (issue #6884).
    assert "--file=x.py" not in err
    assert "| python3 scripts/validation/lefthook_runner.py run pre-push --job a origin" in err
    assert "uv run --frozen lefthook run pre-push" not in err


def test_a_pre_commit_rerun_still_names_lefthook(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(report_module.OUTPUT_ENV, raising=False)
    with (
        mock.patch.object(runner, "resolve_command", return_value=COMMAND),
        mock.patch.object(
            runner.subprocess, "Popen", return_value=_FakeProcess(1, _lefthook_failure("a", "x"))
        ),
    ):
        runner.main(["run", "pre-commit"])

    assert "rerun: uv run --frozen lefthook run pre-commit --job a" in capsys.readouterr().err


def test_main_leaves_a_caller_chosen_output_mode_alone() -> None:
    with (
        mock.patch.object(runner, "resolve_command", return_value=COMMAND),
        mock.patch.dict(os.environ, {report_module.OUTPUT_ENV: "summary,failure"}),
        mock.patch.object(runner.subprocess, "run", return_value=_completed(1, "")) as run,
        mock.patch.object(runner.subprocess, "Popen") as popen,
    ):
        status = runner.main(["run", "pre-commit"])

    assert status == 1
    run.assert_called_once()
    popen.assert_not_called()


def test_main_does_not_report_for_commands_that_are_not_a_hook_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(report_module.OUTPUT_ENV, raising=False)
    with (
        mock.patch.object(runner, "resolve_command", return_value=COMMAND),
        mock.patch.object(runner.subprocess, "run", return_value=_completed(0, "")) as run,
    ):
        runner.main(["version"])

    assert "env" not in run.call_args.kwargs


def test_main_reports_a_child_that_cannot_start_with_the_runner_diagnosis(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(report_module.OUTPUT_ENV, raising=False)
    with (
        mock.patch.object(runner, "resolve_command", return_value=["/x/lefthook"]),
        mock.patch.object(runner.subprocess, "Popen", side_effect=OSError("exec format")),
    ):
        status = runner.main(["run", "pre-commit"])

    err = capsys.readouterr().err
    assert status == runner.EXIT_UNAVAILABLE
    assert "cannot start /x/lefthook" in err


@pytest.mark.parametrize("stdin", [None, "tty"])
def test_pre_push_without_readable_stdin_runs_the_hook_and_replays_no_refs(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, stdin: str | None
) -> None:
    monkeypatch.delenv(report_module.OUTPUT_ENV, raising=False)
    fake_stdin = None
    if stdin == "tty":
        fake_stdin = mock.Mock()
        fake_stdin.isatty.return_value = True
    monkeypatch.setattr(runner.sys, "stdin", fake_stdin)
    process = _FakeProcess(1, _lefthook_failure("a", "boom"))
    with (
        mock.patch.object(runner, "resolve_command", return_value=COMMAND),
        mock.patch.object(runner.subprocess, "Popen", return_value=process) as popen,
    ):
        status = runner.main(["run", "pre-push", "origin", "url"])

    err = capsys.readouterr().err
    assert status == 1
    assert popen.call_args.kwargs["stdin"] is None
    assert "printf" not in err
    assert (
        "rerun: python3 scripts/validation/lefthook_runner.py run pre-push --job a origin url"
        in err
    )


class _Failing(io.BytesIO):
    """A child stdout whose next read raises ``error``."""

    def __init__(self, error: BaseException) -> None:
        super().__init__()
        self._error = error

    def __iter__(self) -> _Failing:
        return self

    def __next__(self) -> bytes:
        raise self._error


class _RunningProcess(_FakeProcess):
    """A child that is still running when its stdout fails."""

    def __init__(
        self,
        error: BaseException,
        *,
        ignores_sigterm: bool = False,
        second_interrupt: bool = False,
    ) -> None:
        super().__init__(1, "")
        self.stdout = _Failing(error)
        self._ignores_sigterm, self._second_interrupt = ignores_sigterm, second_interrupt
        self._terminated = self._killed = False

    def poll(self) -> int | None:
        return None

    def terminate(self) -> None:
        self._terminated = True

    def kill(self) -> None:
        self._killed = True

    def wait(self, timeout: float | None = None) -> int:
        if timeout is not None and self._second_interrupt and not self._killed:
            raise KeyboardInterrupt
        if timeout is not None and self._ignores_sigterm and not self._killed:
            raise subprocess.TimeoutExpired("lefthook", timeout)
        return 1


@pytest.mark.parametrize("ignores_sigterm", [False, True])
def test_an_interrupt_ends_the_child_without_hanging_and_still_propagates(
    monkeypatch: pytest.MonkeyPatch, ignores_sigterm: bool
) -> None:
    monkeypatch.delenv(report_module.OUTPUT_ENV, raising=False)
    process = _RunningProcess(KeyboardInterrupt(), ignores_sigterm=ignores_sigterm)
    with (
        mock.patch.object(runner, "resolve_command", return_value=COMMAND),
        mock.patch.object(runner.subprocess, "Popen", return_value=process),
        pytest.raises(KeyboardInterrupt),
    ):
        runner.main(["run", "pre-commit"])

    assert process._terminated is True
    assert process._killed is ignores_sigterm


def test_a_second_interrupt_during_the_grace_period_still_kills_the_child(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(report_module.OUTPUT_ENV, raising=False)
    process = _RunningProcess(KeyboardInterrupt(), second_interrupt=True)
    with (
        mock.patch.object(runner, "resolve_command", return_value=COMMAND),
        mock.patch.object(runner.subprocess, "Popen", return_value=process),
        pytest.raises(KeyboardInterrupt),
    ):
        runner.main(["run", "pre-commit"])

    assert process._terminated is True
    assert process._killed is True


def test_an_io_error_while_forwarding_output_is_not_reported_as_lefthook_unavailable(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(report_module.OUTPUT_ENV, raising=False)
    process = _RunningProcess(BrokenPipeError("stdout closed"))
    with (
        mock.patch.object(runner, "resolve_command", return_value=COMMAND),
        mock.patch.object(runner.subprocess, "Popen", return_value=process),
        pytest.raises(BrokenPipeError),
    ):
        runner.main(["run", "pre-commit"])

    assert "Lefthook itself is unavailable" not in capsys.readouterr().err


def test_the_console_replaces_characters_it_cannot_encode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(report_module.OUTPUT_ENV, raising=False)
    console = mock.Mock()
    monkeypatch.setattr(runner.sys, "stdout", console)
    with (
        mock.patch.object(runner, "resolve_command", return_value=COMMAND),
        mock.patch.object(runner.subprocess, "Popen", return_value=_FakeProcess(0, "")),
    ):
        runner.main(["run", "pre-commit"])

    console.reconfigure.assert_called_with(errors="replace")
