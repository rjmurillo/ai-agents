"""Changed-file discovery tests for the ruff ratchet."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from scripts.ci import ruff_ratchet
from tests.ci.ruff_ratchet_test_helpers import RunRecorder, completed, names


def test_default_base_ref_uses_origin_main_for_zero_before(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RUFF_RATCHET_BASE_REF", "0" * 40)

    assert ruff_ratchet.default_base_ref() == "origin/main"


def test_passes_without_changed_python_files(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    recorder = RunRecorder([completed(0, names("README.md", "scripts/example.txt"))])
    monkeypatch.setattr(ruff_ratchet, "_run_subprocess", recorder)

    status, files, _base = ruff_ratchet.changed_python_files("origin/main", tmp_path)
    exit_code = ruff_ratchet.run_ruff(files, tmp_path, {})

    assert status == ruff_ratchet.EXIT_OK
    assert exit_code == ruff_ratchet.EXIT_OK
    assert files == []
    assert len(recorder.commands) == 1
    assert "--diff-filter=ACMR" in recorder.commands[0]


def test_changed_python_files_requests_nul_separated_names(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Without ``-z`` git C-quotes any path holding a quote or a backslash, and
    # the quoted form never matches the path ruff reports.
    recorder = RunRecorder([completed(0, "")])
    monkeypatch.setattr(ruff_ratchet, "_run_subprocess", recorder)

    ruff_ratchet.changed_python_files("origin/main", tmp_path)

    assert "-z" in recorder.commands[0]


def test_changed_python_files_keeps_quotable_path_raw(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    odd = tmp_path / "scripts" / "od'd.py"
    odd.parent.mkdir()
    odd.write_text("print('ok')\n", encoding="utf-8")
    recorder = RunRecorder([completed(0, names("scripts/od'd.py"))])
    monkeypatch.setattr(ruff_ratchet, "_run_subprocess", recorder)

    status, files, _base = ruff_ratchet.changed_python_files("origin/main", tmp_path)

    assert status == ruff_ratchet.EXIT_OK
    assert files == ["scripts/od'd.py"]


def test_changed_python_files_includes_renamed_python_files(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    changed_file = tmp_path / "scripts" / "renamed.py"
    changed_file.parent.mkdir()
    changed_file.write_text("print('ok')\n", encoding="utf-8")
    recorder = RunRecorder([completed(0, names("scripts/renamed.py"))])
    monkeypatch.setattr(ruff_ratchet, "_run_subprocess", recorder)

    status, files, _base = ruff_ratchet.changed_python_files("origin/main", tmp_path)

    assert status == ruff_ratchet.EXIT_OK
    assert files == ["scripts/renamed.py"]


def test_changed_python_files_falls_back_when_base_ref_is_stale(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    changed_file = tmp_path / "scripts" / "fallback.py"
    changed_file.parent.mkdir()
    changed_file.write_text("print('ok')\n", encoding="utf-8")
    recorder = RunRecorder(
        [
            completed(128, stderr="fatal: bad revision\n"),
            completed(0, names("scripts/fallback.py")),
        ]
    )
    monkeypatch.setattr(ruff_ratchet, "_run_subprocess", recorder)

    status, files, _base = ruff_ratchet.changed_python_files("stale-before-sha", tmp_path)

    assert status == ruff_ratchet.EXIT_OK
    assert files == ["scripts/fallback.py"]
    assert recorder.commands[1][-1] == "origin/main...HEAD"


def test_passes_when_changed_python_files_are_clean(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    changed_file = tmp_path / "scripts" / "clean.py"
    changed_file.parent.mkdir()
    changed_file.write_text("print('ok')\n", encoding="utf-8")
    recorder = RunRecorder([completed(0, names("scripts/clean.py")), completed(0, "[]")])
    monkeypatch.setattr(ruff_ratchet, "_run_subprocess", recorder)

    status, files, _base = ruff_ratchet.changed_python_files("origin/main", tmp_path)
    exit_code = ruff_ratchet.run_ruff(files, tmp_path, {"scripts/clean.py": {1}})

    assert status == ruff_ratchet.EXIT_OK
    assert files == ["scripts/clean.py"]
    assert exit_code == ruff_ratchet.EXIT_OK
    assert recorder.commands[1] == [
        sys.executable,
        "-E",
        "-P",
        "-m",
        "ruff",
        "check",
        "--output-format=json",
        "--",
        "scripts/clean.py",
    ]


def test_run_ruff_separates_options_from_dash_prefixed_paths(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    recorder = RunRecorder([completed(0, "[]")])
    monkeypatch.setattr(ruff_ratchet, "_run_subprocess", recorder)

    exit_code = ruff_ratchet.run_ruff(["--config.py"], tmp_path, {})

    assert exit_code == ruff_ratchet.EXIT_OK
    assert recorder.commands[0] == [
        sys.executable,
        "-E",
        "-P",
        "-m",
        "ruff",
        "check",
        "--output-format=json",
        "--",
        "--config.py",
    ]
