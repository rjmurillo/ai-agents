"""Tests for audit_orphaned_branches module.

Verifies orphaned session/memory artifact detection across remote branches.
Related: Issue #1379 (orphaned session artifacts)
"""

from __future__ import annotations

import json
from dataclasses import asdict
from unittest.mock import patch

from scripts.audit_orphaned_branches import (
    AuditReport,
    BranchArtifacts,
    audit_branches,
    find_orphaned_artifacts,
    format_report,
    list_remote_branches,
    parse_args,
)


class TestBranchArtifacts:
    """Tests for the BranchArtifacts dataclass."""

    def test_total_counts_both_types(self):
        artifacts = BranchArtifacts(
            branch="feat/test",
            session_files=[".agents/sessions/s1.json"],
            memory_files=[".serena/memories/m1.md", ".serena/memories/m2.md"],
        )
        assert artifacts.total == 3

    def test_total_zero_when_empty(self):
        artifacts = BranchArtifacts(branch="feat/clean")
        assert artifacts.total == 0

    def test_serializable_to_json(self):
        artifacts = BranchArtifacts(
            branch="feat/test",
            session_files=[".agents/sessions/s1.json"],
        )
        result = json.dumps(asdict(artifacts))
        assert '"branch": "feat/test"' in result


class TestAuditReport:
    """Tests for the AuditReport dataclass."""

    def test_has_orphans_false_when_empty(self):
        report = AuditReport(
            timestamp="2026-04-09T00:00:00Z",
            base_ref="origin/main",
        )
        assert report.has_orphans is False

    def test_has_orphans_true_when_populated(self):
        report = AuditReport(
            timestamp="2026-04-09T00:00:00Z",
            base_ref="origin/main",
            branches_with_orphans=1,
            orphans=[
                BranchArtifacts(
                    branch="feat/stale",
                    session_files=[".agents/sessions/s1.json"],
                ),
            ],
        )
        assert report.has_orphans is True

    def test_serializable_to_json(self):
        report = AuditReport(
            timestamp="2026-04-09T00:00:00Z",
            base_ref="origin/main",
        )
        result = json.dumps(asdict(report))
        parsed = json.loads(result)
        assert parsed["base_ref"] == "origin/main"
        assert parsed["branches_scanned"] == 0


class TestFindOrphanedArtifacts:
    """Tests for find_orphaned_artifacts function."""

    def test_detects_session_files(self):
        files = [
            ".agents/sessions/2026-01-01-session-01.json",
            "scripts/some_script.py",
        ]
        result = find_orphaned_artifacts("feat/test", files)
        assert len(result.session_files) == 1
        assert result.memory_files == []

    def test_detects_memory_files(self):
        files = [
            ".serena/memories/skill-cost-001.md",
            ".serena/memories/skill-cost-002.md",
        ]
        result = find_orphaned_artifacts("feat/test", files)
        assert len(result.memory_files) == 2
        assert result.session_files == []

    def test_detects_both_types(self):
        files = [
            ".agents/sessions/s1.json",
            ".serena/memories/m1.md",
            "README.md",
        ]
        result = find_orphaned_artifacts("feat/mixed", files)
        assert result.total == 2

    def test_ignores_non_artifact_files(self):
        files = [
            "scripts/some_script.py",
            ".github/workflows/ci.yml",
            "CLAUDE.md",
        ]
        result = find_orphaned_artifacts("feat/clean", files)
        assert result.total == 0

    def test_branch_name_preserved(self):
        result = find_orphaned_artifacts("fix/my-branch", [])
        assert result.branch == "fix/my-branch"


class TestListRemoteBranches:
    """Tests for list_remote_branches function."""

    @patch("scripts.audit_orphaned_branches._run_git")
    def test_filters_main(self, mock_git):
        mock_git.return_value = "origin/main\norigin/feat/test"
        result = list_remote_branches(exclude_patterns=[])
        assert "main" not in result
        assert "feat/test" in result

    @patch("scripts.audit_orphaned_branches._run_git")
    def test_excludes_patterns(self, mock_git):
        mock_git.return_value = (
            "origin/main\n"
            "origin/renovate/dep-1\n"
            "origin/feat/real"
        )
        result = list_remote_branches(exclude_patterns=["renovate/"])
        assert "renovate/dep-1" not in result
        assert "feat/real" in result

    @patch("scripts.audit_orphaned_branches._run_git")
    def test_returns_sorted(self, mock_git):
        mock_git.return_value = (
            "origin/feat/z-branch\n"
            "origin/feat/a-branch\n"
            "origin/feat/m-branch"
        )
        result = list_remote_branches(exclude_patterns=[])
        assert result == ["feat/a-branch", "feat/m-branch", "feat/z-branch"]

    @patch("scripts.audit_orphaned_branches._run_git")
    def test_handles_empty_output(self, mock_git):
        mock_git.return_value = ""
        result = list_remote_branches(exclude_patterns=[])
        assert result == []


class TestAuditBranches:
    """Tests for audit_branches function."""

    @patch("scripts.audit_orphaned_branches.diff_files_vs_main")
    @patch("scripts.audit_orphaned_branches.list_remote_branches")
    def test_counts_orphans(self, mock_list, mock_diff):
        mock_list.return_value = ["feat/stale", "feat/clean"]
        mock_diff.side_effect = [
            [".agents/sessions/s1.json", "README.md"],
            ["scripts/clean.py"],
        ]
        report = audit_branches()
        assert report.branches_scanned == 2
        assert report.branches_with_orphans == 1
        assert report.total_session_files == 1
        assert report.total_memory_files == 0

    @patch("scripts.audit_orphaned_branches.diff_files_vs_main")
    @patch("scripts.audit_orphaned_branches.list_remote_branches")
    def test_skips_branches_on_git_error(self, mock_list, mock_diff):
        mock_list.return_value = ["feat/deleted", "feat/ok"]
        mock_diff.side_effect = [
            RuntimeError("not found"),
            [".serena/memories/m1.md"],
        ]
        report = audit_branches()
        assert report.branches_scanned == 2
        assert report.branches_with_orphans == 1

    @patch("scripts.audit_orphaned_branches.diff_files_vs_main")
    @patch("scripts.audit_orphaned_branches.list_remote_branches")
    def test_no_orphans_report(self, mock_list, mock_diff):
        mock_list.return_value = ["feat/clean"]
        mock_diff.return_value = ["scripts/ok.py"]
        report = audit_branches()
        assert not report.has_orphans


class TestFormatReport:
    """Tests for format_report function."""

    def test_json_format_is_valid(self):
        report = AuditReport(
            timestamp="2026-04-09T00:00:00Z",
            base_ref="origin/main",
            branches_scanned=5,
        )
        output = format_report(report, "json")
        parsed = json.loads(output)
        assert parsed["branches_scanned"] == 5

    def test_text_format_includes_summary(self):
        report = AuditReport(
            timestamp="2026-04-09T00:00:00Z",
            base_ref="origin/main",
            branches_scanned=10,
            branches_with_orphans=0,
        )
        output = format_report(report, "text")
        assert "Branches scanned: 10" in output
        assert "No orphaned artifacts found." in output

    def test_text_format_lists_orphans(self):
        report = AuditReport(
            timestamp="2026-04-09T00:00:00Z",
            base_ref="origin/main",
            branches_with_orphans=1,
            orphans=[
                BranchArtifacts(
                    branch="feat/stale",
                    session_files=[".agents/sessions/s1.json"],
                    memory_files=[".serena/memories/m1.md"],
                ),
            ],
        )
        output = format_report(report, "text")
        assert "### feat/stale" in output
        assert "Sessions: 1" in output
        assert "Memories: 1" in output


class TestParseArgs:
    """Tests for CLI argument parsing."""

    def test_defaults(self):
        args = parse_args([])
        assert args.base_ref == "origin/main"
        assert args.output_format == "json"

    def test_custom_base_ref(self):
        args = parse_args(["--base-ref", "origin/develop"])
        assert args.base_ref == "origin/develop"

    def test_text_format(self):
        args = parse_args(["--format", "text"])
        assert args.output_format == "text"

    def test_exclude_patterns(self):
        args = parse_args(["--exclude", "renovate/", "dependabot/"])
        assert args.exclude == ["renovate/", "dependabot/"]
