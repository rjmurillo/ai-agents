"""Tests for scripts/velocity_accelerator.py."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from scripts.velocity_accelerator import (
    EventType,
    Opportunity,
    OpportunityType,
    _word_match,
    detect_artifact_changes,
    detect_opportunities,
    extract_todos_from_diff,
    format_summary,
    main,
    process_issue_event,
    process_issue_opened,
    score_issue_complexity,
    suggest_agents,
)


class TestEventType:
    """Test EventType enum."""

    def test_values(self) -> None:
        assert EventType.PR_MERGED == "pull_request_merged"
        assert EventType.ISSUE_OPENED == "issue_opened"
        assert EventType.ISSUE_LABELED == "issue_labeled"

    def test_is_str(self) -> None:
        assert isinstance(EventType.PR_MERGED, str)

    def test_no_scheduled_type(self) -> None:
        """SCHEDULED was removed since the schedule trigger is not implemented."""
        assert not hasattr(EventType, "SCHEDULED")


class TestOpportunityType:
    """Test OpportunityType enum."""

    def test_values(self) -> None:
        assert OpportunityType.TODO_FOLLOWUP == "todo_followup"
        assert OpportunityType.FIXME_FOLLOWUP == "fixme_followup"

    def test_no_stale_issue_type(self) -> None:
        """STALE_ISSUE was removed since it was never produced."""
        assert not hasattr(OpportunityType, "STALE_ISSUE")


class TestOpportunity:
    """Test Opportunity dataclass."""

    def test_defaults(self) -> None:
        opp = Opportunity(
            opportunity_type=OpportunityType.TODO_FOLLOWUP,
            title="Test",
            description="Test desc",
            source_event=EventType.PR_MERGED,
            source_ref="PR #1",
        )
        assert opp.suggested_agent == ""
        assert opp.priority == "medium"
        assert opp.metadata == {}


class TestWordMatch:
    """Test word boundary matching helper."""

    def test_exact_match(self) -> None:
        assert _word_match("fix", "fix the bug")

    def test_no_substring_match(self) -> None:
        assert not _word_match("fix", "prefix the value")

    def test_no_suffix_match(self) -> None:
        assert not _word_match("fix", "fixup the code")

    def test_compound_keyword(self) -> None:
        assert _word_match("breaking change", "this is a breaking change")

    def test_case_sensitive(self) -> None:
        # _word_match itself is case-sensitive; callers lower() the text
        assert not _word_match("fix", "FIX the bug")

    def test_ci_no_false_positive(self) -> None:
        assert not _word_match("ci", "critical infrastructure")

    def test_cd_no_false_positive(self) -> None:
        assert not _word_match("cd", "credential store")


class TestExtractTodosFromDiff:
    """Test TODO/FIXME extraction from PR diffs."""

    def test_detects_todo(self) -> None:
        diff = (
            "diff --git a/src/main.py b/src/main.py\n"
            "+# TODO: Implement error handling\n"
        )
        result = extract_todos_from_diff(diff, 42)
        assert len(result) == 1
        assert result[0].opportunity_type == OpportunityType.TODO_FOLLOWUP
        assert "src/main.py" in result[0].title
        assert result[0].metadata["tag"] == "TODO"
        assert result[0].metadata["pr_number"] == "42"

    def test_detects_fixme(self) -> None:
        diff = (
            "diff --git a/src/api.py b/src/api.py\n"
            "+  # FIXME: This is a temporary workaround\n"
        )
        result = extract_todos_from_diff(diff, 10)
        assert len(result) == 1
        assert result[0].opportunity_type == OpportunityType.FIXME_FOLLOWUP
        assert result[0].metadata["tag"] == "FIXME"

    def test_detects_hack(self) -> None:
        diff = (
            "diff --git a/src/util.py b/src/util.py\n"
            "+  # HACK: quick workaround for deadline\n"
        )
        result = extract_todos_from_diff(diff, 5)
        assert len(result) == 1
        assert result[0].metadata["tag"] == "HACK"

    def test_detects_followup(self) -> None:
        diff = (
            "diff --git a/src/auth.py b/src/auth.py\n"
            "+  # Follow-up: add rate limiting\n"
        )
        result = extract_todos_from_diff(diff, 7)
        assert len(result) == 1

    def test_ignores_removed_lines(self) -> None:
        diff = (
            "diff --git a/src/main.py b/src/main.py\n"
            "-# TODO: This was already here\n"
        )
        result = extract_todos_from_diff(diff, 1)
        assert len(result) == 0

    def test_ignores_context_lines(self) -> None:
        diff = (
            "diff --git a/src/main.py b/src/main.py\n"
            " # TODO: This is a context line\n"
        )
        result = extract_todos_from_diff(diff, 1)
        assert len(result) == 0

    def test_multiple_todos(self) -> None:
        diff = (
            "diff --git a/src/a.py b/src/a.py\n"
            "+# TODO: First thing\n"
            "+# FIXME: Second thing\n"
        )
        result = extract_todos_from_diff(diff, 3)
        assert len(result) == 2

    def test_empty_diff(self) -> None:
        result = extract_todos_from_diff("", 1)
        assert len(result) == 0

    def test_case_insensitive(self) -> None:
        diff = (
            "diff --git a/src/main.py b/src/main.py\n"
            "+# todo: lowercase pattern\n"
        )
        result = extract_todos_from_diff(diff, 1)
        assert len(result) == 1

    def test_suggested_agent_is_task_decomposer(self) -> None:
        diff = (
            "diff --git a/src/x.py b/src/x.py\n"
            "+# TODO: refactor this\n"
        )
        result = extract_todos_from_diff(diff, 1)
        assert result[0].suggested_agent == "task-decomposer"


class TestScoreIssueComplexity:
    """Test issue complexity scoring."""

    def test_high_complexity_architecture(self) -> None:
        assert score_issue_complexity("Architecture redesign", "") == "high"

    def test_high_complexity_security(self) -> None:
        assert score_issue_complexity("Security vulnerability in auth", "") == "high"

    def test_high_complexity_migration(self) -> None:
        assert score_issue_complexity("Database migration plan", "") == "high"

    def test_medium_complexity_feature(self) -> None:
        assert score_issue_complexity("New feature request", "") == "medium"

    def test_low_complexity_bug(self) -> None:
        assert score_issue_complexity("Bug in login page", "") == "low"

    def test_low_complexity_typo(self) -> None:
        assert score_issue_complexity("Fix typo in readme", "") == "low"

    def test_body_used_for_scoring(self) -> None:
        result = score_issue_complexity("Simple title", "This requires a full migration")
        assert result == "high"

    def test_default_medium(self) -> None:
        result = score_issue_complexity("Unrelated title", "No keywords here")
        assert result == "medium"

    def test_no_false_positive_prefix(self) -> None:
        """Word boundary matching prevents 'prefix' from matching 'fix'."""
        result = score_issue_complexity("Add prefix to variables", "")
        assert result == "medium"

    def test_no_false_positive_fixture(self) -> None:
        """Word boundary matching prevents 'fixture' from matching 'fix'."""
        result = score_issue_complexity("Test fixture setup", "")
        assert result == "medium"


class TestSuggestAgents:
    """Test agent routing suggestions."""

    def test_security_keywords(self) -> None:
        agents = suggest_agents("Fix vulnerability in auth", "")
        assert "agent-security" in agents

    def test_architect_keywords(self) -> None:
        agents = suggest_agents("Create ADR for new design", "")
        assert "agent-architect" in agents

    def test_devops_keywords(self) -> None:
        agents = suggest_agents("Update the pipeline config", "")
        assert "agent-devops" in agents

    def test_multiple_agents(self) -> None:
        agents = suggest_agents(
            "Security architecture review",
            "Investigate the auth pipeline for vulnerabilities",
        )
        assert len(agents) >= 2

    def test_no_match(self) -> None:
        agents = suggest_agents("Generic title", "Generic body")
        assert len(agents) == 0

    def test_qa_keywords(self) -> None:
        agents = suggest_agents("Add test coverage for module", "")
        assert "agent-qa" in agents

    def test_planner_keywords(self) -> None:
        agents = suggest_agents("Create milestone for Q3", "")
        assert "agent-milestone-planner" in agents

    def test_no_false_positive_ci_in_critical(self) -> None:
        """'ci' should not match inside 'critical'."""
        agents = suggest_agents("Critical infrastructure down", "")
        # Should not match agent-devops via "ci"
        assert "agent-devops" not in agents

    def test_no_false_positive_cd_in_credential(self) -> None:
        """'cd' should not match inside 'credential'."""
        agents = suggest_agents("Store credential safely", "")
        # 'credential' contains 'credential' which matches agent-security
        assert "agent-devops" not in agents


class TestProcessIssueEvent:
    """Test issue event processing."""

    def test_returns_complexity_triage(self) -> None:
        result = process_issue_event(1, "New feature: add auth", "Implement OAuth")
        types = [o.opportunity_type for o in result]
        assert OpportunityType.COMPLEXITY_TRIAGE in types

    def test_returns_agent_routing(self) -> None:
        result = process_issue_event(1, "Security vulnerability", "CVE fix needed")
        types = [o.opportunity_type for o in result]
        assert OpportunityType.AGENT_ROUTING in types

    def test_high_complexity_gets_high_priority(self) -> None:
        result = process_issue_event(1, "Architecture migration", "")
        triage = [o for o in result if o.opportunity_type == OpportunityType.COMPLEXITY_TRIAGE]
        assert triage[0].priority == "high"

    def test_low_complexity_gets_medium_priority(self) -> None:
        result = process_issue_event(1, "Fix typo", "")
        triage = [o for o in result if o.opportunity_type == OpportunityType.COMPLEXITY_TRIAGE]
        assert triage[0].priority == "medium"

    def test_no_routing_if_no_agent_match(self) -> None:
        result = process_issue_event(1, "Generic title", "Generic body")
        types = [o.opportunity_type for o in result]
        assert OpportunityType.AGENT_ROUTING not in types

    def test_opened_event_uses_issue_opened_type(self) -> None:
        result = process_issue_event(1, "Security vulnerability", "CVE", event_action="opened")
        assert result[0].source_event == EventType.ISSUE_OPENED
        assert "New issue opened" in result[0].description

    def test_labeled_event_uses_issue_labeled_type(self) -> None:
        result = process_issue_event(1, "Security vulnerability", "CVE", event_action="labeled")
        assert result[0].source_event == EventType.ISSUE_LABELED
        assert "Issue labeled" in result[0].description

    def test_backward_compat_alias(self) -> None:
        """process_issue_opened is an alias for process_issue_event."""
        result = process_issue_opened(1, "New feature: add auth", "Implement OAuth")
        types = [o.opportunity_type for o in result]
        assert OpportunityType.COMPLEXITY_TRIAGE in types


class TestDetectArtifactChanges:
    """Test artifact change detection."""

    def test_adr_detection(self) -> None:
        files = [".agents/architecture/ADR-050-new-pattern.md"]
        result = detect_artifact_changes(files)
        assert len(result) == 1
        assert result[0].suggested_agent == "milestone-planner"
        assert result[0].priority == "high"
        assert result[0].metadata["artifact_type"] == "adr"

    def test_planning_detection(self) -> None:
        files = [".agents/planning/001-feature-plan.md"]
        result = detect_artifact_changes(files)
        assert len(result) == 1
        assert result[0].suggested_agent == "critic"
        assert result[0].metadata["artifact_type"] == "planning"

    def test_skills_detection(self) -> None:
        files = [".agents/skills/new-skill.md"]
        result = detect_artifact_changes(files)
        assert len(result) == 1
        assert result[0].suggested_agent == "skillbook"
        assert result[0].metadata["artifact_type"] == "skill"

    def test_ignores_non_agent_files(self) -> None:
        files = ["src/main.py", "README.md"]
        result = detect_artifact_changes(files)
        assert len(result) == 0

    def test_ignores_unrecognized_agent_dirs(self) -> None:
        files = [".agents/sessions/2024-01-01-session.json"]
        result = detect_artifact_changes(files)
        assert len(result) == 0

    def test_multiple_artifacts(self) -> None:
        files = [
            ".agents/architecture/ADR-001-test.md",
            ".agents/planning/plan.md",
            ".agents/skills/skill.md",
        ]
        result = detect_artifact_changes(files)
        assert len(result) == 3


class TestDetectOpportunities:
    """Test the main detect_opportunities function."""

    def test_pr_merged_with_diff(self) -> None:
        diff = (
            "diff --git a/src/x.py b/src/x.py\n"
            "+# TODO: clean up later\n"
        )
        with patch("scripts.velocity_accelerator.get_pr_diff", return_value=diff):
            result = detect_opportunities(
                event_name="pull_request",
                event_action="closed",
                pr_number=10,
                pr_merged=True,
            )
        assert len(result) == 1
        assert result[0].opportunity_type == OpportunityType.TODO_FOLLOWUP

    def test_pr_not_merged_skipped(self) -> None:
        with patch("scripts.velocity_accelerator.get_pr_diff") as mock_diff:
            result = detect_opportunities(
                event_name="pull_request",
                event_action="closed",
                pr_number=10,
                pr_merged=False,
            )
        mock_diff.assert_not_called()
        assert len(result) == 0

    def test_issue_opened(self) -> None:
        result = detect_opportunities(
            event_name="issues",
            event_action="opened",
            issue_number=5,
            issue_title="Security vulnerability",
            issue_body="Found a CVE",
        )
        assert len(result) >= 1

    def test_issue_labeled_uses_labeled_event(self) -> None:
        result = detect_opportunities(
            event_name="issues",
            event_action="labeled",
            issue_number=5,
            issue_title="Security vulnerability",
            issue_body="Found a CVE",
        )
        assert len(result) >= 1
        assert result[0].source_event == EventType.ISSUE_LABELED

    def test_push_with_agent_files(self) -> None:
        result = detect_opportunities(
            event_name="push",
            changed_files=[".agents/architecture/ADR-099-test.md"],
        )
        assert len(result) == 1
        assert result[0].metadata["artifact_type"] == "adr"

    def test_push_with_no_agent_files(self) -> None:
        result = detect_opportunities(
            event_name="push",
            changed_files=["src/main.py"],
        )
        assert len(result) == 0

    def test_unknown_event(self) -> None:
        result = detect_opportunities(event_name="unknown")
        assert len(result) == 0


class TestFormatSummary:
    """Test summary formatting."""

    def test_no_opportunities(self) -> None:
        result = format_summary([])
        assert "No velocity opportunities detected" in result

    def test_with_opportunities(self) -> None:
        opps = [
            Opportunity(
                opportunity_type=OpportunityType.TODO_FOLLOWUP,
                title="TODO in main.py",
                description="Found TODO",
                source_event=EventType.PR_MERGED,
                source_ref="PR #1",
                suggested_agent="task-decomposer",
            )
        ]
        result = format_summary(opps)
        assert "1 Opportunities Detected" in result
        assert "TODO in main.py" in result
        assert "task-decomposer" in result


class TestMainCLI:
    """Test the main CLI entry point."""

    def test_issue_opened_json_output(self, capsys: pytest.CaptureFixture[str]) -> None:
        exit_code = main([
            "--event", "issues",
            "--action", "opened",
            "--issue-number", "1",
            "--issue-title", "Security vulnerability found",
            "--issue-body", "Critical auth bypass",
        ])
        assert exit_code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_issue_opened_summary_output(self, capsys: pytest.CaptureFixture[str]) -> None:
        exit_code = main([
            "--event", "issues",
            "--action", "opened",
            "--issue-number", "1",
            "--issue-title", "New feature request",
            "--issue-body", "Add authentication",
            "--output-format", "summary",
        ])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "Velocity Accelerator" in captured.out

    def test_no_opportunities_returns_0(self) -> None:
        exit_code = main([
            "--event", "push",
            "--changed-files", "README.md",
        ])
        assert exit_code == 0

    def test_push_with_agent_files(self, capsys: pytest.CaptureFixture[str]) -> None:
        exit_code = main([
            "--event", "push",
            "--changed-files", ".agents/architecture/ADR-001-test.md",
        ])
        assert exit_code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert len(data) == 1

    def test_missing_event_returns_2(self) -> None:
        exit_code = main([])
        assert exit_code == 2
