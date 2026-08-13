"""Tests for ``scripts/ci/check_agent_infrastructure.py`` (issues #3527, #4778)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from scripts.ci import check_agent_infrastructure as cai
from scripts.ci.check_agent_infrastructure import CopilotAuthStatus as Auth

REPO_ROOT = Path(__file__).resolve().parents[2]

ACTION = REPO_ROOT / ".github" / "actions" / "check-agent-infrastructure" / "action.yml"
AI_REVIEW_ACTION = REPO_ROOT / ".github" / "actions" / "ai-review" / "action.yml"
AGENT_REVIEW_ACTION = REPO_ROOT / ".github" / "actions" / "agent-review" / "action.yml"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ai-pr-quality-gate.yml"


def _probe(*, gh: bool, auth: Auth, copilot: bool) -> cai.Probe:
    return cai.Probe(github_cli=gh, copilot_auth=auth, copilot=copilot)


def _ok(text: str = "octocat") -> cai.CommandOutcome:
    return cai.CommandOutcome(returncode=0, output=text)


def _fail(text: str) -> cai.CommandOutcome:
    return cai.CommandOutcome(returncode=1, output=text)


class TestStatusGrading:
    """The grade and the gate are the only consumer-visible decisions."""

    def test_everything_present_is_ready(self) -> None:
        probe = _probe(gh=True, auth=Auth.VALID, copilot=True)
        assert probe.status == "ready"
        assert probe.reviews_enabled is True

    def test_missing_copilot_binary_is_unavailable(self) -> None:
        # Issue #4778: a missing binary must not read as a runnable environment.
        probe = _probe(gh=True, auth=Auth.VALID, copilot=False)
        assert probe.status == "unavailable"
        assert probe.reviews_enabled is False

    def test_rejected_credential_is_unavailable_even_with_the_binary(self) -> None:
        # The exact issue #4778 shape: binary present, credential refused.
        probe = _probe(gh=True, auth=Auth.REJECTED, copilot=True)
        assert probe.status == "unavailable"
        assert probe.reviews_enabled is False

    def test_absent_credential_is_unavailable_even_with_the_binary(self) -> None:
        probe = _probe(gh=True, auth=Auth.ABSENT, copilot=True)
        assert probe.status == "unavailable"
        assert probe.reviews_enabled is False

    def test_unverified_credential_is_degraded_and_still_runs(self) -> None:
        # A rate limit is not evidence the credential is dead, so reviews run.
        probe = _probe(gh=True, auth=Auth.UNVERIFIED, copilot=True)
        assert probe.status == "degraded"
        assert probe.reviews_enabled is True

    def test_missing_cli_is_unavailable(self) -> None:
        probe = _probe(gh=False, auth=Auth.ABSENT, copilot=False)
        assert probe.status == "unavailable"
        assert probe.reviews_enabled is False

    def test_valid_auth_without_the_cli_is_unavailable(self) -> None:
        probe = _probe(gh=False, auth=Auth.VALID, copilot=True)
        assert probe.status == "unavailable"
        assert probe.reviews_enabled is False

    def test_auth_valid_tracks_only_the_valid_status(self) -> None:
        for status in Auth:
            probe = _probe(gh=True, auth=status, copilot=True)
            assert probe.auth_valid is (status is Auth.VALID)


class TestGithubCliProbe:
    def test_missing_gh_records_a_warning(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(cai.shutil, "which", lambda _name: None)
        probe = cai.Probe()
        cai._probe_github_cli(probe)
        assert probe.github_cli is False
        assert "GitHub CLI: NOT FOUND" in probe.summary
        assert any(a.startswith("::warning::") for a in probe.annotations)

    def test_present_gh_records_the_version(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(cai.shutil, "which", lambda _name: "/usr/bin/gh")
        monkeypatch.setattr(cai, "_first_line", lambda _argv: "gh version 2.60.1")
        probe = cai.Probe()
        cai._probe_github_cli(probe)
        assert probe.github_cli is True
        assert "GitHub CLI: gh version 2.60.1" in probe.summary

    def test_a_silent_gh_falls_back_to_unknown(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(cai.shutil, "which", lambda _name: "/usr/bin/gh")
        monkeypatch.setattr(cai, "_first_line", lambda _argv: "")
        probe = cai.Probe()
        cai._probe_github_cli(probe)
        assert "GitHub CLI: unknown" in probe.summary


class TestCopilotAuthClassification:
    """Maps a ``gh api user`` outcome to the operator action it requires."""

    def test_success_is_valid(self) -> None:
        assert cai.classify_copilot_auth(_ok()) is Auth.VALID

    def test_bad_credentials_is_rejected(self) -> None:
        # Verbatim from issue #4778 run 31283819979 job 93169277989.
        outcome = _fail("Failed to fetch PAT user login (401): GitHub returned: Bad credentials")
        assert cai.classify_copilot_auth(outcome) is Auth.REJECTED

    def test_installation_token_403_is_rejected(self) -> None:
        # The message the old probe collected on every run. Now it can only be
        # produced by a genuinely wrong-scoped Copilot credential, because the
        # probe no longer sends the runner token to this endpoint.
        outcome = _fail("gh: Resource not accessible by integration (HTTP 403)")
        assert cai.classify_copilot_auth(outcome) is Auth.REJECTED

    @pytest.mark.parametrize(
        "text",
        [
            "API rate limit exceeded for user ID 6811113",
            "You have exceeded a secondary rate limit",
            "connection reset by peer",
            "i/o timeout",
        ],
    )
    def test_transient_faults_are_unverified(self, text: str) -> None:
        assert cai.classify_copilot_auth(_fail(text)) is Auth.UNVERIFIED


class TestCopilotAuthProbe:
    def test_an_empty_token_is_absent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(cai.COPILOT_TOKEN_ENV, "   ")
        probe = cai.Probe(github_cli=True)
        cai._probe_copilot_auth(probe)
        assert probe.copilot_auth is Auth.ABSENT
        assert probe.reviews_enabled is False
        assert any("Provision the secret" in a for a in probe.annotations)

    def test_an_unset_token_is_absent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(cai.COPILOT_TOKEN_ENV, raising=False)
        probe = cai.Probe(github_cli=True)
        cai._probe_copilot_auth(probe)
        assert probe.copilot_auth is Auth.ABSENT

    def test_a_valid_token_records_the_login(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(cai.COPILOT_TOKEN_ENV, "ghp_valid")
        monkeypatch.setattr(cai, "_run", lambda _argv, env=None: _ok("rjmurillo-bot"))
        probe = cai.Probe(github_cli=True)
        cai._probe_copilot_auth(probe)
        assert probe.copilot_auth is Auth.VALID
        assert "Copilot auth: valid (user: rjmurillo-bot)" in probe.summary

    def test_a_rejected_token_tells_the_operator_to_rotate(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(cai.COPILOT_TOKEN_ENV, "ghp_expired")
        monkeypatch.setattr(
            cai, "_run", lambda _argv, env=None: _fail("HTTP 401: Bad credentials")
        )
        probe = cai.Probe(github_cli=True)
        cai._probe_copilot_auth(probe)
        assert probe.copilot_auth is Auth.REJECTED
        assert any("Rotate the secret" in a for a in probe.annotations)

    def test_a_rate_limited_probe_does_not_advise_rotation(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(cai.COPILOT_TOKEN_ENV, "ghp_fine")
        monkeypatch.setattr(
            cai, "_run", lambda _argv, env=None: _fail("API rate limit exceeded")
        )
        probe = cai.Probe(github_cli=True)
        cai._probe_copilot_auth(probe)
        assert probe.copilot_auth is Auth.UNVERIFIED
        assert all("Rotate the secret" not in a for a in probe.annotations)

    def test_the_probe_uses_the_copilot_token_not_the_runner_token(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Issue #4778 root cause: the runner token must not answer for Copilot."""
        monkeypatch.setenv("GH_TOKEN", "runner-installation-token")
        monkeypatch.setenv("GITHUB_TOKEN", "runner-installation-token")
        monkeypatch.setenv(cai.COPILOT_TOKEN_ENV, "ghp_copilot")
        seen: dict[str, object] = {}

        def _capture(argv: list[str], env: dict[str, str] | None = None) -> cai.CommandOutcome:
            seen["argv"] = argv
            seen["env"] = env
            return _ok("rjmurillo-bot")

        monkeypatch.setattr(cai, "_run", _capture)
        cai._probe_copilot_auth(cai.Probe(github_cli=True))

        assert seen["argv"] == ["gh", "api", "user", "-q", ".login"]
        env = seen["env"]
        assert isinstance(env, dict)
        assert env["GH_TOKEN"] == "ghp_copilot"
        assert env["GITHUB_TOKEN"] == "ghp_copilot"

    def test_without_the_cli_the_credential_is_unverified_not_rejected(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(cai.COPILOT_TOKEN_ENV, "ghp_valid")
        called: list[list[str]] = []
        monkeypatch.setattr(
            cai, "_run", lambda argv, env=None: called.append(argv) or _ok()  # type: ignore[func-returns-value]
        )
        probe = cai.Probe(github_cli=False)
        cai._probe_copilot_auth(probe)
        assert probe.copilot_auth is Auth.UNVERIFIED
        assert called == []

    def test_raw_command_output_never_reaches_the_log(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A credential echoed by gh must not land in a public transcript."""
        secret = "ghp_secretvalue0123456789"
        monkeypatch.setenv(cai.COPILOT_TOKEN_ENV, secret)
        monkeypatch.setattr(
            cai,
            "_run",
            lambda _argv, env=None: _fail(f"HTTP 401: Bad credentials for {secret}"),
        )
        probe = cai.Probe(github_cli=True)
        cai._probe_copilot_auth(probe)
        assert all(secret not in line for line in probe.summary)
        assert all(secret not in line for line in probe.annotations)


class TestCopilotProbe:
    def test_the_standalone_binary_wins(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            cai.shutil, "which", lambda name: "/bin/copilot" if name == "copilot" else None
        )
        monkeypatch.setattr(cai, "_first_line", lambda _argv: "1.0.76")
        probe = cai.Probe(github_cli=True)
        cai._probe_copilot(probe)
        assert probe.copilot is True
        assert "Copilot CLI: 1.0.76" in probe.summary

    def test_the_gh_extension_is_the_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(cai.shutil, "which", lambda _name: None)
        monkeypatch.setattr(cai, "_first_line", lambda _argv: "0.5.4")
        probe = cai.Probe(github_cli=True)
        cai._probe_copilot(probe)
        assert probe.copilot is True
        assert "Copilot CLI (via gh extension): 0.5.4" in probe.summary

    def test_the_extension_is_not_probed_without_the_cli(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(cai.shutil, "which", lambda _name: None)
        calls: list[list[str]] = []

        def _record(argv: list[str]) -> str:
            calls.append(argv)
            return "0.5.4"

        monkeypatch.setattr(cai, "_first_line", _record)
        probe = cai.Probe(github_cli=False)
        cai._probe_copilot(probe)
        assert probe.copilot is False
        assert calls == []
        assert "Copilot CLI: NOT FOUND" in probe.summary

    def test_a_failed_extension_probe_is_not_found(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(cai.shutil, "which", lambda _name: None)
        monkeypatch.setattr(cai, "_first_line", lambda _argv: None)
        probe = cai.Probe(github_cli=True)
        cai._probe_copilot(probe)
        assert probe.copilot is False
        assert "Copilot CLI: NOT FOUND" in probe.summary


class TestGateAnnouncement:
    """The log may not promise a skip that does not happen (issue #4778)."""

    def test_a_runnable_environment_announces_enabled(self) -> None:
        probe = _probe(gh=True, auth=Auth.VALID, copilot=True)
        cai._record_gate(probe)
        assert "Agent reviews: ENABLED" in probe.summary
        assert all("will be skipped" not in a for a in probe.annotations)

    def test_a_blocked_environment_announces_the_skip_and_the_consequence(self) -> None:
        probe = _probe(gh=True, auth=Auth.REJECTED, copilot=True)
        cai._record_gate(probe)
        assert "Agent reviews: SKIPPED (infrastructure unavailable)" in probe.summary
        assert any("DID_NOT_RUN" in a for a in probe.annotations)


class TestRenderOutputs:
    def test_booleans_are_lowercased_for_shell_comparison(self) -> None:
        body = cai.render_outputs(_probe(gh=True, auth=Auth.REJECTED, copilot=True))
        assert "github-cli-available=true" in body
        assert "copilot-available=true" in body
        assert "auth-valid=false" in body
        assert "reviews-enabled=false" in body
        assert "copilot-auth-status=rejected" in body
        assert "overall-status=unavailable" in body

    def test_binary_and_auth_are_separate_outputs(self) -> None:
        """Acceptance criterion: presence and validity cannot be conflated."""
        body = cai.render_outputs(_probe(gh=True, auth=Auth.ABSENT, copilot=True))
        assert "copilot-available=true" in body
        assert "auth-valid=false" in body

    def test_a_healthy_environment_enables_reviews(self) -> None:
        body = cai.render_outputs(_probe(gh=True, auth=Auth.VALID, copilot=True))
        assert "reviews-enabled=true" in body
        assert "copilot-auth-status=valid" in body
        assert "overall-status=ready" in body

    def test_the_summary_is_a_heredoc(self) -> None:
        probe = _probe(gh=True, auth=Auth.VALID, copilot=True)
        probe.summary = ["one", "two"]
        body = cai.render_outputs(probe)
        assert "summary<<EOF_SUMMARY\none\ntwo\nEOF_SUMMARY\n" in body

    def test_a_delimiter_in_the_value_cannot_close_its_own_heredoc(self) -> None:
        probe = _probe(gh=True, auth=Auth.VALID, copilot=True)
        probe.summary = ["EOF_SUMMARY", "injected=1"]
        body = cai.render_outputs(probe)
        assert body.count("EOF_SUMMARY\n") == 2
        assert "EOF_SUMMARY_ESCAPED" in body


class TestCli:
    def test_outputs_are_appended_to_github_output(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        out = tmp_path / "out.txt"
        out.write_text("pre-existing=1\n", encoding="utf-8")
        monkeypatch.setenv("GITHUB_OUTPUT", str(out))
        monkeypatch.setattr(
            cai, "run_probes", lambda: _probe(gh=True, auth=Auth.VALID, copilot=True)
        )
        assert cai.main([]) == 0
        text = out.read_text(encoding="utf-8")
        assert text.startswith("pre-existing=1\n")
        assert "overall-status=ready" in text

    def test_without_github_output_the_body_goes_to_stdout(
        self, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
        monkeypatch.setattr(
            cai, "run_probes", lambda: _probe(gh=False, auth=Auth.ABSENT, copilot=False)
        )
        assert cai.main([]) == 0
        assert "overall-status=unavailable" in capsys.readouterr().out

    def test_a_rejected_credential_still_exits_zero(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The probe is advisory: the caller decides, so it never fails the job."""
        monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
        monkeypatch.setattr(
            cai, "run_probes", lambda: _probe(gh=True, auth=Auth.REJECTED, copilot=True)
        )
        assert cai.main([]) == 0

    def test_the_health_block_is_printed(
        self, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
        probe = _probe(gh=True, auth=Auth.VALID, copilot=True)
        probe.summary = ["GitHub CLI: x"]
        monkeypatch.setattr(cai, "run_probes", lambda: probe)
        cai.main([])
        out = capsys.readouterr().out
        assert "=== Infrastructure Health Check ===" in out
        assert "  GitHub CLI: x" in out


class TestRunProbes:
    """End-to-end probe ordering, with every external call stubbed."""

    def test_a_healthy_runner_grades_ready(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(cai.shutil, "which", lambda _name: "/usr/bin/tool")
        monkeypatch.setattr(cai, "_first_line", lambda _argv: "1.0.0")
        monkeypatch.setenv(cai.COPILOT_TOKEN_ENV, "ghp_valid")
        monkeypatch.setattr(cai, "_run", lambda _argv, env=None: _ok("rjmurillo-bot"))
        probe = cai.run_probes()
        assert probe.status == "ready"
        assert "Overall: ready" in probe.summary

    def test_the_issue_4778_shape_grades_unavailable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Binary installed, credential refused: the run that shipped ten jobs."""
        monkeypatch.setattr(cai.shutil, "which", lambda _name: "/usr/bin/tool")
        monkeypatch.setattr(cai, "_first_line", lambda _argv: "1.0.63")
        monkeypatch.setenv(cai.COPILOT_TOKEN_ENV, "ghp_expired")
        monkeypatch.setattr(
            cai,
            "_run",
            lambda _argv, env=None: _fail(
                "Failed to fetch PAT user login (401): GitHub returned: Bad credentials"
            ),
        )
        probe = cai.run_probes()
        assert probe.copilot is True
        assert probe.reviews_enabled is False
        assert probe.status == "unavailable"


class TestFirstLine:
    def test_a_failing_command_returns_none(self) -> None:
        assert cai._first_line([sys.executable, "-c", "raise SystemExit(3)"]) is None

    def test_only_the_first_line_is_returned(self) -> None:
        argv = [sys.executable, "-c", "print('a'); print('b')"]
        assert cai._first_line(argv) == "a"

    def test_undecodable_bytes_do_not_crash(self) -> None:
        argv = [sys.executable, "-c", "import sys; sys.stdout.buffer.write(b'\\xff\\n')"]
        assert cai._first_line(argv) == "\ufffd"

    def test_a_missing_binary_is_not_an_exception(self) -> None:
        outcome = cai._run(["definitely-not-a-real-binary-4778"])
        assert outcome.returncode == 127


class TestWorkflowWiring:
    def test_the_action_accepts_a_runner_github_token(self) -> None:
        action = yaml.safe_load(ACTION.read_text(encoding="utf-8"))
        assert "github-token" in action["inputs"]

    def test_the_action_uses_runner_token_for_github_api_reads(self) -> None:
        action = yaml.safe_load(ACTION.read_text(encoding="utf-8"))
        step = action["runs"]["steps"][0]
        assert (
            step["env"]["GH_TOKEN"]
            == "${{ inputs.github-token || github.token || inputs.bot-pat }}"
        )

    def test_the_action_passes_the_copilot_token_for_the_auth_probe(self) -> None:
        action = yaml.safe_load(ACTION.read_text(encoding="utf-8"))
        step = action["runs"]["steps"][0]
        assert step["env"]["COPILOT_GITHUB_TOKEN"] == (
            "${{ inputs.copilot-token || inputs.bot-pat }}"
        )

    def test_the_action_exposes_presence_and_auth_separately(self) -> None:
        action = yaml.safe_load(ACTION.read_text(encoding="utf-8"))
        for name in ("copilot-available", "auth-valid", "copilot-auth-status", "reviews-enabled"):
            assert name in action["outputs"], name

    def test_the_action_invokes_the_script(self) -> None:
        assert "scripts/ci/check_agent_infrastructure.py" in ACTION.read_text(encoding="utf-8")

    def test_the_replaced_shell_is_gone(self) -> None:
        text = ACTION.read_text(encoding="utf-8")
        assert "SUMMARY_LINES" not in text
        assert "GITHUB_CLI_AVAILABLE=false" not in text
        assert "command -v copilot" not in text

    def test_the_action_is_clean_under_the_adr006_scanner(self) -> None:
        scanner = REPO_ROOT / "scripts" / "ci" / "adr006_run_block_scanner.py"
        completed = subprocess.run(
            [sys.executable, str(scanner), "--max", "999"],
            check=False,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            text=True,
            cwd=REPO_ROOT,
        )
        assert "check-agent-infrastructure" not in completed.stdout


class TestQualityGateWiring:
    """The workflow must follow the preflight result (issue #4778)."""

    @staticmethod
    def _workflow() -> dict:
        return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))

    @staticmethod
    def _review_steps(workflow: dict) -> list[dict]:
        steps = []
        for job in workflow["jobs"].values():
            for step in job.get("steps", []):
                if step.get("uses") == "./.github/actions/agent-review":
                    steps.append(step)
        return steps

    def test_all_ten_review_jobs_are_wired(self) -> None:
        assert len(self._review_steps(self._workflow())) == 10

    def test_every_review_follows_the_preflight_gate(self) -> None:
        expected = "${{ needs.infra-check.outputs.reviews-enabled == 'true' }}"
        for step in self._review_steps(self._workflow()):
            assert step["with"]["infra-ready"] == expected, step["name"]

    def test_no_review_gates_should_run_on_binary_presence(self) -> None:
        """The bug: binary presence decided whether ten model calls happened."""
        for step in self._review_steps(self._workflow()):
            assert "copilot-available" not in step["with"]["should-run"], step["name"]

    def test_should_run_carries_only_the_change_signal(self) -> None:
        expected = "${{ needs.check-changes.outputs.should-run-review == 'true' }}"
        for step in self._review_steps(self._workflow()):
            assert step["with"]["should-run"] == expected, step["name"]

    def test_the_infra_job_publishes_the_gate_output(self) -> None:
        outputs = self._workflow()["jobs"]["infra-check"]["outputs"]
        assert outputs["reviews-enabled"] == "${{ steps.infra.outputs.reviews-enabled }}"
        assert outputs["copilot-auth-status"] == "${{ steps.infra.outputs.copilot-auth-status }}"

    def test_the_misleading_skip_announcement_is_gone(self) -> None:
        """It claimed a skip while the caller launched all ten jobs anyway."""
        assert "Agent reviews requiring Copilot CLI will be skipped" not in WORKFLOW.read_text(
            encoding="utf-8"
        )


class TestAgentReviewInfraWiring:
    """An infrastructure skip must still upload an artifact (issue #4778)."""

    @staticmethod
    def _steps() -> dict[str, dict]:
        action = yaml.safe_load(AGENT_REVIEW_ACTION.read_text(encoding="utf-8"))
        return {step["name"]: step for step in action["runs"]["steps"]}

    def test_the_action_defaults_infra_ready_to_false(self) -> None:
        action = yaml.safe_load(AGENT_REVIEW_ACTION.read_text(encoding="utf-8"))
        assert action["inputs"]["infra-ready"]["default"] == "false"

    def test_the_model_call_requires_a_ready_preflight(self) -> None:
        steps = self._steps()
        review = next(name for name in steps if name.endswith("Review"))
        assert "inputs.infra-ready == 'true'" in steps[review]["if"]

    def test_saving_and_uploading_do_not_require_a_ready_preflight(self) -> None:
        steps = self._steps()
        for name in ("Save review results", "Upload review results"):
            assert steps[name]["if"] == "always() && inputs.should-run == 'true'", name

    def test_outcome_steps_receive_the_preflight_result(self) -> None:
        steps = self._steps()
        expected = "${{ steps.cache.outputs.cache-hit == 'true' && 'true' || inputs.infra-ready }}"
        for name in (
            "Save review results",
            "Generate step summary",
            "Check verdict and fail if needed",
        ):
            assert steps[name]["env"]["INFRA_READY"] == expected, name


class TestAiReviewActionAuthWiring:
    def test_read_only_gh_steps_use_runner_token_before_bot_pat(self) -> None:
        action = yaml.safe_load(AI_REVIEW_ACTION.read_text(encoding="utf-8"))
        steps = {step["name"]: step for step in action["runs"]["steps"]}
        expected = "${{ inputs.github-token || github.token || inputs.bot-pat }}"

        for name in (
            "Verify GitHub authentication",
            "Diagnose Copilot CLI",
            "Build context",
            "Invoke Copilot CLI (with retry for infrastructure failures)",
        ):
            assert steps[name]["env"]["GH_TOKEN"] == expected

    def test_post_analysis_writes_still_use_bot_pat(self) -> None:
        action = yaml.safe_load(AI_REVIEW_ACTION.read_text(encoding="utf-8"))
        steps = {step["name"]: step for step in action["runs"]["steps"]}
        assert steps["Execute post-analysis script"]["env"]["GH_TOKEN"] == "${{ inputs.bot-pat }}"
