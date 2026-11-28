"""Executable resolution and startup diagnostics for the ruff ratchet."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.ci import ruff_ratchet
from scripts.cli_exec import resolve_executable
from tests.ci.ruff_ratchet_test_helpers import RunRecorder, completed


def test_windows_git_exe_resolution_bypasses_a_cmd_shim(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The explicit native name resolves exactly even when PATHEXT prefers .cmd."""
    monkeypatch.setattr(ruff_ratchet.os, "name", "nt")
    (tmp_path / "git.cmd").write_text("@echo off\n", encoding="utf-8")
    (tmp_path / "git.exe").write_text("native\n", encoding="utf-8")
    env = {"PATH": str(tmp_path), "PATHEXT": ".CMD;.EXE"}

    resolved = resolve_executable(ruff_ratchet._native_program("git"), windows=True, env=env)

    assert resolved.lower().endswith("git.exe")


def test_run_ruff_uses_a_standalone_native_binary_when_the_module_is_absent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    recorder = RunRecorder([completed(0, "[]")])
    monkeypatch.setattr(ruff_ratchet, "_run_subprocess", recorder)
    monkeypatch.setattr(ruff_ratchet, "_module_available_outside_checkout", lambda _n, _r: False)

    exit_code = ruff_ratchet.run_ruff(["scripts/a.py"], tmp_path, {})

    assert exit_code == ruff_ratchet.EXIT_OK
    assert recorder.commands[0][:2] == ["ruff", "check"]


def test_windows_commands_name_native_executables_not_batch_shims(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    recorder = RunRecorder([completed(0, ""), completed(0, "[]")])
    monkeypatch.setattr(ruff_ratchet, "_run_subprocess", recorder)
    monkeypatch.setattr(ruff_ratchet.os, "name", "nt")
    monkeypatch.setattr(ruff_ratchet, "_module_available_outside_checkout", lambda _n, _r: False)

    status, files, _base = ruff_ratchet.changed_python_files("origin/main", tmp_path)
    assert status == ruff_ratchet.EXIT_OK
    if files:
        ruff_ratchet.run_ruff(files, tmp_path, {})

    assert recorder.commands[0][0] == "git.exe"


def test_run_ruff_windows_standalone_names_the_native_executable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    recorder = RunRecorder([completed(0, "[]")])
    monkeypatch.setattr(ruff_ratchet, "_run_subprocess", recorder)
    monkeypatch.setattr(ruff_ratchet.os, "name", "nt")
    monkeypatch.setattr(ruff_ratchet, "_module_available_outside_checkout", lambda _n, _r: False)

    ruff_ratchet.run_ruff(["scripts/a.py"], tmp_path, {})

    assert recorder.commands[0][0] == "ruff.exe"


def test_ruff_signal_death_prints_a_diagnostic_when_stderr_is_empty(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    recorder = RunRecorder([completed(-15, stderr="")])
    monkeypatch.setattr(ruff_ratchet, "_run_subprocess", recorder)

    exit_code = ruff_ratchet.run_ruff(["scripts/a.py"], tmp_path, {})
    captured = capsys.readouterr()

    assert exit_code == ruff_ratchet.EXIT_EXTERNAL
    assert "ruff terminated by signal 15" in captured.err


def test_windows_job_setup_failure_is_not_reported_as_signal_one(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    recorder = RunRecorder([completed(-1, stderr="Windows job setup failed: denied")])
    monkeypatch.setattr(ruff_ratchet, "_run_subprocess", recorder)

    exit_code = ruff_ratchet.run_ruff(["scripts/a.py"], tmp_path, {})
    captured = capsys.readouterr()

    assert exit_code == ruff_ratchet.EXIT_EXTERNAL
    assert "Windows job setup failed" in captured.err
    assert "signal 1" not in captured.err
