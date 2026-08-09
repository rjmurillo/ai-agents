"""Tests for scripts/ci/detect_session_logs.py.

Covers the two filters (path shape and date cutoff), the ``GITHUB_OUTPUT``
contract the matrix consumes, and the fail-closed behaviour when the files API
cannot be read.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
import yaml

from scripts.ci import detect_session_logs as mod

WORKFLOW = Path(".github/workflows/ai-session-protocol.yml")


def _workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))

SESSION = ".agents/sessions/2026-01-05-session-12.json"
OLD_SESSION = ".agents/sessions/2025-01-05-session-12.json"


def _completed(
    stdout: str = "", returncode: int = 0, stderr: str = ""
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["gh"], returncode=returncode, stdout=stdout, stderr=stderr
    )


class TestSessionLogs:
    @pytest.mark.parametrize(
        "path",
        [
            ".agents/sessions/2026-01-05-session-12.json",
            ".agents/sessions/2026-01-05-session-12.md",
            ".agents/sessions/2026-01-05-session-7-some-description.json",
            ".agents/sessions/2026-01-05-session-123.md",
        ],
    )
    def test_accepts_session_log_shapes(self, path: str) -> None:
        assert mod.session_logs([path]) == [path]

    @pytest.mark.parametrize(
        "path",
        [
            ".agents/sessions/STEP-0-METRICS.md",
            ".agents/sessions/README.md",
            ".agents/sessions/2026-01-05-session-12.txt",
            ".agents/sessions/2026-1-5-session-12.json",
            ".agents/sessions/2026-01-05-session-.json",
            "docs/2026-01-05-session-12.json",
            ".agents/archive/2026-01-05-session-12.json",
        ],
    )
    def test_rejects_non_session_paths(self, path: str) -> None:
        assert mod.session_logs([path]) == []

    def test_tally_file_beside_a_real_log_is_dropped(self) -> None:
        """The pattern exists to separate logs from the tallies filed next to them."""
        paths = [".agents/sessions/STEP-0-METRICS.md", SESSION]
        assert mod.session_logs(paths) == [SESSION]

    def test_preserves_input_order(self) -> None:
        second = ".agents/sessions/2026-02-05-session-1.json"
        assert mod.session_logs([SESSION, second]) == [SESSION, second]


class TestPartitionByCutoff:
    def test_logs_before_the_cutoff_are_skipped(self) -> None:
        validate, skip = mod.partition_by_cutoff([OLD_SESSION], "2025-12-21")
        assert validate == []
        assert skip == [OLD_SESSION]

    def test_logs_after_the_cutoff_are_validated(self) -> None:
        validate, skip = mod.partition_by_cutoff([SESSION], "2025-12-21")
        assert validate == [SESSION]
        assert skip == []

    def test_the_cutoff_date_itself_is_validated(self) -> None:
        """The rule landed on the cutoff date, so that day's logs are bound by it."""
        same = ".agents/sessions/2025-12-21-session-1.json"
        validate, skip = mod.partition_by_cutoff([same], "2025-12-21")
        assert validate == [same]
        assert skip == []

    def test_the_day_before_the_cutoff_is_skipped(self) -> None:
        before = ".agents/sessions/2025-12-20-session-1.json"
        validate, skip = mod.partition_by_cutoff([before], "2025-12-21")
        assert skip == [before]

    def test_an_unparseable_date_is_validated_not_skipped(self) -> None:
        """An odd filename is a reason to look, not a reason to look away."""
        odd = ".agents/sessions/session-weird.json"
        validate, skip = mod.partition_by_cutoff([odd], "2025-12-21")
        assert validate == [odd]
        assert skip == []

    def test_a_short_filename_does_not_raise(self) -> None:
        validate, skip = mod.partition_by_cutoff([".agents/sessions/a.json"], "2025-12-21")
        assert validate == [".agents/sessions/a.json"]
        assert skip == []

    def test_mixed_input_splits_both_ways(self) -> None:
        validate, skip = mod.partition_by_cutoff([SESSION, OLD_SESSION], "2025-12-21")
        assert validate == [SESSION]
        assert skip == [OLD_SESSION]


class TestChangedFiles:
    def test_reads_the_files_api_with_pagination(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """``gh pr diff`` truncates on large PRs (issue #468); the files API paginates."""
        seen: list[list[str]] = []

        def fake_run(argv: list[str]) -> subprocess.CompletedProcess[str]:
            seen.append(argv)
            return _completed(stdout=f"{SESSION}\nREADME.md\n")

        monkeypatch.setattr(mod, "_run", fake_run)
        assert mod.changed_files("o/r", "7") == [SESSION, "README.md"]
        assert seen[0][:3] == ["gh", "api", "repos/o/r/pulls/7/files"]
        assert "--paginate" in seen[0]

    def test_blank_lines_are_dropped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(mod, "_run", lambda argv: _completed(stdout=f"\n{SESSION}\n\n"))
        assert mod.changed_files("o/r", "7") == [SESSION]

    def test_a_failed_call_raises_rather_than_returning_empty(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An unreadable pull request is unknown, not clean."""
        monkeypatch.setattr(mod, "_run", lambda argv: _completed(returncode=1, stderr="boom"))
        with pytest.raises(mod.GhApiError, match="boom"):
            mod.changed_files("o/r", "7")

    def test_a_failure_with_no_stderr_still_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(mod, "_run", lambda argv: _completed(returncode=1))
        with pytest.raises(mod.GhApiError):
            mod.changed_files("o/r", "7")

    def test_a_rate_limit_403_is_retried_and_then_succeeds(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Issue #4510: PR #4508 exited 3 immediately on a single 403 rate-limit
        response instead of retrying."""
        calls = {"n": 0}

        def fake_run(argv: list[str]) -> subprocess.CompletedProcess[str]:
            calls["n"] += 1
            if calls["n"] < 3:
                return _completed(
                    returncode=1,
                    stderr=("gh: API rate limit exceeded for user ID 6811113. (HTTP 403)"),
                )
            return _completed(stdout=f"{SESSION}\n")

        sleeps: list[float] = []
        monkeypatch.setattr(mod, "_run", fake_run)
        monkeypatch.setattr(mod.time, "sleep", lambda seconds: sleeps.append(seconds))

        assert mod.changed_files("o/r", "7") == [SESSION]
        assert calls["n"] == 3
        assert len(sleeps) == 2

    def test_a_secondary_rate_limit_429_is_retried(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls = {"n": 0}

        def fake_run(argv: list[str]) -> subprocess.CompletedProcess[str]:
            calls["n"] += 1
            if calls["n"] < 2:
                return _completed(returncode=1, stderr="gh: secondary rate limit (HTTP 429)")
            return _completed(stdout=f"{SESSION}\n")

        monkeypatch.setattr(mod, "_run", fake_run)
        monkeypatch.setattr(mod.time, "sleep", lambda seconds: None)

        assert mod.changed_files("o/r", "7") == [SESSION]
        assert calls["n"] == 2

    def test_a_genuine_404_is_not_retried(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls = {"n": 0}

        def fake_run(argv: list[str]) -> subprocess.CompletedProcess[str]:
            calls["n"] += 1
            return _completed(returncode=1, stderr="gh: Not Found (HTTP 404)")

        monkeypatch.setattr(mod, "_run", fake_run)
        slept = []
        monkeypatch.setattr(mod.time, "sleep", lambda seconds: slept.append(seconds))

        with pytest.raises(mod.GhApiError, match="404"):
            mod.changed_files("o/r", "7")
        assert calls["n"] == 1
        assert slept == []

    def test_a_genuine_401_is_not_retried(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls = {"n": 0}

        def fake_run(argv: list[str]) -> subprocess.CompletedProcess[str]:
            calls["n"] += 1
            return _completed(returncode=1, stderr="gh: Bad credentials (HTTP 401)")

        monkeypatch.setattr(mod, "_run", fake_run)
        slept = []
        monkeypatch.setattr(mod.time, "sleep", lambda seconds: slept.append(seconds))

        with pytest.raises(mod.GhApiError, match="401"):
            mod.changed_files("o/r", "7")
        assert calls["n"] == 1
        assert slept == []

    def test_a_permission_403_without_rate_limit_text_is_not_retried(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A 403 is retried only when it names a rate limit; plain permission
        denial is permanent."""
        calls = {"n": 0}

        def fake_run(argv: list[str]) -> subprocess.CompletedProcess[str]:
            calls["n"] += 1
            return _completed(
                returncode=1, stderr="gh: Resource not accessible by integration (HTTP 403)"
            )

        monkeypatch.setattr(mod, "_run", fake_run)
        slept = []
        monkeypatch.setattr(mod.time, "sleep", lambda seconds: slept.append(seconds))

        with pytest.raises(mod.GhApiError, match="403"):
            mod.changed_files("o/r", "7")
        assert calls["n"] == 1
        assert slept == []

    def test_retry_budget_exhaustion_raises_after_max_attempts(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls = {"n": 0}

        def fake_run(argv: list[str]) -> subprocess.CompletedProcess[str]:
            calls["n"] += 1
            return _completed(returncode=1, stderr="gh: API rate limit exceeded (HTTP 403)")

        monkeypatch.setattr(mod, "_run", fake_run)
        slept = []
        monkeypatch.setattr(mod.time, "sleep", lambda seconds: slept.append(seconds))

        with pytest.raises(mod.GhApiError, match="rate limit"):
            mod.changed_files("o/r", "7")
        assert calls["n"] == mod._MAX_ATTEMPTS
        assert len(slept) == mod._MAX_ATTEMPTS - 1

    def test_retry_budget_exhaustion_surfaces_as_exit_code_3(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Fail only after the retry budget is exhausted (issue #4510); the
        documented external-API exit code is 3 (ADR-035)."""
        out = tmp_path / "out"
        out.touch()
        monkeypatch.setenv("GITHUB_OUTPUT", str(out))
        monkeypatch.setattr(
            mod,
            "_run",
            lambda argv: _completed(returncode=1, stderr="gh: API rate limit exceeded (HTTP 403)"),
        )
        monkeypatch.setattr(mod.time, "sleep", lambda seconds: None)

        assert mod.main(["--repo", "o/r", "--pr-number", "7", "--cutoff", "2025-12-21"]) == 3

    def test_retry_after_header_is_honoured_over_backoff(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Edge: Retry-After must be respected rather than a fixed/computed
        backoff sleep."""
        calls = {"n": 0}

        def fake_run(argv: list[str]) -> subprocess.CompletedProcess[str]:
            calls["n"] += 1
            if calls["n"] < 2:
                return _completed(
                    returncode=1,
                    stderr="gh: API rate limit exceeded (HTTP 403) Retry-After: 42",
                )
            return _completed(stdout=f"{SESSION}\n")

        sleeps: list[float] = []
        monkeypatch.setattr(mod, "_run", fake_run)
        monkeypatch.setattr(mod.time, "sleep", lambda seconds: sleeps.append(seconds))

        assert mod.changed_files("o/r", "7") == [SESSION]
        assert sleeps == [42.0]

    def test_x_ratelimit_reset_is_honoured_when_no_retry_after(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Edge: X-RateLimit-Reset (an epoch second timestamp) is honoured
        when Retry-After is absent."""
        calls = {"n": 0}
        fixed_now = 1_700_000_000.0

        def fake_run(argv: list[str]) -> subprocess.CompletedProcess[str]:
            calls["n"] += 1
            if calls["n"] < 2:
                return _completed(
                    returncode=1,
                    stderr=(
                        "gh: API rate limit exceeded (HTTP 403) "
                        f"X-RateLimit-Reset: {int(fixed_now) + 30}"
                    ),
                )
            return _completed(stdout=f"{SESSION}\n")

        sleeps: list[float] = []
        monkeypatch.setattr(mod, "_run", fake_run)
        monkeypatch.setattr(mod.time, "sleep", lambda seconds: sleeps.append(seconds))
        monkeypatch.setattr(mod.time, "time", lambda: fixed_now)

        assert mod.changed_files("o/r", "7") == [SESSION]
        assert sleeps == [30.0]


class TestMain:
    def _outputs(self, path) -> dict[str, str]:
        parsed: dict[str, str] = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            key, _, value = line.partition("=")
            parsed[key] = value
        return parsed

    def test_a_validatable_log_sets_has_sessions_true_and_a_json_matrix(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        out = tmp_path / "out"
        out.touch()
        monkeypatch.setenv("GITHUB_OUTPUT", str(out))
        monkeypatch.setattr(mod, "_run", lambda argv: _completed(stdout=f"{SESSION}\nREADME.md\n"))

        assert mod.main(["--repo", "o/r", "--pr-number", "7", "--cutoff", "2025-12-21"]) == 0
        outputs = self._outputs(out)
        assert outputs["has_sessions"] == "true"
        assert json.loads(outputs["session_files"]) == [SESSION]

    def test_no_session_files_sets_has_sessions_false_and_an_empty_matrix(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``fromJson`` still has to parse, so the empty case must emit ``[]``."""
        out = tmp_path / "out"
        out.touch()
        monkeypatch.setenv("GITHUB_OUTPUT", str(out))
        monkeypatch.setattr(mod, "_run", lambda argv: _completed(stdout="README.md\n"))

        assert mod.main(["--repo", "o/r", "--pr-number", "7", "--cutoff", "2025-12-21"]) == 0
        outputs = self._outputs(out)
        assert outputs["has_sessions"] == "false"
        assert json.loads(outputs["session_files"]) == []

    def test_only_historical_logs_sets_has_sessions_false(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        out = tmp_path / "out"
        out.touch()
        monkeypatch.setenv("GITHUB_OUTPUT", str(out))
        monkeypatch.setattr(mod, "_run", lambda argv: _completed(stdout=f"{OLD_SESSION}\n"))

        assert mod.main(["--repo", "o/r", "--pr-number", "7", "--cutoff", "2025-12-21"]) == 0
        assert self._outputs(out)["has_sessions"] == "false"

    def test_the_skipped_list_is_printed(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        out = tmp_path / "out"
        out.touch()
        monkeypatch.setenv("GITHUB_OUTPUT", str(out))
        monkeypatch.setattr(
            mod, "_run", lambda argv: _completed(stdout=f"{SESSION}\n{OLD_SESSION}\n")
        )

        mod.main(["--repo", "o/r", "--pr-number", "7", "--cutoff", "2025-12-21"])
        captured = capsys.readouterr().out
        assert "Skipped historical sessions (before 2025-12-21)" in captured
        assert OLD_SESSION in captured

    def test_a_files_api_failure_exits_non_zero(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Fail closed: the shell original masked this with ``|| true`` and passed."""
        out = tmp_path / "out"
        out.touch()
        monkeypatch.setenv("GITHUB_OUTPUT", str(out))
        monkeypatch.setattr(
            mod, "_run", lambda argv: _completed(returncode=1, stderr="rate limited")
        )

        assert mod.main(["--repo", "o/r", "--pr-number", "7", "--cutoff", "2025-12-21"]) == 3
        assert out.read_text(encoding="utf-8") == ""

    @pytest.mark.parametrize(
        "argv",
        [
            ["--repo", "", "--pr-number", "7", "--cutoff", "2025-12-21"],
            ["--repo", "o/r", "--pr-number", "", "--cutoff", "2025-12-21"],
            ["--repo", "o/r", "--pr-number", "7", "--cutoff", ""],
        ],
    )
    def test_missing_required_input_is_a_config_error(
        self, argv: list[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
        assert mod.main(argv) == 2

    def test_env_vars_supply_the_defaults(self, tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
        out = tmp_path / "out"
        out.touch()
        monkeypatch.setenv("GITHUB_OUTPUT", str(out))
        monkeypatch.setenv("GH_REPO", "o/r")
        monkeypatch.setenv("PR_NUMBER", "7")
        monkeypatch.setenv("CUTOFF_DATE", "2025-12-21")
        monkeypatch.setattr(mod, "_run", lambda argv: _completed(stdout=f"{SESSION}\n"))

        assert mod.main([]) == 0
        assert self._outputs(out)["has_sessions"] == "true"

    def test_a_missing_github_output_does_not_raise(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
        monkeypatch.setattr(mod, "_run", lambda argv: _completed(stdout=f"{SESSION}\n"))
        assert mod.main(["--repo", "o/r", "--pr-number", "7", "--cutoff", "2025-12-21"]) == 0

    def test_the_matrix_json_is_compact(self, tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
        """``fromJson`` is fine either way, but the output line must not wrap."""
        out = tmp_path / "out"
        out.touch()
        monkeypatch.setenv("GITHUB_OUTPUT", str(out))
        second = ".agents/sessions/2026-02-05-session-1.json"
        monkeypatch.setattr(mod, "_run", lambda argv: _completed(stdout=f"{SESSION}\n{second}\n"))

        mod.main(["--repo", "o/r", "--pr-number", "7", "--cutoff", "2025-12-21"])
        line = self._outputs(out)["session_files"]
        assert "\n" not in line
        assert ", " not in line


class TestWorkflowWiring:
    def test_the_workflow_invokes_this_script(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        assert "scripts/ci/detect_session_logs.py" in text

    def test_the_workflow_still_supplies_every_required_input(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        detect = text.split("scripts/ci/detect_session_logs.py")[0]
        for key in ("PR_NUMBER:", "GH_REPO:", "CUTOFF_DATE:"):
            assert key in detect, f"{key} must reach the detector"

    def test_manual_dispatch_supplies_pr_number_to_session_detection(self) -> None:
        workflow = _workflow()
        on_block = workflow.get("on", workflow.get(True))
        assert on_block["workflow_dispatch"]["inputs"]["pr_number"]["required"] is True

        env = workflow["jobs"]["detect-changes"]["steps"][1]["env"]
        assert env["PR_NUMBER"] == "${{ github.event.pull_request.number || inputs.pr_number }}"

    def test_manual_dispatch_uses_a_valid_checkout_ref(self) -> None:
        checkout = _workflow()["jobs"]["detect-changes"]["steps"][0]["with"]
        assert checkout["ref"] == "${{ github.event.pull_request.head.sha || github.ref }}"
