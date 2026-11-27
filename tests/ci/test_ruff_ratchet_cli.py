"""CLI exit-code tests for the ruff ratchet."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.ci import ruff_ratchet
from tests.ci.ruff_ratchet_test_helpers import (
    RunRecorder,
    completed,
    finding,
    make_changed_file,
    names,
    stub_line_map,
    timed_out,
)

# --- CLI contract: exit codes 0, 1, 2, 3 through main ----------------------


def test_main_git_timeout_exits_three(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / ".git").mkdir()
    recorder = RunRecorder([timed_out(60)])
    monkeypatch.setattr(ruff_ratchet, "_run_subprocess", recorder)

    exit_code = ruff_ratchet.main(["--base-ref", "feature-base", "--repo-root", str(tmp_path)])

    assert exit_code == ruff_ratchet.EXIT_EXTERNAL == 3
    assert len(recorder.commands) == 1
    assert "Command timed out after 60s" in capsys.readouterr().err


def test_main_ruff_timeout_exits_three(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / ".git").mkdir()
    make_changed_file(tmp_path)
    recorder = RunRecorder([completed(0, names("scripts/a.py")), timed_out(180, stdout="partial")])
    monkeypatch.setattr(ruff_ratchet, "_run_subprocess", recorder)
    stub_line_map(monkeypatch, {"scripts/a.py": {1}})

    exit_code = ruff_ratchet.main(["--base-ref", "origin/main", "--repo-root", str(tmp_path)])
    captured = capsys.readouterr()

    assert exit_code == ruff_ratchet.EXIT_EXTERNAL == 3
    assert "Command timed out after 180s" in captured.err
    assert "partial" in captured.err


def test_main_clean_run_exits_zero(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    make_changed_file(tmp_path)
    recorder = RunRecorder([completed(0, names("scripts/a.py")), completed(0, "[]")])
    monkeypatch.setattr(ruff_ratchet, "_run_subprocess", recorder)
    stub_line_map(monkeypatch, {"scripts/a.py": {1}})

    exit_code = ruff_ratchet.main(["--base-ref", "origin/main", "--repo-root", str(tmp_path)])

    assert exit_code == ruff_ratchet.EXIT_OK == 0
    assert recorder.timeouts == [
        ruff_ratchet._GIT_TIMEOUT_SECONDS,
        ruff_ratchet._RUFF_TIMEOUT_SECONDS,
    ]


def test_main_blocking_finding_exits_one(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    make_changed_file(tmp_path)
    payload = json.dumps([finding("scripts/a.py", 1)])
    recorder = RunRecorder([completed(0, names("scripts/a.py")), completed(1, payload)])
    monkeypatch.setattr(ruff_ratchet, "_run_subprocess", recorder)
    stub_line_map(monkeypatch, {"scripts/a.py": {1}})

    exit_code = ruff_ratchet.main(["--base-ref", "origin/main", "--repo-root", str(tmp_path)])

    assert exit_code == ruff_ratchet.EXIT_VIOLATIONS == 1


def test_main_config_error_exits_two_without_running_anything(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    recorder = RunRecorder([])
    monkeypatch.setattr(ruff_ratchet, "_run_subprocess", recorder)

    exit_code = ruff_ratchet.main(["--repo-root", str(tmp_path)])

    assert exit_code == ruff_ratchet.EXIT_CONFIG == 2
    assert recorder.commands == []
