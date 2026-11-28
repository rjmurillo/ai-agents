"""Finding classification tests for the ruff ratchet."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.ci import ruff_ratchet
from tests.ci.ruff_ratchet_test_helpers import RunRecorder, completed, finding, names


def test_blocks_finding_on_an_added_line(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    payload = json.dumps([finding("scripts/dirty.py", 12)])
    recorder = RunRecorder([completed(1, payload)])
    monkeypatch.setattr(ruff_ratchet, "_run_subprocess", recorder)

    exit_code = ruff_ratchet.run_ruff(["scripts/dirty.py"], tmp_path, {"scripts/dirty.py": {12}})

    assert exit_code == ruff_ratchet.EXIT_VIOLATIONS


def test_pre_existing_finding_outside_the_change_does_not_block(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # The defect this gate was rewritten for: editing line 12 of a file that
    # already carried an E501 on line 300 used to block the push (issue #2993).
    payload = json.dumps([finding("scripts/shared.py", 300)])
    recorder = RunRecorder([completed(1, payload)])
    monkeypatch.setattr(ruff_ratchet, "_run_subprocess", recorder)

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
    monkeypatch.setattr(ruff_ratchet, "_run_subprocess", recorder)

    exit_code = ruff_ratchet.run_ruff(["scripts/multi.py"], tmp_path, {"scripts/multi.py": {13}})

    assert exit_code == ruff_ratchet.EXIT_VIOLATIONS


def test_renamed_file_with_unchanged_content_does_not_block(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # A pure rename produces no hunk, so the path is absent from the map even
    # though it is in the changed-file list.
    payload = json.dumps([finding("scripts/new_name.py", 4)])
    recorder = RunRecorder([completed(1, payload)])
    monkeypatch.setattr(ruff_ratchet, "_run_subprocess", recorder)

    exit_code = ruff_ratchet.run_ruff(["scripts/new_name.py"], tmp_path, {})

    assert exit_code == ruff_ratchet.EXIT_OK


def test_empty_stdout_at_returncode_1_is_an_external_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Ruff's own contract is returncode 1 means violations found. Empty stdout
    # alongside that (truncated output, a killed process, a broken pipe) is
    # not "zero findings"; treating it that way would silently pass a run
    # ruff itself flagged as failing.
    recorder = RunRecorder([completed(1, "")])
    monkeypatch.setattr(ruff_ratchet, "_run_subprocess", recorder)

    exit_code = ruff_ratchet.run_ruff(["scripts/dirty.py"], tmp_path, {"scripts/dirty.py": {12}})
    captured = capsys.readouterr()

    assert exit_code == ruff_ratchet.EXIT_EXTERNAL
    assert "no JSON output" in captured.err


def test_whitespace_only_stdout_at_returncode_1_is_an_external_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    recorder = RunRecorder([completed(1, "   \n")])
    monkeypatch.setattr(ruff_ratchet, "_run_subprocess", recorder)

    exit_code = ruff_ratchet.run_ruff(["scripts/dirty.py"], tmp_path, {})

    assert exit_code == ruff_ratchet.EXIT_EXTERNAL


def test_relative_finding_path_treats_an_empty_filename_as_unmappable(tmp_path: Path) -> None:
    assert ruff_ratchet.relative_finding_path("", tmp_path) is None


def test_missing_filename_finding_blocks_rather_than_passing_silently(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # A finding with no filename key defaults to "" via finding.get("filename", "").
    # relative_finding_path("") must return None (unmappable, block), not ""
    # (falsy but not None, which would fall through to a non-blocking lookup
    # on an empty-string key in the changed-line map).
    payload = json.dumps([{"code": "E501", "message": "x", "location": {"row": 1, "column": 1}}])
    recorder = RunRecorder([completed(1, payload)])
    monkeypatch.setattr(ruff_ratchet, "_run_subprocess", recorder)

    exit_code = ruff_ratchet.run_ruff(["scripts/dirty.py"], tmp_path, {})

    assert exit_code == ruff_ratchet.EXIT_VIOLATIONS


def test_unresolved_diff_base_blocks_every_finding(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    payload = json.dumps([finding("scripts/shared.py", 300)])
    recorder = RunRecorder([completed(1, payload)])
    monkeypatch.setattr(ruff_ratchet, "_run_subprocess", recorder)

    exit_code = ruff_ratchet.run_ruff(["scripts/shared.py"], tmp_path, None)

    assert exit_code == ruff_ratchet.EXIT_VIOLATIONS


def test_absolute_ruff_filename_is_matched_against_the_map(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    payload = json.dumps([finding(str(tmp_path / "scripts" / "abs.py"), 7)])
    recorder = RunRecorder([completed(1, payload)])
    monkeypatch.setattr(ruff_ratchet, "_run_subprocess", recorder)

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
    monkeypatch.setattr(ruff_ratchet, "_run_subprocess", recorder)

    exit_code = ruff_ratchet.run_ruff(["scripts/bare.py"], tmp_path, {"scripts/bare.py": {3}})

    assert exit_code == ruff_ratchet.EXIT_VIOLATIONS


def test_malformed_ruff_json_is_external_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    recorder = RunRecorder([completed(1, "not json at all")])
    monkeypatch.setattr(ruff_ratchet, "_run_subprocess", recorder)

    exit_code = ruff_ratchet.run_ruff(["scripts/a.py"], tmp_path, {})

    assert exit_code == ruff_ratchet.EXIT_EXTERNAL


def test_non_list_ruff_json_is_external_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    recorder = RunRecorder([completed(1, '{"code": "E501"}')])
    monkeypatch.setattr(ruff_ratchet, "_run_subprocess", recorder)

    exit_code = ruff_ratchet.run_ruff(["scripts/a.py"], tmp_path, {})

    assert exit_code == ruff_ratchet.EXIT_EXTERNAL


def test_ruff_invocation_failure_is_external_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    recorder = RunRecorder([completed(2, stderr="ruff: unknown option\n")])
    monkeypatch.setattr(ruff_ratchet, "_run_subprocess", recorder)

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
    monkeypatch.setattr(ruff_ratchet, "_run_subprocess", recorder)

    status, files, _base = ruff_ratchet.changed_python_files("missing-ref", tmp_path)

    assert status == ruff_ratchet.EXIT_EXTERNAL
    assert files == []
    assert len(recorder.commands) == 2


def test_main_rejects_a_non_git_repo_root(tmp_path: Path) -> None:
    assert ruff_ratchet.main(["--repo-root", str(tmp_path)]) == ruff_ratchet.EXIT_CONFIG


def test_main_builds_the_line_map_from_the_ref_that_resolved(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Regression: main used to pass the requested ref to changed_line_map even
    # when the file list came from the origin/main fallback. The stale ref
    # failed, the map dropped to None, and the gate blocked on every finding.
    (tmp_path / ".git").mkdir()
    changed_file = tmp_path / "scripts" / "fallback.py"
    changed_file.parent.mkdir()
    changed_file.write_text("print('ok')\n", encoding="utf-8")
    recorder = RunRecorder(
        [
            completed(128, stderr="fatal: bad revision\n"),
            completed(0, names("scripts/fallback.py")),
            completed(0, "[]"),
        ]
    )
    monkeypatch.setattr(ruff_ratchet, "_run_subprocess", recorder)
    seen: list[str] = []

    def record_base_ref(
        base_ref: str, _root: Path, _paths: object, **_kwargs: object
    ) -> dict[str, set[int]]:
        seen.append(base_ref)
        return {}

    monkeypatch.setattr(ruff_ratchet, "changed_line_map", record_base_ref)

    exit_code = ruff_ratchet.main(["--base-ref", "stale-sha", "--repo-root", str(tmp_path)])

    assert exit_code == ruff_ratchet.EXIT_OK
    assert seen == ["origin/main"]


def test_finding_outside_the_repo_root_blocks(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # A path that cannot be placed inside the repo can never match the map, so
    # passing it would make every finding in that file silently non-blocking.
    payload = json.dumps([finding("/elsewhere/outside.py", 3)])
    recorder = RunRecorder([completed(1, payload)])
    monkeypatch.setattr(ruff_ratchet, "_run_subprocess", recorder)

    exit_code = ruff_ratchet.run_ruff(["scripts/a.py"], tmp_path, {})

    assert exit_code == ruff_ratchet.EXIT_VIOLATIONS


def test_finding_with_a_null_row_does_not_raise(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    malformed = {
        "code": "E501",
        "message": "Line too long",
        "filename": "scripts/a.py",
        "location": {"row": None, "column": 1},
    }
    recorder = RunRecorder([completed(1, json.dumps([malformed]))])
    monkeypatch.setattr(ruff_ratchet, "_run_subprocess", recorder)

    exit_code = ruff_ratchet.run_ruff(["scripts/a.py"], tmp_path, {"scripts/a.py": {1}})

    assert exit_code == ruff_ratchet.EXIT_VIOLATIONS
