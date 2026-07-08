from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.ci import ruff_ratchet


class RunRecorder:
    def __init__(self, results: list[subprocess.CompletedProcess[str]]) -> None:
        self.results = results
        self.commands: list[list[str]] = []

    def __call__(
        self,
        command: list[str],
        *,
        check: bool,
        capture_output: bool,
        text: bool,
        cwd: Path | None = None,
        encoding: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        assert check is False
        assert capture_output is True
        assert text is True
        assert encoding == "utf-8"
        self.commands.append(command)
        return self.results.pop(0)


def completed(
    returncode: int, stdout: str = "", stderr: str = ""
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def test_default_base_ref_uses_origin_main_for_zero_before(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RUFF_RATCHET_BASE_REF", "0" * 40)

    assert ruff_ratchet.default_base_ref() == "origin/main"


def test_passes_without_changed_python_files(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    recorder = RunRecorder([completed(0, "README.md
scripts/example.txt
")])
    monkeypatch.setattr(ruff_ratchet.subprocess, "run", recorder)

    status, files = ruff_ratchet.changed_python_files("origin/main", tmp_path)
    exit_code = ruff_ratchet.run_ruff(files, tmp_path)

    assert status == ruff_ratchet.EXIT_OK
    assert exit_code == ruff_ratchet.EXIT_OK
    assert files == []
    assert len(recorder.commands) == 1
    assert "--diff-filter=ACMR" in recorder.commands[0]


def test_changed_python_files_includes_renamed_python_files(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    changed_file = tmp_path / "scripts" / "renamed.py"
    changed_file.parent.mkdir()
    changed_file.write_text("print('ok')
", encoding="utf-8")
    recorder = RunRecorder([completed(0, "scripts/renamed.py
")])
    monkeypatch.setattr(ruff_ratchet.subprocess, "run", recorder)

    status, files = ruff_ratchet.changed_python_files("origin/main", tmp_path)

    assert status == ruff_ratchet.EXIT_OK
    assert files == ["scripts/renamed.py"]


def test_changed_python_files_falls_back_when_base_ref_is_stale(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    changed_file = tmp_path / "scripts" / "fallback.py"
    changed_file.parent.mkdir()
    changed_file.write_text("print('ok')
", encoding="utf-8")
    recorder = RunRecorder(
        [
            completed(128, stderr="fatal: bad revision
"),
            completed(0, "scripts/fallback.py
"),
        ]
    )
    monkeypatch.setattr(ruff_ratchet.subprocess, "run", recorder)

    status, files = ruff_ratchet.changed_python_files("stale-before-sha", tmp_path)

    assert status == ruff_ratchet.EXIT_OK
    assert files == ["scripts/fallback.py"]
    assert recorder.commands[1][-1] == "origin/main...HEAD"


def test_passes_when_changed_python_files_are_clean(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    changed_file = tmp_path / "scripts" / "clean.py"
    changed_file.parent.mkdir()
    changed_file.write_text("print('ok')
", encoding="utf-8")
    recorder = RunRecorder([completed(0, "scripts/clean.py
"), completed(0)])
    monkeypatch.setattr(ruff_ratchet.subprocess, "run", recorder)

    status, files = ruff_ratchet.changed_python_files("origin/main", tmp_path)
    exit_code = ruff_ratchet.run_ruff(files, tmp_path)

    assert status == ruff_ratchet.EXIT_OK
    assert files == ["scripts/clean.py"]
    assert exit_code == ruff_ratchet.EXIT_OK
    assert recorder.commands[1] == [
        "ruff",
        "check",
        "--output-format=github",
        "--",
        "scripts/clean.py",
    ]


def test_run_ruff_separates_options_from_dash_prefixed_paths(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    recorder = RunRecorder([completed(0)])
    monkeypatch.setattr(ruff_ratchet.subprocess, "run", recorder)

    exit_code = ruff_ratchet.run_ruff(["--config.py"], tmp_path)

    assert exit_code == ruff_ratchet.EXIT_OK
    assert recorder.commands[0] == [
        "ruff",
        "check",
        "--output-format=github",
        "--",
        "--config.py",
    ]


def test_fails_when_changed_python_files_have_ruff_violations(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    changed_file = tmp_path / "scripts" / "dirty.py"
    changed_file.parent.mkdir()
    changed_file.write_text("import os
", encoding="utf-8")
    recorder = RunRecorder(
        [
            completed(0, "scripts/dirty.py
"),
            completed(1, "::error file=scripts/dirty.py,line=1::F401 unused import
"),
        ]
    )
    monkeypatch.setattr(ruff_ratchet.subprocess, "run", recorder)

    status, files = ruff_ratchet.changed_python_files("origin/main", tmp_path)
    exit_code = ruff_ratchet.run_ruff(files, tmp_path)

    assert status == ruff_ratchet.EXIT_OK
    assert files == ["scripts/dirty.py"]
    assert exit_code == ruff_ratchet.EXIT_VIOLATIONS


def test_git_diff_failure_is_external_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    recorder = RunRecorder(
        [
            completed(128, stderr="fatal: bad revision
"),
            completed(128, stderr="fatal: bad fallback revision
"),
        ]
    )
    monkeypatch.setattr(ruff_ratchet.subprocess, "run", recorder)

    status, files = ruff_ratchet.changed_python_files("missing-ref", tmp_path)

    assert status == ruff_ratchet.EXIT_EXTERNAL
    assert files == []
    assert len(recorder.commands) == 2
