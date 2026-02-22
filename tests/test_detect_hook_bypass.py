"""Tests for detect_hook_bypass module.

Verifies the hook bypass detection heuristics used for CI audit trail.
Related: Issue #664 (--no-verify bypass logging)
"""

from __future__ import annotations

import json
from dataclasses import asdict

from scripts.detect_hook_bypass import (
    AuditReport,
    BypassIndicator,
    check_agents_without_session,
    check_bash_scripts_added,
    check_handoff_modified,
    format_report,
)


class TestBypassIndicator:
    """Tests for the BypassIndicator dataclass."""

    def test_fields_stored(self) -> None:
        indicator = BypassIndicator(
            commit_sha="abc123",
            commit_message="test commit",
            indicator_type="test-type",
            details="test details",
        )
        assert indicator.commit_sha == "abc123"
        assert indicator.commit_message == "test commit"
        assert indicator.indicator_type == "test-type"
        assert indicator.details == "test details"

    def test_serializable_to_json(self) -> None:
        indicator = BypassIndicator(
            commit_sha="abc123",
            commit_message="test",
            indicator_type="test",
            details="details",
        )
        result = json.dumps(asdict(indicator))
        assert '"commit_sha": "abc123"' in result


class TestAuditReport:
    """Tests for the AuditReport dataclass."""

    def test_has_indicators_false_when_empty(self) -> None:
        report = AuditReport(
            timestamp="2026-01-01T00:00:00Z",
            branch="feat/test",
            base_ref="origin/main",
            total_commits=5,
        )
        assert report.has_indicators is False

    def test_has_indicators_true_with_indicators(self) -> None:
        report = AuditReport(
            timestamp="2026-01-01T00:00:00Z",
            branch="feat/test",
            base_ref="origin/main",
            total_commits=5,
            bypass_indicators=[
                BypassIndicator("sha1", "msg", "type", "details"),
            ],
        )
        assert report.has_indicators is True

    def test_serializable_to_json(self) -> None:
        report = AuditReport(
            timestamp="2026-01-01T00:00:00Z",
            branch="feat/test",
            base_ref="origin/main",
            total_commits=3,
        )
        result = json.loads(json.dumps(asdict(report)))
        assert result["total_commits"] == 3
        assert result["bypass_indicators"] == []


class TestCheckAgentsWithoutSession:
    """Tests for check_agents_without_session."""

    def test_returns_none_for_non_agents_files(self) -> None:
        result = check_agents_without_session(
            "sha1",
            "update readme",
            ["README.md", "scripts/foo.py"],
        )
        assert result is None

    def test_returns_none_when_session_log_present(self) -> None:
        result = check_agents_without_session(
            "sha1",
            "session work",
            [
                ".agents/HANDOFF.md",
                ".agents/sessions/2026-01-01-session-01.json",
            ],
        )
        assert result is None

    def test_returns_indicator_when_agents_without_session(self) -> None:
        result = check_agents_without_session(
            "sha1",
            "modify agents",
            [".agents/planning/plan.md"],
        )
        assert result is not None
        assert result.indicator_type == "agents-without-session"

    def test_session_log_must_be_json(self) -> None:
        result = check_agents_without_session(
            "sha1",
            "old format",
            [
                ".agents/planning/plan.md",
                ".agents/sessions/2026-01-01-session-01.md",
            ],
        )
        assert result is not None


class TestCheckHandoffModified:
    """Tests for check_handoff_modified."""

    def test_returns_none_when_handoff_not_in_files(self) -> None:
        result = check_handoff_modified(
            "sha1",
            "normal commit",
            ["README.md", ".agents/sessions/log.json"],
        )
        assert result is None

    def test_returns_indicator_when_handoff_modified(self) -> None:
        result = check_handoff_modified(
            "sha1",
            "update handoff",
            [".agents/HANDOFF.md"],
        )
        assert result is not None
        assert result.indicator_type == "handoff-modified"


class TestCheckBashScriptsAdded:
    """Tests for check_bash_scripts_added."""

    def test_returns_none_for_python_scripts(self) -> None:
        result = check_bash_scripts_added(
            "sha1",
            "add script",
            [".github/scripts/validate.py"],
        )
        assert result is None

    def test_returns_none_for_bash_outside_github(self) -> None:
        result = check_bash_scripts_added(
            "sha1",
            "add hook",
            ["scripts/hooks/pre-push"],
        )
        assert result is None

    def test_returns_indicator_for_bash_in_github_scripts(self) -> None:
        result = check_bash_scripts_added(
            "sha1",
            "add bash script",
            [".github/scripts/deploy.sh"],
        )
        assert result is not None
        assert result.indicator_type == "bash-script-added"

    def test_detects_bash_extension(self) -> None:
        result = check_bash_scripts_added(
            "sha1",
            "add script",
            [".github/scripts/run.bash"],
        )
        assert result is not None


class TestFormatReport:
    """Tests for format_report."""

    def test_clean_report(self) -> None:
        report = AuditReport(
            timestamp="2026-01-01T00:00:00Z",
            branch="feat/test",
            base_ref="origin/main",
            total_commits=3,
        )
        output = format_report(report)
        assert "No bypass indicators detected" in output
        assert "Commits analyzed: 3" in output

    def test_report_with_indicators(self) -> None:
        report = AuditReport(
            timestamp="2026-01-01T00:00:00Z",
            branch="feat/test",
            base_ref="origin/main",
            total_commits=5,
            bypass_indicators=[
                BypassIndicator(
                    "abc12345full",
                    "bad commit",
                    "handoff-modified",
                    "HANDOFF.md modified",
                ),
            ],
        )
        output = format_report(report)
        assert "Bypass indicators: 1" in output
        assert "abc12345" in output
        assert "handoff-modified" in output
