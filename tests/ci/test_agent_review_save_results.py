"""Tests for scripts/ci/agent_review_save_results.py."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from scripts.ci.agent_review_save_results import _ALLOWED_AGENTS, main, run


class TestAllowlist:
    def test_has_10_agents(self) -> None:
        assert len(_ALLOWED_AGENTS) == 10

    def test_all_expected_agents_present(self) -> None:
        expected = {
            "security",
            "qa",
            "analyst",
            "architect",
            "devops",
            "roadmap",
            "reliability",
            "observability",
            "agent-safety",
            "decision-rigor",
        }
        assert _ALLOWED_AGENTS == expected


class TestRun:
    def test_invalid_agent_returns_1(self) -> None:
        with patch.dict(os.environ, {"AGENT": "unknown-bot"}):
            assert run() == 1

    def test_valid_agent_writes_files(self, tmp_path: Path) -> None:
        env = {
            "AGENT": "security",
            "VERDICT": "PASS",
            "FINDINGS": "No issues",
            "INFRASTRUCTURE_FAILURE": "false",
            "RETRY_COUNT": "0",
            "CACHE_HIT": "false",
        }
        original_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            with patch.dict(os.environ, env):
                rc = run()
        finally:
            os.chdir(original_cwd)
        assert rc == 0
        base = tmp_path / "ai-review-results"
        assert (base / "security-verdict.txt").read_text() == "PASS"
        assert (base / "security-findings.txt").read_text() == "No issues"
        assert (base / "security-infrastructure-failure.txt").read_text() == "false"
        assert (base / "security-retry-count.txt").read_text() == "0"

    def test_empty_verdict_defaults_to_needs_review(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        env = {
            "AGENT": "qa",
            "VERDICT": "",
            "FINDINGS": "something",
            "INFRASTRUCTURE_FAILURE": "",
            "INFRA_READY": "true",
            "RETRY_COUNT": "0",
            "CACHE_HIT": "false",
        }
        original_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            with patch.dict(os.environ, env):
                run()
        finally:
            os.chdir(original_cwd)
        assert "NEEDS_REVIEW" in (tmp_path / "ai-review-results" / "qa-verdict.txt").read_text()
        assert "::warning::" in capsys.readouterr().out

    def test_empty_verdict_and_findings_sets_infra_failure(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        env = {
            "AGENT": "analyst",
            "VERDICT": "",
            "FINDINGS": "",
            "INFRASTRUCTURE_FAILURE": "",
            "INFRA_READY": "true",
            "RETRY_COUNT": "0",
            "CACHE_HIT": "",
        }
        original_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            with patch.dict(os.environ, env):
                run()
        finally:
            os.chdir(original_cwd)
        infra = (tmp_path / "ai-review-results" / "analyst-infrastructure-failure.txt").read_text()
        assert infra == "true"

    def test_cache_hit_message_printed(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        env = {
            "AGENT": "devops",
            "VERDICT": "PASS",
            "FINDINGS": "ok",
            "INFRASTRUCTURE_FAILURE": "false",
            "RETRY_COUNT": "0",
            "CACHE_HIT": "true",
        }
        original_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            with patch.dict(os.environ, env):
                run()
        finally:
            os.chdir(original_cwd)
        assert "cached" in capsys.readouterr().out.lower()

    def test_all_10_agents_accepted(self, tmp_path: Path) -> None:
        for agent in _ALLOWED_AGENTS:
            env = {
                "AGENT": agent,
                "VERDICT": "PASS",
                "FINDINGS": "ok",
                "INFRASTRUCTURE_FAILURE": "false",
                "RETRY_COUNT": "0",
                "CACHE_HIT": "false",
            }
            original_cwd = os.getcwd()
            work = tmp_path / agent
            work.mkdir()
            os.chdir(work)
            try:
                with patch.dict(os.environ, env):
                    rc = run()
            finally:
                os.chdir(original_cwd)
            assert rc == 0, f"Agent {agent} should be accepted"


class TestMain:
    def test_main_delegates(self) -> None:
        with patch("scripts.ci.agent_review_save_results.run", return_value=0):
            assert main() == 0


class TestInfrastructureSkipArtifacts:
    """An infrastructure skip must still leave a complete artifact (#4778).

    ``AI Quality Gate Results`` downloads these files and
    ``validate_artifact_download.py`` exits 1 when any ``<agent>-verdict.txt`` is
    missing, so a silent skip crashes aggregation before it can post a report.
    """

    @staticmethod
    def _run_in(tmp_path: Path, env: dict[str, str]) -> None:
        original_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            with patch.dict(os.environ, env):
                assert run() == 0
        finally:
            os.chdir(original_cwd)

    def _skip_env(self, agent: str = "security") -> dict[str, str]:
        return {
            "AGENT": agent,
            "VERDICT": "",
            "FINDINGS": "",
            "INFRASTRUCTURE_FAILURE": "",
            "INFRA_READY": "false",
            "RETRY_COUNT": "0",
            "CACHE_HIT": "false",
        }

    def test_the_skip_writes_a_did_not_run_verdict(self, tmp_path: Path) -> None:
        self._run_in(tmp_path, self._skip_env())
        base = tmp_path / "ai-review-results"
        assert (base / "security-verdict.txt").read_text() == "DID_NOT_RUN"
        assert (base / "security-infrastructure-failure.txt").read_text() == "true"

    def test_the_skip_writes_every_file_the_aggregate_reads(self, tmp_path: Path) -> None:
        self._run_in(tmp_path, self._skip_env("qa"))
        base = tmp_path / "ai-review-results"
        for suffix in (
            "verdict.txt",
            "findings.txt",
            "infrastructure-failure.txt",
            "retry-count.txt",
        ):
            assert (base / f"qa-{suffix}").exists(), suffix

    def test_the_findings_say_why_rather_than_staying_empty(self, tmp_path: Path) -> None:
        self._run_in(tmp_path, self._skip_env("devops"))
        findings = (tmp_path / "ai-review-results" / "devops-findings.txt").read_text()
        assert "did not execute" in findings

    def test_a_missing_preflight_output_fails_closed(self, tmp_path: Path) -> None:
        env = self._skip_env("analyst")
        del env["INFRA_READY"]
        self._run_in(tmp_path, env)
        base = tmp_path / "ai-review-results"
        assert (base / "analyst-verdict.txt").read_text() == "DID_NOT_RUN"

    def test_a_cached_verdict_survives_an_unavailable_preflight(self, tmp_path: Path) -> None:
        env = self._skip_env("architect")
        env.update({"VERDICT": "PASS", "FINDINGS": "cached", "CACHE_HIT": "true"})
        self._run_in(tmp_path, env)
        base = tmp_path / "ai-review-results"
        assert (base / "architect-verdict.txt").read_text() == "PASS"

    def test_every_agent_produces_a_downloadable_artifact_on_skip(
        self, tmp_path: Path
    ) -> None:
        """The aggregate needs all ten, so no agent may go silent."""
        results = tmp_path / "results"
        results.mkdir()
        for agent in sorted(_ALLOWED_AGENTS):
            work = tmp_path / f"work-{agent}"
            work.mkdir()
            self._run_in(work, self._skip_env(agent))
            for produced in (work / "ai-review-results").iterdir():
                (results / produced.name).write_text(
                    produced.read_text(encoding="utf-8"), encoding="utf-8"
                )

        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "quality_gate"))
        from scripts.quality_gate.validate_artifact_download import find_missing

        assert find_missing(results) == []
