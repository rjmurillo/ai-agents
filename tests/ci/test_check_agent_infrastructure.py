"""Tests for ``scripts/ci/check_agent_infrastructure.py`` (issue #3527)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from scripts.ci import check_agent_infrastructure as cai

REPO_ROOT = Path(__file__).resolve().parents[2]

ACTION = REPO_ROOT / ".github" / "actions" / "check-agent-infrastructure" / "action.yml"
AI_REVIEW_ACTION = REPO_ROOT / ".github" / "actions" / "ai-review" / "action.yml"
AGENT_REVIEW_ACTION = REPO_ROOT / ".github" / "actions" / "agent-review" / "action.yml"
AI_PR_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ai-pr-quality-gate.yml"
BUILD_AI_REVIEW_CONTEXT = REPO_ROOT / "scripts" / "ci" / "build_ai_review_context.py"
SESSION_PROTOCOL_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ai-session-protocol.yml"
SHARED_PAT_CANDIDATE_WORKFLOWS = (
    REPO_ROOT / ".github" / "workflows" / "ai-spec-validation.yml",
    REPO_ROOT / ".github" / "workflows" / "ai-metrics-analysis.yml",
    REPO_ROOT / ".github" / "workflows" / "pr-maintenance.yml",
    REPO_ROOT / ".github" / "workflows" / "ai-issue-triage.yml",
)


def _probe(*, gh: bool, auth: bool, copilot: bool) -> cai.Probe:
    return cai.Probe(github_cli=gh, auth_valid=auth, copilot=copilot)


class TestStatusGrading:
    """The three-way grade is the only consumer-visible decision."""

    def test_everything_present_is_ready(self) -> None:
        assert _probe(gh=True, auth=True, copilot=True).status == "ready"

    def test_missing_copilot_is_degraded(self) -> None:
        assert _probe(gh=True, auth=True, copilot=False).status == "degraded"

    def test_missing_auth_is_unavailable_even_with_copilot(self) -> None:
        assert _probe(gh=True, auth=False, copilot=True).status == "unavailable"

    def test_missing_cli_is_unavailable(self) -> None:
        assert _probe(gh=False, auth=False, copilot=False).status == "unavailable"

    def test_auth_without_cli_is_unavailable(self) -> None:
        assert _probe(gh=False, auth=True, copilot=True).status == "unavailable"


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


class TestAuthProbe:
    def test_auth_is_skipped_without_the_cli(self) -> None:
        probe = cai.Probe(github_cli=False)
        cai._probe_auth(probe)
        assert probe.auth_valid is False
        assert "Authentication: skipped (no gh CLI)" in probe.summary
        assert probe.annotations == []

    def test_a_failed_api_call_is_a_warning_not_a_crash(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(cai, "_first_line", lambda _argv: None)
        probe = cai.Probe(github_cli=True)
        cai._probe_auth(probe)
        assert probe.auth_valid is False
        assert "Authentication: FAILED" in probe.summary
        assert all("bot-pat" not in annotation for annotation in probe.annotations)

    def test_a_login_marks_auth_valid(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(cai, "_first_line", lambda _argv: "octocat")
        probe = cai.Probe(github_cli=True)
        cai._probe_auth(probe)
        assert probe.auth_valid is True
        assert "Authentication: valid (user: octocat)" in probe.summary


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


class TestRenderOutputs:
    def test_booleans_are_lowercased_for_shell_comparison(self) -> None:
        body = cai.render_outputs(_probe(gh=True, auth=False, copilot=True))
        assert "github-cli-available=true" in body
        assert "auth-valid=false" in body
        assert "overall-status=unavailable" in body

    def test_the_summary_is_a_heredoc(self) -> None:
        probe = _probe(gh=True, auth=True, copilot=True)
        probe.summary = ["one", "two"]
        body = cai.render_outputs(probe)
        assert "summary<<EOF_SUMMARY\none\ntwo\nEOF_SUMMARY\n" in body

    def test_a_delimiter_in_the_value_cannot_close_its_own_heredoc(self) -> None:
        probe = _probe(gh=True, auth=True, copilot=True)
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
        monkeypatch.setattr(cai, "run_probes", lambda: _probe(gh=True, auth=True, copilot=True))
        assert cai.main([]) == 0
        text = out.read_text(encoding="utf-8")
        assert text.startswith("pre-existing=1\n")
        assert "overall-status=ready" in text

    def test_without_github_output_the_body_goes_to_stdout(
        self, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
        monkeypatch.setattr(cai, "run_probes", lambda: _probe(gh=False, auth=False, copilot=False))
        assert cai.main([]) == 0
        assert "overall-status=unavailable" in capsys.readouterr().out

    def test_a_degraded_environment_still_exits_zero(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
        monkeypatch.setattr(cai, "run_probes", lambda: _probe(gh=True, auth=True, copilot=False))
        assert cai.main([]) == 0

    def test_the_health_block_is_printed(
        self, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
        probe = _probe(gh=True, auth=True, copilot=True)
        probe.summary = ["GitHub CLI: x"]
        monkeypatch.setattr(cai, "run_probes", lambda: probe)
        cai.main([])
        out = capsys.readouterr().out
        assert "=== Infrastructure Health Check ===" in out
        assert "  GitHub CLI: x" in out


class TestFirstLine:
    def test_a_failing_command_returns_none(self) -> None:
        assert cai._first_line([sys.executable, "-c", "raise SystemExit(3)"]) is None

    def test_only_the_first_line_is_returned(self) -> None:
        argv = [sys.executable, "-c", "print('a'); print('b')"]
        assert cai._first_line(argv) == "a"

    def test_undecodable_bytes_do_not_crash(self) -> None:
        argv = [sys.executable, "-c", "import sys; sys.stdout.buffer.write(b'\\xff\\n')"]
        assert cai._first_line(argv) == "\ufffd"


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


class TestAgentReviewAuthWiring:
    def test_agent_review_accepts_and_forwards_the_runner_token(self) -> None:
        action = yaml.safe_load(AGENT_REVIEW_ACTION.read_text(encoding="utf-8"))
        assert "github-token" in action["inputs"]

        steps = {step["name"]: step for step in action["runs"]["steps"]}
        review_with = steps["${{ inputs.emoji }} ${{ inputs.agent }} Review"]["with"]
        assert review_with["github-token"] == "${{ inputs.github-token }}"

    def test_quality_gate_jobs_pass_the_runner_token_to_agent_review(self) -> None:
        workflow = yaml.safe_load(AI_PR_WORKFLOW.read_text(encoding="utf-8"))
        review_steps = []
        for job in workflow["jobs"].values():
            for step in job.get("steps", []):
                if step.get("uses") == "./.github/actions/agent-review":
                    review_steps.append(step)

        assert len(review_steps) == 10
        for step in review_steps:
            assert step["with"]["github-token"] == "${{ secrets.GITHUB_TOKEN }}"


class TestSharedPatCandidateWorkflows:
    @pytest.mark.parametrize("workflow_path", SHARED_PAT_CANDIDATE_WORKFLOWS)
    def test_repository_local_gh_calls_use_runner_token(self, workflow_path: Path) -> None:
        workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))

        assert self._find_values(workflow, "secrets.BOT_PAT") == []

    @pytest.mark.parametrize("workflow_path", SHARED_PAT_CANDIDATE_WORKFLOWS)
    def test_ai_review_calls_receive_runner_token(self, workflow_path: Path) -> None:
        workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
        review_steps = [
            step
            for job in workflow["jobs"].values()
            for step in job.get("steps", [])
            if step.get("uses") == "./.github/actions/ai-review"
        ]

        for step in review_steps:
            assert step["with"]["bot-pat"] == "${{ github.token }}"
            assert step["with"]["github-token"] == "${{ github.token }}"

    def _find_values(self, value: object, needle: str) -> list[str]:
        if isinstance(value, str):
            return [value] if needle in value else []
        if isinstance(value, list):
            return [match for item in value for match in self._find_values(item, needle)]
        if isinstance(value, dict):
            return [
                match
                for item in value.values()
                for match in self._find_values(item, needle)
            ]
        return []

    def test_session_protocol_gh_consumers_use_runner_token(self) -> None:
        workflow = yaml.safe_load(SESSION_PROTOCOL_WORKFLOW.read_text(encoding="utf-8"))
        gh_token_steps = [
            step
            for job in workflow["jobs"].values()
            for step in job.get("steps", [])
            if (step.get("env") or {}).get("GH_TOKEN")
        ]

        assert len(gh_token_steps) == 2
        for step in gh_token_steps:
            assert step["env"]["GH_TOKEN"] == "${{ github.token }}"


class TestBuildAiReviewContextAuthBoundary:
    def test_context_builder_passes_gh_token_to_gh_boundary(self) -> None:
        self._assert_context_builder_token(self._scratch_dir("with-token"), token="runner-token")

    def test_context_builder_fails_when_gh_token_is_absent(self) -> None:
        with pytest.raises(AssertionError):
            self._assert_context_builder_token(self._scratch_dir("without-token"), token=None)

    def _assert_context_builder_token(self, tmp_path: Path, *, token: str | None) -> None:
        try:
            completed, calls_path = self._run_context_builder(tmp_path, token=token)

            if token is not None:
                assert completed.returncode == 0, completed.stderr
            calls = yaml.safe_load(calls_path.read_text(encoding="utf-8"))
            assert [call["gh_token"] for call in calls] == ["runner-token", "runner-token"]
        finally:
            shutil.rmtree(tmp_path, ignore_errors=True)

    def _scratch_dir(self, name: str) -> Path:
        path = REPO_ROOT / ".pytest_tmp" / "agent-review-auth-boundary" / name
        if path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True)
        return path

    def _run_context_builder(
        self,
        tmp_path: Path,
        *,
        token: str | None,
    ) -> tuple[subprocess.CompletedProcess[str], Path]:
        fake_bin = tmp_path / "bin"
        fake_bin.mkdir()
        calls_path = tmp_path / "gh-calls.yml"
        fake_gh = fake_bin / "gh"
        fake_gh.write_text(
            f"""#!{sys.executable}
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

calls_path = Path({str(calls_path)!r})
args = sys.argv[1:]
records = []
if calls_path.exists():
    records = json.loads(calls_path.read_text(encoding="utf-8"))
records.append({{"args": args, "gh_token": os.environ.get("GH_TOKEN", "")}})
calls_path.write_text(json.dumps(records), encoding="utf-8")

if not os.environ.get("GH_TOKEN"):
    print("missing GH_TOKEN", file=sys.stderr)
    raise SystemExit(7)

if args == ["api", "repos/rjmurillo/ai-agents/pulls/123"]:
    print(json.dumps({{"number": 123, "title": "Token test", "body": "body"}}))
    raise SystemExit(0)

if args == ["pr", "diff", "123", "--repo", "rjmurillo/ai-agents"]:
    print("diff --git a/file.txt b/file.txt")
    print("+changed")
    raise SystemExit(0)

print(f"unexpected gh args: {{args!r}}", file=sys.stderr)
raise SystemExit(9)
""",
            encoding="utf-8",
        )
        fake_gh.chmod(0o755)

        env = {
            "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
            "PYTHONPATH": str(REPO_ROOT),
            "CONTEXT_TYPE": "pr-diff",
            "PR_NUMBER": "123",
            "GITHUB_REPOSITORY": "rjmurillo/ai-agents",
            "MAX_DIFF_LINES": "500",
            "GITHUB_OUTPUT": str(tmp_path / "github-output.txt"),
            "RUNNER_TEMP": str(tmp_path / "runner-temp"),
        }
        if token is not None:
            env["GH_TOKEN"] = token

        completed = subprocess.run(
            [sys.executable, str(BUILD_AI_REVIEW_CONTEXT)],
            check=False,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            text=True,
            cwd=REPO_ROOT,
            env=env,
        )
        return completed, calls_path
