from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.ci import ruff_ratchet
from scripts.cli_exec import resolve_executable


class RunRecorder:
    """Fake for the shared runner ``_run_subprocess``; records each call."""

    def __init__(self, results: list[subprocess.CompletedProcess[str]]) -> None:
        self.results = results
        self.commands: list[list[str]] = []
        self.timeouts: list[int] = []
        self.cwds: list[Path | str | None] = []

    def __call__(
        self,
        args: list[str],
        timeout: int = 300,
        cwd: Path | str | None = None,
        env: dict[str, str] | None = None,
    ) -> tuple[int, str, str]:
        self.commands.append(args)
        self.timeouts.append(timeout)
        self.cwds.append(cwd)
        result = self.results.pop(0)
        return result.returncode, result.stdout, result.stderr


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
        "-P",
        "-m",
        "ruff",
        "check",
        "--output-format=json",
        "--",
        "--config.py",
    ]


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
    monkeypatch.setattr(ruff_ratchet.importlib.util, "find_spec", lambda _name: None)

    exit_code = ruff_ratchet.run_ruff(["scripts/a.py"], tmp_path, {})

    assert exit_code == ruff_ratchet.EXIT_OK
    assert recorder.commands[0][:2] == ["ruff", "check"]


def test_windows_commands_name_native_executables_not_batch_shims(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    recorder = RunRecorder([completed(0, ""), completed(0, "[]")])
    monkeypatch.setattr(ruff_ratchet, "_run_subprocess", recorder)
    monkeypatch.setattr(ruff_ratchet.os, "name", "nt")
    monkeypatch.setattr(ruff_ratchet.importlib.util, "find_spec", lambda _name: None)

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
    monkeypatch.setattr(ruff_ratchet.importlib.util, "find_spec", lambda _name: None)

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

    def record_base_ref(base_ref: str, _root: Path, _paths: object) -> dict[str, set[int]]:
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


# --- Subprocess deadlines -------------------------------------------------
#
# The shared runner reports a timeout as exit -1 with a "Command timed out
# after Ns" marker in stderr, and a missing executable as exit -1 with
# "Command not found: <name>". These tests feed those shapes through the fake
# and assert the gate fails closed with exit 3.


def timed_out(seconds: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
    """Render the runner's timeout result, partial stderr first, marker last."""
    marker = f"Command timed out after {seconds}s"
    return completed(-1, stdout, f"{stderr}\n{marker}" if stderr else marker)


def make_changed_file(tmp_path: Path, name: str = "scripts/a.py") -> None:
    target = tmp_path / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("print('ok')\n", encoding="utf-8")


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


# --- CLI contract: exit codes 0, 1, 2, 3 through main ----------------------


def stub_line_map(monkeypatch: pytest.MonkeyPatch, lines: dict[str, set[int]]) -> None:
    monkeypatch.setattr(ruff_ratchet, "changed_line_map", lambda *_args: lines)


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


# --- Through the real shared runner ----------------------------------------
#
# The tests above fake ``_run_subprocess`` and write its marker text by hand.
# These run the real runner with only ``Popen`` replaced, so a change to the
# runner's timeout contract (exit -1, "Command timed out after Ns") fails here.


class _HungPopen:
    """``Popen`` stand-in whose first ``communicate`` times out, then drains."""

    pid = 1
    returncode = None
    _handle = 1

    def __init__(self, partial_stdout: bytes, partial_stderr: bytes) -> None:
        self._partial = (partial_stdout, partial_stderr)
        self.timeouts: list[float | None] = []
        self.killed = False

    def __enter__(self) -> _HungPopen:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def communicate(self, timeout: float | None = None) -> tuple[bytes, bytes]:
        self.timeouts.append(timeout)
        if len(self.timeouts) == 1:
            raise subprocess.TimeoutExpired("ruff", timeout or 0, *self._partial)
        return self._partial

    def kill(self) -> None:
        self.killed = True

    def wait(self, timeout: float | None = None) -> int:
        return self.returncode if self.returncode is not None else 0


def _install_noop_windows_job(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep runner-contract fakes out of real Windows job assignment.

    These tests replace ``Popen`` with an object that has no real process
    handle. They exercise timeout and output plumbing, not job assignment, so
    the Windows branch needs the same seam the POSIX tests already get from
    the absent job-object path.
    """
    from scripts.validation import subprocess_runner

    class _NoopJob:
        def __init__(self, _process: object) -> None:
            pass

        def resume(self, _process: object) -> None:
            pass

        def terminate(self) -> None:
            pass

        def close(self) -> None:
            pass

    monkeypatch.setattr(subprocess_runner, "_WindowsJob", _NoopJob, raising=False)


def _install_hung_popen(
    monkeypatch: pytest.MonkeyPatch, partial_stdout: bytes, partial_stderr: bytes
) -> _HungPopen:
    from scripts.validation import subprocess_runner

    child = _HungPopen(partial_stdout, partial_stderr)
    _install_noop_windows_job(monkeypatch)
    monkeypatch.setattr(subprocess_runner.subprocess, "Popen", lambda *_a, **_k: child)
    # The stand-in has no real pid; never signal a process group for it.
    monkeypatch.setattr(subprocess_runner, "_terminate", lambda _proc, _job=None: None)
    return child


@pytest.mark.windows_path
def test_real_runner_ruff_timeout_exits_external_with_partial_output(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    child = _install_hung_popen(monkeypatch, b'[{"code": "E5', b"warning: slow\n")

    exit_code = ruff_ratchet.run_ruff(["scripts/a.py"], tmp_path, {})
    captured = capsys.readouterr()

    assert exit_code == ruff_ratchet.EXIT_EXTERNAL
    assert child.timeouts[0] == ruff_ratchet._RUFF_TIMEOUT_SECONDS
    assert f"Command timed out after {ruff_ratchet._RUFF_TIMEOUT_SECONDS}s" in captured.err
    assert "warning: slow" in captured.err
    assert '[{"code": "E5' in captured.err


@pytest.mark.windows_path
def test_real_runner_git_timeout_exits_external_with_partial_output(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    child = _install_hung_popen(monkeypatch, b"scripts/partial.py\0", b"progress: reading refs")

    status, files, _base = ruff_ratchet.changed_python_files("feature-base", tmp_path)
    captured = capsys.readouterr()

    assert status == ruff_ratchet.EXIT_EXTERNAL
    assert files == []
    assert child.timeouts[0] == ruff_ratchet._GIT_TIMEOUT_SECONDS
    # One hung call: the timed-out communicate plus its drain, no second git.
    assert len(child.timeouts) == 2
    assert f"Command timed out after {ruff_ratchet._GIT_TIMEOUT_SECONDS}s" in captured.err
    assert "progress: reading refs" in captured.err
    assert "git partial stdout" in captured.err
    assert "scripts/partial.py" in captured.err


@pytest.mark.windows_path
def test_hung_popen_fixture_reaches_communicate_under_simulated_windows(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The Windows branch must not kill the runner-contract fake before use."""
    from scripts.validation import subprocess_runner

    child = _install_hung_popen(monkeypatch, b"", b"")
    monkeypatch.setattr(subprocess_runner.os, "name", "nt")
    monkeypatch.setattr(subprocess_runner.sys, "platform", "win32")
    monkeypatch.setattr(subprocess_runner, "_SUPPORTS_PGROUP", False)

    exit_code = ruff_ratchet.run_ruff(["scripts/a.py"], tmp_path, {})

    assert exit_code == ruff_ratchet.EXIT_EXTERNAL
    assert child.timeouts, "the Windows setup path never reached communicate"


@pytest.mark.windows_path
def test_real_runner_missing_ruff_module_exits_external(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from scripts.validation import subprocess_runner

    class _MissingModulePopen:
        pid = 1
        returncode = 1
        _handle = 1

        def communicate(self, timeout: float | None = None) -> tuple[str, str]:
            return "", "No module named ruff\n"

        def kill(self) -> None:
            return None

        def wait(self, timeout: float | None = None) -> int:
            return self.returncode

        def __enter__(self) -> _MissingModulePopen:
            return self

        def __exit__(self, *_exc: object) -> None:
            return None

    _install_noop_windows_job(monkeypatch)
    monkeypatch.setattr(
        subprocess_runner.subprocess,
        "Popen",
        lambda *_a, **_k: _MissingModulePopen(),
    )

    exit_code = ruff_ratchet.run_ruff(["scripts/a.py"], tmp_path, {})

    assert exit_code == ruff_ratchet.EXIT_EXTERNAL
    captured = capsys.readouterr()
    assert "No module named ruff" in captured.err
    assert "produced no JSON output" in captured.err
