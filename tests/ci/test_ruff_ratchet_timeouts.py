"""Timeout and partial-output tests for the ruff ratchet."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.ci import ruff_ratchet
from tests.ci.ruff_ratchet_test_helpers import (
    RunRecorder,
    completed,
    make_changed_file,
    names,
    timed_out,
)

# --- Subprocess deadlines -------------------------------------------------
#
# The shared runner reports a timeout as exit -1 with a "Command timed out
# after Ns" marker in stderr, and a missing executable as exit -1 with
# "Command not found: <name>". These tests feed those shapes through the fake
# and assert the gate fails closed with exit 3.


def test_git_diff_runs_under_an_explicit_deadline(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    recorder = RunRecorder([completed(0, "")])
    monkeypatch.setattr(ruff_ratchet, "_run_subprocess", recorder)

    ruff_ratchet.changed_python_files("origin/main", tmp_path)

    assert recorder.timeouts == [ruff_ratchet._GIT_TIMEOUT_SECONDS]


def test_ruff_runs_under_an_explicit_deadline_in_the_repo_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    recorder = RunRecorder([completed(0, "[]")])
    monkeypatch.setattr(ruff_ratchet, "_run_subprocess", recorder)

    ruff_ratchet.run_ruff(["scripts/a.py"], tmp_path, {})

    assert recorder.timeouts == [ruff_ratchet._RUFF_TIMEOUT_SECONDS]
    assert recorder.cwds == [tmp_path]


def test_deadlines_are_positive_and_bounded() -> None:
    # A zero or huge value would silently turn the deadline into a no-op.
    for seconds in (ruff_ratchet._GIT_TIMEOUT_SECONDS, ruff_ratchet._RUFF_TIMEOUT_SECONDS):
        assert 0 < seconds <= 600


def test_fallback_git_call_also_runs_under_the_deadline(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    make_changed_file(tmp_path)
    recorder = RunRecorder([completed(128, stderr="fatal: bad revision\n"), completed(0, "")])
    monkeypatch.setattr(ruff_ratchet, "_run_subprocess", recorder)

    ruff_ratchet.changed_python_files("stale-sha", tmp_path)

    assert recorder.timeouts == [ruff_ratchet._GIT_TIMEOUT_SECONDS] * 2


def test_git_timeout_is_an_external_error_without_a_fallback_retry(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # A timeout says nothing about the ref. Retrying against origin/main would
    # double the wait on a wedged git and could pass on the fallback's list.
    recorder = RunRecorder([timed_out(60)])
    monkeypatch.setattr(ruff_ratchet, "_run_subprocess", recorder)

    status, files, _base = ruff_ratchet.changed_python_files("feature-base", tmp_path)

    assert status == ruff_ratchet.EXIT_EXTERNAL
    assert files == []
    assert len(recorder.commands) == 1
    assert "Command timed out after 60s" in capsys.readouterr().err


def test_git_timeout_prints_partial_stdout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # The runner contract preserves what git flushed before the deadline. The
    # ratchet's documented diagnostic guarantee covers that output too.
    recorder = RunRecorder(
        [timed_out(60, stdout=names("scripts/partial.py"), stderr="progress: reading refs")]
    )
    monkeypatch.setattr(ruff_ratchet, "_run_subprocess", recorder)

    status, files, _base = ruff_ratchet.changed_python_files("feature-base", tmp_path)
    captured = capsys.readouterr()

    assert status == ruff_ratchet.EXIT_EXTERNAL
    assert files == []
    assert "git partial stdout" in captured.err
    assert "scripts/partial.py" in captured.err


def test_git_signal_death_prints_a_diagnostic_when_stderr_is_empty(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # A signal-killed git produces no ref resolution and no finding. The log
    # must say that much even when the child wrote only whitespace to stderr.
    recorder = RunRecorder([completed(-15, stderr="\n")])
    monkeypatch.setattr(ruff_ratchet, "_run_subprocess", recorder)

    status, files, _base = ruff_ratchet.changed_python_files("feature-base", tmp_path)
    captured = capsys.readouterr()

    assert status == ruff_ratchet.EXIT_EXTERNAL
    assert files == []
    assert "signal 15" in captured.err


def test_git_timeout_on_the_fallback_ref_is_an_external_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    recorder = RunRecorder([completed(128, stderr="fatal: bad revision\n"), timed_out(60)])
    monkeypatch.setattr(ruff_ratchet, "_run_subprocess", recorder)

    status, files, resolved = ruff_ratchet.changed_python_files("stale-sha", tmp_path)

    assert status == ruff_ratchet.EXIT_EXTERNAL
    assert files == []
    assert resolved == "origin/main"
    assert "Command timed out after 60s" in capsys.readouterr().err


@pytest.mark.parametrize(
    "result",
    [
        completed(-1, stderr="Command not found: git"),
        completed(-9, stderr=""),
    ],
    ids=["git-missing", "git-killed-by-signal"],
)
def test_git_runner_sentinel_or_signal_does_not_trigger_the_fallback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    result: subprocess.CompletedProcess[str],
) -> None:
    recorder = RunRecorder([result])
    monkeypatch.setattr(ruff_ratchet, "_run_subprocess", recorder)

    status, files, _base = ruff_ratchet.changed_python_files("feature-base", tmp_path)

    assert status == ruff_ratchet.EXIT_EXTERNAL
    assert files == []
    assert len(recorder.commands) == 1


def test_ruff_timeout_is_an_external_error_with_partial_output(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    recorder = RunRecorder(
        [timed_out(180, stdout='[{"code": "E501"', stderr="warning: slow cache\n")]
    )
    monkeypatch.setattr(ruff_ratchet, "_run_subprocess", recorder)

    exit_code = ruff_ratchet.run_ruff(["scripts/a.py"], tmp_path, {"scripts/a.py": {1}})
    captured = capsys.readouterr()

    assert exit_code == ruff_ratchet.EXIT_EXTERNAL
    assert "warning: slow cache" in captured.err
    assert "Command timed out after 180s" in captured.err
    assert '[{"code": "E501"' in captured.err
    assert "Ruff ratchet passed" not in captured.out


def test_ruff_timeout_without_partial_output_still_fails_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    recorder = RunRecorder([timed_out(180)])
    monkeypatch.setattr(ruff_ratchet, "_run_subprocess", recorder)

    exit_code = ruff_ratchet.run_ruff(["scripts/a.py"], tmp_path, {})
    captured = capsys.readouterr()

    assert exit_code == ruff_ratchet.EXIT_EXTERNAL
    assert "Command timed out after 180s" in captured.err
    assert "partial stdout" not in captured.err


def test_ruff_timeout_never_passes_even_when_partial_stdout_is_clean_json(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Partial stdout of "[]" parses as zero findings. A timeout must not be
    # read as that verdict.
    recorder = RunRecorder([timed_out(180, stdout="[]")])
    monkeypatch.setattr(ruff_ratchet, "_run_subprocess", recorder)

    exit_code = ruff_ratchet.run_ruff(["scripts/a.py"], tmp_path, {})

    assert exit_code == ruff_ratchet.EXIT_EXTERNAL


def test_ruff_partial_stdout_is_truncated(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    limit = ruff_ratchet._PARTIAL_OUTPUT_LIMIT
    recorder = RunRecorder([timed_out(180, stdout="x" * limit + "TAIL")])
    monkeypatch.setattr(ruff_ratchet, "_run_subprocess", recorder)

    exit_code = ruff_ratchet.run_ruff(["scripts/a.py"], tmp_path, {})
    captured = capsys.readouterr()

    assert exit_code == ruff_ratchet.EXIT_EXTERNAL
    assert "x" * limit in captured.err
    assert "TAIL" not in captured.err


def test_missing_ruff_is_an_external_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Before the shared runner, a missing ruff raised FileNotFoundError out of
    # main, and the interpreter's exit 1 read as EXIT_VIOLATIONS.
    recorder = RunRecorder([completed(-1, stderr="Command not found: ruff")])
    monkeypatch.setattr(ruff_ratchet, "_run_subprocess", recorder)

    exit_code = ruff_ratchet.run_ruff(["scripts/a.py"], tmp_path, {})

    assert exit_code == ruff_ratchet.EXIT_EXTERNAL
    assert "Command not found: ruff" in capsys.readouterr().err


def test_ruff_stderr_is_printed_with_a_single_trailing_newline(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    recorder = RunRecorder([completed(0, "[]", stderr="note: cache cold\n")])
    monkeypatch.setattr(ruff_ratchet, "_run_subprocess", recorder)

    ruff_ratchet.run_ruff(["scripts/a.py"], tmp_path, {})

    assert capsys.readouterr().err == "note: cache cold\n"


def test_ruff_exit_two_prints_partial_stdout_and_stays_external(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    recorder = RunRecorder([completed(2, stdout="usage text", stderr="ruff: bad flag\n")])
    monkeypatch.setattr(ruff_ratchet, "_run_subprocess", recorder)

    exit_code = ruff_ratchet.run_ruff(["scripts/a.py"], tmp_path, {})
    captured = capsys.readouterr()

    assert exit_code == ruff_ratchet.EXIT_EXTERNAL
    assert "usage text" in captured.err
    assert "ruff: bad flag" in captured.err
