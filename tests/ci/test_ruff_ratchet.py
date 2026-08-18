from __future__ import annotations

import json
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
        errors: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        assert check is False
        assert capture_output is True
        assert text is True
        assert encoding == "utf-8"
        assert errors == "replace"
        self.commands.append(command)
        return self.results.pop(0)


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


def test_default_base_ref_uses_origin_main_for_zero_before(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RUFF_RATCHET_BASE_REF", "0" * 40)

    assert ruff_ratchet.default_base_ref() == "origin/main"


def test_passes_without_changed_python_files(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    recorder = RunRecorder([completed(0, names("README.md", "scripts/example.txt"))])
    monkeypatch.setattr(ruff_ratchet.subprocess, "run", recorder)

    status, files = ruff_ratchet.changed_python_files("origin/main", tmp_path)
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
    monkeypatch.setattr(ruff_ratchet.subprocess, "run", recorder)

    ruff_ratchet.changed_python_files("origin/main", tmp_path)

    assert "-z" in recorder.commands[0]


def test_changed_python_files_keeps_quotable_path_raw(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    odd = tmp_path / "scripts" / "od'd.py"
    odd.parent.mkdir()
    odd.write_text("print('ok')\n", encoding="utf-8")
    recorder = RunRecorder([completed(0, names("scripts/od'd.py"))])
    monkeypatch.setattr(ruff_ratchet.subprocess, "run", recorder)

    status, files = ruff_ratchet.changed_python_files("origin/main", tmp_path)

    assert status == ruff_ratchet.EXIT_OK
    assert files == ["scripts/od'd.py"]


def test_changed_python_files_includes_renamed_python_files(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    changed_file = tmp_path / "scripts" / "renamed.py"
    changed_file.parent.mkdir()
    changed_file.write_text("print('ok')\n", encoding="utf-8")
    recorder = RunRecorder([completed(0, names("scripts/renamed.py"))])
    monkeypatch.setattr(ruff_ratchet.subprocess, "run", recorder)

    status, files = ruff_ratchet.changed_python_files("origin/main", tmp_path)

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
    changed_file.write_text("print('ok')\n", encoding="utf-8")
    recorder = RunRecorder([completed(0, names("scripts/clean.py")), completed(0, "[]")])
    monkeypatch.setattr(ruff_ratchet.subprocess, "run", recorder)

    status, files = ruff_ratchet.changed_python_files("origin/main", tmp_path)
    exit_code = ruff_ratchet.run_ruff(files, tmp_path, {"scripts/clean.py": {1}})

    assert status == ruff_ratchet.EXIT_OK
    assert files == ["scripts/clean.py"]
    assert exit_code == ruff_ratchet.EXIT_OK
    assert recorder.commands[1] == [
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
    monkeypatch.setattr(ruff_ratchet.subprocess, "run", recorder)

    exit_code = ruff_ratchet.run_ruff(["--config.py"], tmp_path, {})

    assert exit_code == ruff_ratchet.EXIT_OK
    assert recorder.commands[0] == [
        "ruff",
        "check",
        "--output-format=json",
        "--",
        "--config.py",
    ]


def test_blocks_finding_on_an_added_line(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    payload = json.dumps([finding("scripts/dirty.py", 12)])
    recorder = RunRecorder([completed(1, payload)])
    monkeypatch.setattr(ruff_ratchet.subprocess, "run", recorder)

    exit_code = ruff_ratchet.run_ruff(["scripts/dirty.py"], tmp_path, {"scripts/dirty.py": {12}})

    assert exit_code == ruff_ratchet.EXIT_VIOLATIONS


def test_pre_existing_finding_outside_the_change_does_not_block(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # The defect this gate was rewritten for: editing line 12 of a file that
    # already carried an E501 on line 300 used to block the push (issue #2993).
    payload = json.dumps([finding("scripts/shared.py", 300)])
    recorder = RunRecorder([completed(1, payload)])
    monkeypatch.setattr(ruff_ratchet.subprocess, "run", recorder)

    exit_code = ruff_ratchet.run_ruff(["scripts/shared.py"], tmp_path, {"scripts/shared.py": {12}})
    captured = capsys.readouterr()

    assert exit_code == ruff_ratchet.EXIT_OK
    assert "not blocking" in captured.out
    assert "scripts/shared.py:300:1: E501" in captured.out
    assert "::error" not in captured.out


def test_blocks_multiline_finding_whose_range_reaches_a_changed_line(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    payload = json.dumps([finding("scripts/multi.py", 10, end_row=14, code="B905")])
    recorder = RunRecorder([completed(1, payload)])
    monkeypatch.setattr(ruff_ratchet.subprocess, "run", recorder)

    exit_code = ruff_ratchet.run_ruff(["scripts/multi.py"], tmp_path, {"scripts/multi.py": {13}})

    assert exit_code == ruff_ratchet.EXIT_VIOLATIONS


def test_renamed_file_with_unchanged_content_does_not_block(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # A pure rename produces no hunk, so the path is absent from the map even
    # though it is in the changed-file list.
    payload = json.dumps([finding("scripts/new_name.py", 4)])
    recorder = RunRecorder([completed(1, payload)])
    monkeypatch.setattr(ruff_ratchet.subprocess, "run", recorder)

    exit_code = ruff_ratchet.run_ruff(["scripts/new_name.py"], tmp_path, {})

    assert exit_code == ruff_ratchet.EXIT_OK


def test_unresolved_diff_base_blocks_every_finding(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    payload = json.dumps([finding("scripts/shared.py", 300)])
    recorder = RunRecorder([completed(1, payload)])
    monkeypatch.setattr(ruff_ratchet.subprocess, "run", recorder)

    exit_code = ruff_ratchet.run_ruff(["scripts/shared.py"], tmp_path, None)

    assert exit_code == ruff_ratchet.EXIT_VIOLATIONS


def test_absolute_ruff_filename_is_matched_against_the_map(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    payload = json.dumps([finding(str(tmp_path / "scripts" / "abs.py"), 7)])
    recorder = RunRecorder([completed(1, payload)])
    monkeypatch.setattr(ruff_ratchet.subprocess, "run", recorder)

    exit_code = ruff_ratchet.run_ruff(["scripts/abs.py"], tmp_path, {"scripts/abs.py": {7}})

    assert exit_code == ruff_ratchet.EXIT_VIOLATIONS


def test_finding_without_end_location_uses_the_start_row(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    bare = {
        "code": "F401",
        "message": "unused import",
        "filename": "scripts/bare.py",
        "location": {"row": 3, "column": 1},
    }
    recorder = RunRecorder([completed(1, json.dumps([bare]))])
    monkeypatch.setattr(ruff_ratchet.subprocess, "run", recorder)

    exit_code = ruff_ratchet.run_ruff(["scripts/bare.py"], tmp_path, {"scripts/bare.py": {3}})

    assert exit_code == ruff_ratchet.EXIT_VIOLATIONS


def test_malformed_ruff_json_is_external_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    recorder = RunRecorder([completed(1, "not json at all")])
    monkeypatch.setattr(ruff_ratchet.subprocess, "run", recorder)

    exit_code = ruff_ratchet.run_ruff(["scripts/a.py"], tmp_path, {})

    assert exit_code == ruff_ratchet.EXIT_EXTERNAL


def test_non_list_ruff_json_is_external_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    recorder = RunRecorder([completed(1, '{"code": "E501"}')])
    monkeypatch.setattr(ruff_ratchet.subprocess, "run", recorder)

    exit_code = ruff_ratchet.run_ruff(["scripts/a.py"], tmp_path, {})

    assert exit_code == ruff_ratchet.EXIT_EXTERNAL


def test_ruff_invocation_failure_is_external_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    recorder = RunRecorder([completed(2, stderr="ruff: unknown option\n")])
    monkeypatch.setattr(ruff_ratchet.subprocess, "run", recorder)

    exit_code = ruff_ratchet.run_ruff(["scripts/a.py"], tmp_path, {})

    assert exit_code == ruff_ratchet.EXIT_EXTERNAL


def test_git_diff_failure_is_external_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    recorder = RunRecorder(
        [
            completed(128, stderr="fatal: bad revision\n"),
            completed(128, stderr="fatal: bad fallback revision\n"),
        ]
    )
    monkeypatch.setattr(ruff_ratchet.subprocess, "run", recorder)

    status, files = ruff_ratchet.changed_python_files("missing-ref", tmp_path)

    assert status == ruff_ratchet.EXIT_EXTERNAL
    assert files == []
    assert len(recorder.commands) == 2


def test_main_rejects_a_non_git_repo_root(tmp_path: Path) -> None:
    assert ruff_ratchet.main(["--repo-root", str(tmp_path)]) == ruff_ratchet.EXIT_CONFIG
