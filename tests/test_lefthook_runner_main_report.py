"""`lefthook_runner.main` closes a failed hook with the report (issue #6734, item 5).

A fake Lefthook child process stands in for the binary, so each test pins what the
runner does with its output: forward the job text, drop the job lines, add the
report to stderr, replay pre-push stdin, and clean up on an interrupt.

Coverage:

- positive: job output reaches stdout and the report reaches stderr.
- negative: a passing hook prints nothing extra; a caller-set LEFTHOOK_OUTPUT and a
  non-hook command keep Lefthook's own behavior.
- edge: pre-push stdin is replayed, a missing or interactive stdin is not, a child
  that cannot start gets the runner diagnosis, and an interrupt ends the child.
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
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout.encode())


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


def test_main_replays_stdin_to_a_pre_push_child_and_into_the_rerun(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(report_module.OUTPUT_ENV, raising=False)
    ref_line = "refs/heads/x abc refs/heads/x 000\n"
    process = _FakeProcess(1, _lefthook_failure("a", "boom"))
    stdin = mock.Mock(buffer=io.BytesIO(ref_line.encode()))
    stdin.isatty.return_value = False
    monkeypatch.setattr(runner.sys, "stdin", stdin)
    with (
        mock.patch.object(runner, "resolve_command", return_value=COMMAND),
        mock.patch.object(runner.subprocess, "Popen", return_value=process),
        mock.patch.object(report_module.threading, "Thread") as thread,
    ):
        runner.main(["run", "pre-push", "origin", "https://u:tok@h/r.git"])

    err = capsys.readouterr().err
    assert thread.call_args.kwargs["args"][1] == ref_line.encode()
    assert "printf '%s\\n' 'refs/heads/x abc refs/heads/x 000' |" in err


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
    assert "rerun: uv run --frozen lefthook run pre-push --job a origin url" in err


def test_an_interrupt_terminates_the_child_and_still_propagates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(report_module.OUTPUT_ENV, raising=False)

    class _Interrupted(_FakeProcess):
        terminated = False

        def __init__(self) -> None:
            super().__init__(1, "")
            self.stdout = self._raise_on_read()

        @staticmethod
        def _raise_on_read() -> io.BytesIO:
            class _Boom(io.BytesIO):
                def __iter__(self) -> _Boom:
                    return self

                def __next__(self) -> bytes:
                    raise KeyboardInterrupt

            return _Boom()

        def poll(self) -> int | None:
            return None

        def terminate(self) -> None:
            self.terminated = True

    process = _Interrupted()
    with (
        mock.patch.object(runner, "resolve_command", return_value=COMMAND),
        mock.patch.object(runner.subprocess, "Popen", return_value=process),
        pytest.raises(KeyboardInterrupt),
    ):
        runner.main(["run", "pre-commit"])

    assert process.terminated is True
