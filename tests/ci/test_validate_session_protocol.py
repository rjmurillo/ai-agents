"""Tests for scripts/ci/validate_session_protocol.py.

The port fixes four defects the PowerShell original carried, each covered here:

* the deleted-file path never set ``artifact-name``, so every such leg uploaded
  to the artifact literally named ``validation-``;
* the deleted-file path wrote verdict files without the parent-directory
  prefix the normal path uses, so ``sessions/x`` and ``archive/x`` collided;
* a corrupt ``validation-summary.json`` threw out of ``ConvertFrom-Json``,
  killing the step before it wrote ``must-failures.txt`` at all;
* a summary missing the ``must_failures`` key cast to ``0`` in PowerShell, the
  same silent pass issue #3365 was filed to close.
"""

from __future__ import annotations

import json
import subprocess

import pytest

from scripts.ci import validate_session_protocol as mod


@pytest.fixture(autouse=True)
def _in_tmp_dir(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """Every test writes result files; keep them out of the checkout."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture(autouse=True)
def _default_validation_modes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Most tests exercise result handling, not validation-mode classification."""
    monkeypatch.setattr(
        mod,
        "committed_session_validation_modes",
        lambda paths, repo_root: {path: "full" for path in paths},
    )


def _completed(
    returncode: int = 0, stdout: str = "", stderr: str = ""
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["python"], returncode=returncode, stdout=stdout, stderr=stderr
    )


class TestArtifactName:
    def test_includes_the_parent_directory(self) -> None:
        assert mod.artifact_name(".agents/sessions/2026-01-05-session-1.json") == (
            "sessions-2026-01-05-session-1"
        )

    def test_same_stem_in_two_directories_does_not_collide(self) -> None:
        """This is the whole reason the parent name is in there."""
        a = mod.artifact_name(".agents/sessions/2026-01-05-session-1.json")
        b = mod.artifact_name(".agents/archive/2026-01-05-session-1.json")
        assert a != b

    def test_drops_the_extension(self) -> None:
        assert mod.artifact_name("s/x.json").endswith("x")

    def test_a_bare_filename_still_yields_a_name(self) -> None:
        assert mod.artifact_name("x.json") == "-x"


class TestEscapesWorkspace:
    """CWE-22 defence in depth. Not reachable through the workflow today: the
    detector anchors under .agents/sessions/ and git normalises stored paths.
    Both invariants are owned elsewhere, so the entry point checks locally."""

    @pytest.mark.parametrize(
        "path",
        [
            ".agents/sessions/2026-01-05-session-1.json",
            "sessions/x.json",
            "x.json",
            "./sessions/x.json",
            "a/../sessions/x.json",
        ],
    )
    def test_paths_inside_the_checkout_are_allowed(self, path: str) -> None:
        assert mod.escapes_workspace(path) is False

    @pytest.mark.parametrize(
        "path",
        [
            "../outside.json",
            ".agents/sessions/2026-01-05-session-1/../../../../etc/passwd.json",
            "/etc/passwd",
        ],
    )
    def test_paths_outside_the_checkout_are_rejected(self, path: str) -> None:
        assert mod.escapes_workspace(path) is True

    def test_main_refuses_an_escaping_path(self, tmp_path) -> None:
        assert mod.main(["--session-file", "../outside.json"]) == 2

    def test_main_writes_no_results_for_an_escaping_path(self, tmp_path) -> None:
        mod.main(["--session-file", "../outside.json"])
        assert not mod._RESULTS.exists()

    def test_main_emits_no_artifact_name_for_an_escaping_path(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        out = tmp_path / "out"
        out.touch()
        monkeypatch.setenv("GITHUB_OUTPUT", str(out))
        mod.main(["--session-file", "/etc/passwd"])
        assert out.read_text(encoding="utf-8") == ""


class TestMustFailureCount:
    def test_reads_the_count_from_the_summary(self) -> None:
        mod._SUMMARY.write_text(json.dumps({"must_failures": 3}), encoding="utf-8")
        assert mod.must_failure_count(1) == 3

    def test_a_zero_count_is_reported_as_zero(self) -> None:
        mod._SUMMARY.write_text(json.dumps({"must_failures": 0}), encoding="utf-8")
        assert mod.must_failure_count(0) == 0

    def test_a_string_count_is_coerced(self) -> None:
        mod._SUMMARY.write_text(json.dumps({"must_failures": "2"}), encoding="utf-8")
        assert mod.must_failure_count(1) == 2

    def test_a_corrupt_summary_assumes_a_failure(self) -> None:
        """PowerShell's ConvertFrom-Json threw here, killing the step mid-write."""
        mod._SUMMARY.write_text("{not json", encoding="utf-8")
        assert mod.must_failure_count(1) == 1

    def test_a_summary_missing_the_key_assumes_a_failure(self) -> None:
        """PowerShell cast the missing key to 0, the silent pass of issue #3365."""
        mod._SUMMARY.write_text(json.dumps({"other": 3}), encoding="utf-8")
        assert mod.must_failure_count(1) == 1

    def test_a_non_numeric_count_assumes_a_failure(self) -> None:
        mod._SUMMARY.write_text(json.dumps({"must_failures": "abc"}), encoding="utf-8")
        assert mod.must_failure_count(1) == 1

    def test_a_null_count_assumes_a_failure(self) -> None:
        mod._SUMMARY.write_text(json.dumps({"must_failures": None}), encoding="utf-8")
        assert mod.must_failure_count(1) == 1

    def test_no_summary_and_a_failing_validator_assumes_a_failure(self) -> None:
        assert not mod._SUMMARY.exists()
        assert mod.must_failure_count(1) == 1

    def test_no_summary_and_a_passing_validator_reports_zero(self) -> None:
        assert mod.must_failure_count(0) == 0

    def test_the_sentinel_is_above_the_enforcement_threshold(self) -> None:
        """The enforcement step tests ``> 0``; any lower sentinel reads as clean."""
        mod._SUMMARY.write_text(json.dumps({"other": 1}), encoding="utf-8")
        assert mod.must_failure_count(1) > 0


class TestValidate:
    def test_a_markdown_log_is_rejected_without_running_the_validator(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        called: list[list[str]] = []

        def fake_run(argv: list[str]) -> subprocess.CompletedProcess[str]:
            called.append(argv)
            return _completed()

        def _fail_modes(_paths: list[str], _repo_root) -> dict[str, str]:
            raise AssertionError("git probe should not run")

        monkeypatch.setattr(mod, "_run", fake_run)
        monkeypatch.setattr(mod, "committed_session_validation_modes", _fail_modes)
        code, findings = mod.validate("s/x.md")
        assert code == 1
        assert "no longer supported" in findings
        assert called == []

    def test_a_head_added_log_runs_the_validator_in_creation_mode(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen: list[list[str]] = []

        def fake_run(argv: list[str]) -> subprocess.CompletedProcess[str]:
            seen.append(argv)
            return _completed(stdout="ok")

        monkeypatch.setattr(mod, "_run", fake_run)
        monkeypatch.setattr(
            mod,
            "committed_session_validation_modes",
            lambda paths, repo_root: {"s/x.json": "creation"},
        )
        code, findings = mod.validate("s/x.json")
        assert code == 0
        assert findings == "ok"
        assert "./scripts/validate_session_json.py" in seen[0]
        assert "--creation-mode" in seen[0]
        assert "--existing-log" not in seen[0]
        assert "--json-output" in seen[0]

    def test_a_branch_owned_log_runs_the_validator_without_a_mode_flag(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen: list[list[str]] = []

        def fake_run(argv: list[str]) -> subprocess.CompletedProcess[str]:
            seen.append(argv)
            return _completed(stdout="ok")

        monkeypatch.setattr(mod, "_run", fake_run)
        monkeypatch.setattr(
            mod,
            "committed_session_validation_modes",
            lambda paths, repo_root: {"s/x.json": "full"},
        )
        code, findings = mod.validate("s/x.json")
        assert code == 0
        assert findings == "ok"
        assert "--existing-log" not in seen[0]
        assert "--creation-mode" not in seen[0]

    def test_a_historical_log_runs_the_validator_as_existing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen: list[list[str]] = []

        def fake_run(argv: list[str]) -> subprocess.CompletedProcess[str]:
            seen.append(argv)
            return _completed(stdout="ok")

        monkeypatch.setattr(mod, "_run", fake_run)
        monkeypatch.setattr(
            mod,
            "committed_session_validation_modes",
            lambda paths, repo_root: {"s/x.json": "existing"},
        )
        code, findings = mod.validate("s/x.json")
        assert code == 0
        assert findings == "ok"
        assert "--existing-log" in seen[0]
        assert "--creation-mode" not in seen[0]

    def test_a_git_probe_failure_blocks_without_running_the_validator(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        called: list[list[str]] = []

        def fake_run(argv: list[str]) -> subprocess.CompletedProcess[str]:
            called.append(argv)
            return _completed(stdout="ok")

        def mode_lookup(_paths: list[str], _repo_root: object) -> None:
            return None

        monkeypatch.setattr(mod, "_run", fake_run)
        monkeypatch.setattr(mod, "committed_session_validation_modes", mode_lookup)
        code, findings = mod.validate("s/x.json")
        assert code == 1
        assert "refusing to guess creation-mode" in findings
        assert called == []

    def test_pr_head_extends_validation_past_recorded_ending_commit(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen: list[list[str]] = []
        head = "c" * 40

        def fake_run(argv: list[str]) -> subprocess.CompletedProcess[str]:
            seen.append(argv)
            return _completed()

        monkeypatch.setattr(mod, "_run", fake_run)

        mod.validate("s/x.json", validation_head=head)

        assert seen[0][-2:] == ["--validation-head", head]

    def test_findings_merge_both_streams(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(mod, "_run", lambda argv: _completed(1, stdout="out\n", stderr="err\n"))
        _, findings = mod.validate("s/x.json")
        assert "out" in findings
        assert "err" in findings

    def test_the_validator_exit_code_is_returned_unchanged(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(mod, "_run", lambda argv: _completed(7))
        assert mod.validate("s/x.json")[0] == 7


class TestMain:
    def _outputs(self, path) -> dict[str, str]:
        parsed: dict[str, str] = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            key, _, value = line.partition("=")
            parsed[key] = value
        return parsed

    def test_a_compliant_log_writes_a_compliant_verdict(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (tmp_path / "sessions").mkdir()
        (tmp_path / "sessions" / "x.json").write_text("{}", encoding="utf-8")
        monkeypatch.setattr(mod, "_run", lambda argv: _completed(0, stdout="fine"))
        mod._SUMMARY.write_text(json.dumps({"must_failures": 0}), encoding="utf-8")

        assert mod.main(["--session-file", "sessions/x.json"]) == 0
        assert (mod._RESULTS / "sessions-x-verdict.txt").read_text().strip() == "COMPLIANT"
        assert (mod._RESULTS / "sessions-x-must-failures.txt").read_text().strip() == "0"

    def test_a_failing_log_writes_a_non_compliant_verdict_and_exits_non_zero(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (tmp_path / "sessions").mkdir()
        (tmp_path / "sessions" / "x.json").write_text("{}", encoding="utf-8")
        monkeypatch.setattr(mod, "_run", lambda argv: _completed(1, stdout="bad"))
        mod._SUMMARY.write_text(json.dumps({"must_failures": 2}), encoding="utf-8")

        assert mod.main(["--session-file", "sessions/x.json"]) == 1
        assert (mod._RESULTS / "sessions-x-verdict.txt").read_text().strip() == "NON_COMPLIANT"
        assert (mod._RESULTS / "sessions-x-must-failures.txt").read_text().strip() == "2"

    def test_findings_are_echoed_into_the_job_log_on_failure(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A blocking gate has to be readable without downloading an artifact (issue #3364)."""
        (tmp_path / "sessions").mkdir()
        (tmp_path / "sessions" / "x.json").write_text("{}", encoding="utf-8")
        monkeypatch.setattr(mod, "_run", lambda argv: _completed(1, stdout="the reason"))

        mod.main(["--session-file", "sessions/x.json"])
        captured = capsys.readouterr().out
        assert "::group::" in captured
        assert "the reason" in captured
        assert "::endgroup::" in captured

    def test_findings_are_not_grouped_on_success(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        (tmp_path / "sessions").mkdir()
        (tmp_path / "sessions" / "x.json").write_text("{}", encoding="utf-8")
        monkeypatch.setattr(mod, "_run", lambda argv: _completed(0, stdout="quiet"))

        mod.main(["--session-file", "sessions/x.json"])
        assert "::group::" not in capsys.readouterr().out

    def test_a_deleted_file_is_skipped_not_failed(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        assert mod.main(["--session-file", "sessions/gone.json"]) == 0
        assert (mod._RESULTS / "sessions-gone-verdict.txt").read_text().strip() == "SKIPPED"

    def test_a_deleted_file_still_sets_the_artifact_name(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The original returned before this, so the upload got ``validation-``."""
        out = tmp_path / "out"
        out.touch()
        monkeypatch.setenv("GITHUB_OUTPUT", str(out))

        mod.main(["--session-file", "sessions/gone.json"])
        assert self._outputs(out)["artifact-name"] == "sessions-gone"

    def test_two_deleted_logs_with_the_same_stem_do_not_collide(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The original dropped the parent prefix on this path only."""
        out = tmp_path / "out"
        out.touch()
        monkeypatch.setenv("GITHUB_OUTPUT", str(out))

        mod.main(["--session-file", "sessions/x.json"])
        mod.main(["--session-file", "archive/x.json"])
        names = sorted(p.name for p in mod._RESULTS.glob("*-verdict.txt"))
        assert names == ["archive-x-verdict.txt", "sessions-x-verdict.txt"]

    def test_the_artifact_name_matches_the_verdict_filenames(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The aggregate job globs by that prefix, so the two must agree."""
        out = tmp_path / "out"
        out.touch()
        monkeypatch.setenv("GITHUB_OUTPUT", str(out))
        (tmp_path / "sessions").mkdir()
        (tmp_path / "sessions" / "x.json").write_text("{}", encoding="utf-8")
        monkeypatch.setattr(mod, "_run", lambda argv: _completed(0))

        mod.main(["--session-file", "sessions/x.json"])
        name = self._outputs(out)["artifact-name"]
        assert (mod._RESULTS / f"{name}-verdict.txt").is_file()
        assert (mod._RESULTS / f"{name}-must-failures.txt").is_file()

    def test_a_deleted_file_reports_zero_must_failures(self, tmp_path) -> None:
        mod.main(["--session-file", "sessions/gone.json"])
        assert (mod._RESULTS / "sessions-gone-must-failures.txt").read_text().strip() == "0"

    def test_a_corrupt_summary_still_writes_the_must_failure_file(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """PowerShell threw here and never reached this write."""
        (tmp_path / "sessions").mkdir()
        (tmp_path / "sessions" / "x.json").write_text("{}", encoding="utf-8")
        monkeypatch.setattr(mod, "_run", lambda argv: _completed(1))
        mod._SUMMARY.write_text("{broken", encoding="utf-8")

        assert mod.main(["--session-file", "sessions/x.json"]) == 1
        assert (mod._RESULTS / "sessions-x-must-failures.txt").read_text().strip() == "1"

    def test_a_markdown_log_fails_with_an_actionable_message(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (tmp_path / "sessions").mkdir()
        (tmp_path / "sessions" / "x.md").write_text("# log", encoding="utf-8")

        assert mod.main(["--session-file", "sessions/x.md"]) == 1
        findings = (mod._RESULTS / "sessions-x-findings.txt").read_text(encoding="utf-8")
        assert "convert this file to JSON" in findings

    def test_a_missing_session_file_argument_is_a_config_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("SESSION_FILE", raising=False)
        assert mod.main([]) == 2

    def test_the_env_var_supplies_the_default(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SESSION_FILE", "sessions/gone.json")
        assert mod.main([]) == 0
        assert (mod._RESULTS / "sessions-gone-verdict.txt").is_file()

    def test_a_missing_github_output_does_not_raise(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
        assert mod.main(["--session-file", "sessions/gone.json"]) == 0

    def test_the_result_markdown_is_written_for_the_artifact(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (tmp_path / "sessions").mkdir()
        (tmp_path / "sessions" / "x.json").write_text("{}", encoding="utf-8")
        monkeypatch.setattr(mod, "_run", lambda argv: _completed(0, stdout="body"))

        mod.main(["--session-file", "sessions/x.json"])
        assert mod._RESULT_MD.read_text(encoding="utf-8") == "body"
