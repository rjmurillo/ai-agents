"""`lefthook_runner.main` hands Lefthook the pushed file list (issue #6884).

Lefthook alone skips every pre-push job when HEAD is level with its push base.
The runner reads git's ref lines, adds the ``--file`` list, and passes git's two
hook arguments after ``--``. A fake ``lefthook_file_args`` and a mocked child
pin what reaches Lefthook; ``tests/test_push_file_list.py`` covers the list.

Coverage:

- positive: the file list and stdin reach Lefthook in the caller-chosen output mode.
- negative: a list that cannot be built refuses the push with exit 1; a caller
  that chose files keeps its own flags.
- edge: remotes named like Lefthook flags, a trailing ``--job`` with and without
  ref lines, and an empty stdin.
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

COMMAND = ["uv", "run", "--frozen", "lefthook"]
REF_LINE = f"refs/heads/x {'a' * 40} refs/heads/x {'0' * 40}\n"


def _pipe_stdin(monkeypatch: pytest.MonkeyPatch, text: str) -> None:
    stdin = mock.Mock(buffer=io.BytesIO(text.encode()))
    stdin.isatty.return_value = False
    monkeypatch.setattr(runner.sys, "stdin", stdin)


def _completed(returncode: int, stdout: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.CompletedProcess([], returncode, stdout=stdout.encode())


def test_main_refuses_the_push_when_the_file_list_cannot_be_built(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(report_module.OUTPUT_ENV, raising=False)
    _pipe_stdin(monkeypatch, "refs/heads/x abc refs/heads/x 000\n")
    with (
        mock.patch.object(runner, "resolve_command", return_value=COMMAND),
        mock.patch.object(runner.subprocess, "Popen") as popen,
        mock.patch.object(runner.subprocess, "run") as run,
    ):
        status = runner.main(["run", "pre-push", "origin", "url"])

    err = capsys.readouterr().err
    assert status == runner.EXIT_FILE_LIST == 1
    assert "pushed file list cannot be built" in err
    assert "invalid object id" in err
    popen.assert_not_called()
    run.assert_not_called()


def test_a_caller_chosen_output_mode_still_gets_the_file_list_and_the_stdin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _pipe_stdin(monkeypatch, REF_LINE)
    with (
        mock.patch.object(runner, "resolve_command", return_value=COMMAND),
        mock.patch.dict(os.environ, {report_module.OUTPUT_ENV: "failure"}),
        mock.patch.object(runner, "lefthook_file_args", return_value=["--file=x.py"]),
        mock.patch.object(runner.subprocess, "run", return_value=_completed(0, "")) as run,
    ):
        status = runner.main(["run", "pre-push", "origin", "url"])

    assert status == 0
    assert run.call_args.args[0] == [
        *COMMAND,
        "run",
        "pre-push",
        "--file=x.py",
        "--",
        "origin",
        "url",
    ]
    assert run.call_args.kwargs["input"] == REF_LINE.encode()


@pytest.mark.parametrize(
    "flag", ["--file=a.py", "--all-files", "--files-from-stdin", "--force", "--file"]
)
def test_a_caller_chosen_file_list_is_left_alone(
    monkeypatch: pytest.MonkeyPatch, flag: str
) -> None:
    _pipe_stdin(monkeypatch, REF_LINE)
    with (
        mock.patch.object(runner, "resolve_command", return_value=COMMAND),
        mock.patch.dict(os.environ, {report_module.OUTPUT_ENV: "failure"}),
        mock.patch.object(runner, "lefthook_file_args") as files,
        mock.patch.object(runner.subprocess, "run", return_value=_completed(0, "")) as run,
    ):
        runner.main(["run", "pre-push", flag, "origin", "url"])

    files.assert_not_called()
    assert run.call_args.args[0] == [*COMMAND, "run", "pre-push", flag, "--", "origin", "url"]


@pytest.mark.parametrize(
    ("rest", "flags", "git_arguments"),
    [
        (["origin", "url"], [], ["origin", "url"]),
        (
            ["--job", "push-ref-policy", "origin", "url"],
            ["--job", "push-ref-policy"],
            ["origin", "url"],
        ),
        (["--no-tty", "upstream", "url"], ["--no-tty"], ["upstream", "url"]),
        (["--file=README.md", "url"], [], ["--file=README.md", "url"]),
        (["--job", "x"], ["--job", "x"], []),
        (["--job"], ["--job"], []),
        ([], [], []),
    ],
)
def test_git_arguments_are_the_last_two(
    rest: list[str], flags: list[str], git_arguments: list[str]
) -> None:
    assert runner._split_hook_arguments(rest, from_git=False) == (flags, git_arguments)


@pytest.mark.parametrize("remote", ["--job", "--tag", "--command", "--exclude", "--file"])
def test_with_ref_lines_the_last_two_are_git_arguments_whatever_their_name(remote: str) -> None:
    assert runner._split_hook_arguments([remote, "url"], from_git=True) == ([], [remote, "url"])


@pytest.mark.parametrize(
    "remote",
    ["--force", "--file=README.md", "--all-files", "--job", "--tag", "--file", "--exclude"],
)
def test_a_remote_named_like_a_file_flag_keeps_the_file_list(
    monkeypatch: pytest.MonkeyPatch, remote: str
) -> None:
    """``git remote add -- --file=README.md`` is valid, so git's arguments go after ``--``."""
    _pipe_stdin(monkeypatch, REF_LINE)
    with (
        mock.patch.object(runner, "resolve_command", return_value=COMMAND),
        mock.patch.dict(os.environ, {report_module.OUTPUT_ENV: "failure"}),
        mock.patch.object(runner, "lefthook_file_args", return_value=["--file=x.py"]) as files,
        mock.patch.object(runner.subprocess, "run", return_value=_completed(0, "")) as run,
    ):
        runner.main(["run", "pre-push", remote, "url"])

    files.assert_called_once_with(REF_LINE.encode(), remote)
    assert run.call_args.args[0] == [
        *COMMAND,
        "run",
        "pre-push",
        "--file=x.py",
        "--",
        remote,
        "url",
    ]


def test_with_ref_lines_a_trailing_job_flag_is_taken_as_git_arguments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fail safe: the pair goes after ``--``, so Lefthook selects no job and runs them all."""
    _pipe_stdin(monkeypatch, REF_LINE)
    with (
        mock.patch.object(runner, "resolve_command", return_value=COMMAND),
        mock.patch.dict(os.environ, {report_module.OUTPUT_ENV: "failure"}),
        mock.patch.object(runner, "lefthook_file_args", return_value=["--file=x.py"]) as files,
        mock.patch.object(runner.subprocess, "run", return_value=_completed(0, "")) as run,
    ):
        runner.main(["run", "pre-push", "--job", "x"])

    files.assert_called_once_with(REF_LINE.encode(), "--job")
    assert run.call_args.args[0] == [
        *COMMAND,
        "run",
        "pre-push",
        "--file=x.py",
        "--",
        "--job",
        "x",
    ]


def test_without_ref_lines_a_trailing_job_flag_stays_a_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _pipe_stdin(monkeypatch, "")
    with (
        mock.patch.object(runner, "resolve_command", return_value=COMMAND),
        mock.patch.dict(os.environ, {report_module.OUTPUT_ENV: "failure"}),
        mock.patch.object(runner.subprocess, "run", return_value=_completed(0, "")) as run,
    ):
        runner.main(["run", "pre-push", "--job", "x"])

    assert run.call_args.args[0] == [*COMMAND, "run", "pre-push", "--job", "x"]


def test_pre_push_with_empty_stdin_adds_no_file_list(monkeypatch: pytest.MonkeyPatch) -> None:
    _pipe_stdin(monkeypatch, "")
    with (
        mock.patch.object(runner, "resolve_command", return_value=COMMAND),
        mock.patch.dict(os.environ, {report_module.OUTPUT_ENV: "failure"}),
        mock.patch.object(runner.subprocess, "run", return_value=_completed(0, "")) as run,
    ):
        runner.main(["run", "pre-push", "origin", "url"])

    assert run.call_args.args[0] == [*COMMAND, "run", "pre-push", "--", "origin", "url"]
