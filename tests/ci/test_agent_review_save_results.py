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
