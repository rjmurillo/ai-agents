#!/usr/bin/env python3
"""Tests for collect_metrics module."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)

from claude_skills_import import import_skill_script

mod = import_skill_script(".claude/skills/metrics/collect_metrics.py")
find_agents_in_text = mod.find_agents_in_text
get_commit_type = mod.get_commit_type
is_infrastructure_file = mod.is_infrastructure_file
get_metrics = mod.get_metrics
format_summary = mod.format_summary
format_markdown = mod.format_markdown
main = mod.main


class TestFindAgentsInText:
    """Tests for find_agents_in_text function."""

    def test_finds_agent_names(self) -> None:
        result = find_agents_in_text("orchestrator agent reviewed this")
        assert "orchestrator" in result

    def test_finds_reviewed_by_pattern(self) -> None:
        result = find_agents_in_text("reviewed by: security")
        assert "security" in result

    def test_finds_agent_prefix(self) -> None:
        result = find_agents_in_text("agent: architect")
        assert "architect" in result

    def test_finds_bracket_pattern(self) -> None:
        result = find_agents_in_text("[qa-agent] reviewed")
        assert "qa" in result

    def test_returns_empty_for_no_agents(self) -> None:
        result = find_agents_in_text("normal commit message")
        assert result == []

    def test_case_insensitive(self) -> None:
        result = find_agents_in_text("ORCHESTRATOR reviewed this")
        assert "orchestrator" in result

    def test_finds_multiple_agents(self) -> None:
        result = find_agents_in_text("orchestrator and security agents reviewed")
        assert "orchestrator" in result
        assert "security" in result


class TestGetCommitType:
    """Tests for get_commit_type function."""

    def test_detects_feat(self) -> None:
        assert get_commit_type("feat: add new feature") == "feature"

    def test_detects_fix(self) -> None:
        assert get_commit_type("fix: resolve bug") == "fix"

    def test_detects_docs(self) -> None:
        assert get_commit_type("docs: update README") == "docs"

    def test_detects_refactor(self) -> None:
        assert get_commit_type("refactor: improve code") == "refactor"

    def test_detects_test(self) -> None:
        assert get_commit_type("test: add unit tests") == "test"

    def test_detects_chore(self) -> None:
        assert get_commit_type("chore: update deps") == "chore"

    def test_detects_ci(self) -> None:
        assert get_commit_type("ci: update workflow") == "ci"

    def test_detects_scoped_commit(self) -> None:
        assert get_commit_type("feat(auth): add login") == "feature"

    def test_returns_other_for_unknown(self) -> None:
        assert get_commit_type("random commit message") == "other"


class TestIsInfrastructureFile:
    """Tests for is_infrastructure_file function."""

    def test_detects_workflow(self) -> None:
        assert is_infrastructure_file(".github/workflows/ci.yml") is True

    def test_detects_actions(self) -> None:
        assert is_infrastructure_file(".github/actions/setup/action.yml") is True

    def test_detects_githooks(self) -> None:
        assert is_infrastructure_file(".githooks/pre-commit") is True

    def test_detects_build(self) -> None:
        assert is_infrastructure_file("build/deploy.sh") is True

    def test_detects_scripts(self) -> None:
        assert is_infrastructure_file("scripts/setup.py") is True

    def test_detects_dockerfile(self) -> None:
        assert is_infrastructure_file("Dockerfile") is True

    def test_detects_terraform(self) -> None:
        assert is_infrastructure_file("infra/main.tf") is True

    def test_detects_agents(self) -> None:
        assert is_infrastructure_file(".agents/config.md") is True

    def test_returns_false_for_source(self) -> None:
        assert is_infrastructure_file("src/app.py") is False


class TestGetMetrics:
    """Tests for get_metrics function."""

    @pytest.fixture
    def git_repo(self, tmp_path: Path) -> Path:
        subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True, check=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=str(tmp_path), capture_output=True, check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=str(tmp_path), capture_output=True, check=True,
        )
        (tmp_path / "README.md").write_text("init")
        subprocess.run(["git", "add", "."], cwd=str(tmp_path), capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "feat: initial commit by orchestrator agent"],
            cwd=str(tmp_path), capture_output=True, check=True,
        )
        return tmp_path

    def test_returns_metrics_structure(self, git_repo: Path) -> None:
        metrics = get_metrics(str(git_repo), 30)
        assert "period" in metrics
        assert "metric_1_invocation_rate" in metrics
        assert "metric_2_coverage" in metrics
        assert "metric_4_infrastructure_review" in metrics
        assert "metric_5_distribution" in metrics

    def test_period_contains_dates(self, git_repo: Path) -> None:
        metrics = get_metrics(str(git_repo), 30)
        assert "start_date" in metrics["period"]
        assert "end_date" in metrics["period"]
        assert "total_commits" in metrics["period"]

    def test_empty_repo_returns_zeros(self, tmp_path: Path) -> None:
        subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True, check=True)
        metrics = get_metrics(str(tmp_path), 30)
        assert metrics["period"]["total_commits"] == 0
        assert metrics["metric_1_invocation_rate"]["total_invocations"] == 0


class TestFormatSummary:
    """Tests for format_summary function."""

    def test_contains_header(self) -> None:
        metrics = _make_test_metrics()
        result = format_summary(metrics)
        assert "AGENT METRICS SUMMARY" in result

    def test_contains_period(self) -> None:
        metrics = _make_test_metrics()
        result = format_summary(metrics)
        assert "2024-01-01" in result

    def test_contains_coverage(self) -> None:
        metrics = _make_test_metrics()
        result = format_summary(metrics)
        assert "AGENT COVERAGE" in result


class TestFormatMarkdown:
    """Tests for format_markdown function."""

    def test_contains_markdown_header(self) -> None:
        metrics = _make_test_metrics()
        result = format_markdown(metrics)
        assert "# Agent Metrics Report" in result

    def test_contains_table(self) -> None:
        metrics = _make_test_metrics()
        result = format_markdown(metrics)
        assert "|" in result
        assert "Agent" in result

    def test_contains_generated_by(self) -> None:
        metrics = _make_test_metrics()
        result = format_markdown(metrics)
        assert "collect_metrics.py" in result


class TestMain:
    """Tests for main entry point."""

    def test_returns_1_for_missing_path(self) -> None:
        with patch("sys.argv", ["collect_metrics.py", "--repo-path", "/nonexistent/path"]):
            result = main()
        assert result == 1

    def test_returns_1_for_non_git_repo(self, tmp_path: Path) -> None:
        with patch("sys.argv", ["collect_metrics.py", "--repo-path", str(tmp_path)]):
            result = main()
        assert result == 1

    def test_json_output(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True, check=True)
        argv = ["collect_metrics.py", "--repo-path", str(tmp_path), "--output", "json"]
        with patch("sys.argv", argv):
            result = main()
        assert result == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "period" in data


def _make_test_metrics() -> dict:
    return {
        "period": {
            "days": 30,
            "start_date": "2024-01-01",
            "end_date": "2024-01-31",
            "total_commits": 10,
        },
        "metric_1_invocation_rate": {
            "agents": {"orchestrator": {"count": 5, "rate": 50.0}},
            "total_invocations": 10,
        },
        "metric_2_coverage": {
            "total_commits": 10,
            "commits_with_agent": 5,
            "coverage_rate": 50.0,
            "target": 50,
            "by_type": {"feature": {"total": 5, "with_agent": 3, "rate": 60.0}},
            "status": "on_track",
        },
        "metric_4_infrastructure_review": {
            "infrastructure_commits": 2,
            "with_security_review": 2,
            "review_rate": 100.0,
            "target": 100,
            "status": "on_track",
        },
        "metric_5_distribution": {"orchestrator": 50.0},
    }
