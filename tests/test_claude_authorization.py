"""Tests for test_claude_authorization module.

Comprehensive tests for the Claude Code authorization check script,
verifying webhook event authorization logic, audit logging, and error handling.

This is the test suite for the Python port of Test-ClaudeAuthorization.ps1
following ADR-042 migration.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

# Add project root to path for imports
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT))

from tests.workflows.test_claude_authorization import (  # noqa: E402
    ALLOWED_ASSOCIATIONS,
    ALLOWED_BOTS,
    CLAUDE_MENTION_PATTERN,
    MAX_BODY_LENGTH,
    VALID_EVENTS,
    build_parser,
    check_authorization,
    extract_body,
    has_claude_mention,
    main,
    write_audit_log,
    write_error_audit_log,
    write_oversize_audit_log,
)

if TYPE_CHECKING:
    from _pytest.capture import CaptureFixture


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestConstants:
    """Tests for module-level constants."""

    def test_allowed_associations_contains_member(self) -> None:
        assert "MEMBER" in ALLOWED_ASSOCIATIONS

    def test_allowed_associations_contains_owner(self) -> None:
        assert "OWNER" in ALLOWED_ASSOCIATIONS

    def test_allowed_associations_contains_collaborator(self) -> None:
        assert "COLLABORATOR" in ALLOWED_ASSOCIATIONS

    def test_allowed_associations_count(self) -> None:
        assert len(ALLOWED_ASSOCIATIONS) == 3

    def test_allowed_bots_contains_dependabot(self) -> None:
        assert "dependabot[bot]" in ALLOWED_BOTS

    def test_allowed_bots_contains_renovate(self) -> None:
        assert "renovate[bot]" in ALLOWED_BOTS

    def test_allowed_bots_contains_github_actions(self) -> None:
        assert "github-actions[bot]" in ALLOWED_BOTS

    def test_allowed_bots_contains_copilot(self) -> None:
        assert "copilot[bot]" in ALLOWED_BOTS

    def test_allowed_bots_contains_coderabbitai(self) -> None:
        assert "coderabbitai[bot]" in ALLOWED_BOTS

    def test_allowed_bots_contains_cursor(self) -> None:
        assert "cursor[bot]" in ALLOWED_BOTS

    def test_allowed_bots_contains_gemini_ai(self) -> None:
        assert "gemini-ai[bot]" in ALLOWED_BOTS

    def test_allowed_bots_contains_claude_ai(self) -> None:
        assert "claude-ai[bot]" in ALLOWED_BOTS

    def test_allowed_bots_contains_amazonq(self) -> None:
        assert "amazonq[bot]" in ALLOWED_BOTS

    def test_allowed_bots_contains_tabnine(self) -> None:
        assert "tabnine[bot]" in ALLOWED_BOTS

    def test_allowed_bots_count(self) -> None:
        assert len(ALLOWED_BOTS) == 10

    def test_max_body_length_is_1mb(self) -> None:
        assert MAX_BODY_LENGTH == 1_048_576

    def test_valid_events_count(self) -> None:
        assert len(VALID_EVENTS) == 6


# ---------------------------------------------------------------------------
# extract_body
# ---------------------------------------------------------------------------


class TestExtractBody:
    """Tests for extract_body function."""

    def test_issue_comment_returns_comment_body(self) -> None:
        result = extract_body(
            "issue_comment", "comment text", "", "", "", "", "",
        )
        assert result == "comment text"

    def test_pr_review_comment_returns_comment_body(self) -> None:
        result = extract_body(
            "pull_request_review_comment", "review comment", "", "", "", "", "",
        )
        assert result == "review comment"

    def test_pr_review_returns_review_body(self) -> None:
        result = extract_body(
            "pull_request_review", "", "review body", "", "", "", "",
        )
        assert result == "review body"

    def test_issues_combines_body_and_title(self) -> None:
        result = extract_body(
            "issues", "", "", "issue body", "issue title", "", "",
        )
        assert result == "issue body issue title"

    def test_pull_request_combines_body_and_title(self) -> None:
        result = extract_body(
            "pull_request", "", "", "", "", "pr body", "pr title",
        )
        assert result == "pr body pr title"

    def test_workflow_dispatch_returns_empty(self) -> None:
        result = extract_body(
            "workflow_dispatch", "ignored", "ignored", "ignored",
            "ignored", "ignored", "ignored",
        )
        assert result == ""


# ---------------------------------------------------------------------------
# has_claude_mention
# ---------------------------------------------------------------------------


class TestHasClaudeMention:
    """Tests for has_claude_mention and the regex pattern."""

    def test_basic_mention(self) -> None:
        assert has_claude_mention("Hey @claude help me")

    def test_mention_at_end_of_string(self) -> None:
        assert has_claude_mention("Please help @claude")

    def test_mention_followed_by_period(self) -> None:
        assert has_claude_mention("Ask @claude.")

    def test_mention_followed_by_comma(self) -> None:
        assert has_claude_mention("Hey @claude, what do you think?")

    def test_mention_followed_by_newline(self) -> None:
        assert has_claude_mention("@claude\nPlease review this")

    def test_mention_followed_by_space(self) -> None:
        assert has_claude_mention("@claude please help")

    def test_claudette_not_matched(self) -> None:
        assert not has_claude_mention("Hey @claudette help me")

    def test_claude123_not_matched(self) -> None:
        assert not has_claude_mention("Hey @claude123 help me")

    def test_claude_bot_not_matched(self) -> None:
        assert not has_claude_mention("Hey @claude_bot help me")

    def test_claudeai_not_matched(self) -> None:
        assert not has_claude_mention("Hey @claudeai help me")

    def test_empty_string(self) -> None:
        assert not has_claude_mention("")

    def test_whitespace_only(self) -> None:
        assert not has_claude_mention("   ")

    def test_no_mention(self) -> None:
        assert not has_claude_mention("Just a regular comment")

    def test_case_sensitive_uppercase_not_matched(self) -> None:
        """@Claude (uppercase C) should NOT match. Case-sensitive pattern."""
        assert not has_claude_mention("Hey @Claude help")

    def test_case_sensitive_allcaps_not_matched(self) -> None:
        assert not has_claude_mention("Hey @CLAUDE help")

    def test_mention_in_middle_of_text(self) -> None:
        assert has_claude_mention("Some text @claude more text")

    def test_multiple_mentions(self) -> None:
        assert has_claude_mention("@claude and @claude again")

    def test_mention_with_exclamation(self) -> None:
        assert has_claude_mention("@claude!")


# ---------------------------------------------------------------------------
# check_authorization
# ---------------------------------------------------------------------------


class TestCheckAuthorization:
    """Tests for check_authorization function."""

    # -- workflow_dispatch --

    def test_workflow_dispatch_member_authorized(self) -> None:
        authorized, reason = check_authorization(
            "workflow_dispatch", "octocat", "MEMBER", False,
        )
        assert authorized is True
        assert "workflow_dispatch" in reason
        assert "octocat" in reason

    def test_workflow_dispatch_owner_authorized(self) -> None:
        authorized, _ = check_authorization(
            "workflow_dispatch", "octocat", "OWNER", False,
        )
        assert authorized is True

    def test_workflow_dispatch_collaborator_authorized(self) -> None:
        authorized, _ = check_authorization(
            "workflow_dispatch", "octocat", "COLLABORATOR", False,
        )
        assert authorized is True

    def test_workflow_dispatch_contributor_denied(self) -> None:
        authorized, reason = check_authorization(
            "workflow_dispatch", "external", "CONTRIBUTOR", False,
        )
        assert authorized is False
        assert "Access denied" in reason

    def test_workflow_dispatch_none_association_denied(self) -> None:
        authorized, reason = check_authorization(
            "workflow_dispatch", "stranger", "NONE", False,
        )
        assert authorized is False
        assert "Access denied" in reason

    def test_workflow_dispatch_no_mention_needed(self) -> None:
        """workflow_dispatch authorizes by association alone, no mention needed."""
        authorized, _ = check_authorization(
            "workflow_dispatch", "octocat", "MEMBER", False,
        )
        assert authorized is True

    # -- pull_request --

    def test_pr_bot_authorized_without_mention(self) -> None:
        for bot in ALLOWED_BOTS:
            authorized, reason = check_authorization(
                "pull_request", bot, "", False,
            )
            assert authorized is True, f"Bot {bot} should be authorized"
            assert "bot allowlist" in reason

    def test_pr_human_with_mention_and_association_authorized(self) -> None:
        authorized, reason = check_authorization(
            "pull_request", "octocat", "MEMBER", True,
        )
        assert authorized is True
        assert "@claude mention" in reason

    def test_pr_human_without_mention_denied(self) -> None:
        authorized, reason = check_authorization(
            "pull_request", "octocat", "MEMBER", False,
        )
        assert authorized is False
        assert "Access denied" in reason

    def test_pr_human_with_mention_but_wrong_association_denied(self) -> None:
        authorized, reason = check_authorization(
            "pull_request", "external", "CONTRIBUTOR", True,
        )
        assert authorized is False
        assert "Access denied" in reason

    # -- issue_comment (representative of "other events") --

    def test_issue_comment_member_with_mention_authorized(self) -> None:
        authorized, reason = check_authorization(
            "issue_comment", "octocat", "MEMBER", True,
        )
        assert authorized is True
        assert "author association" in reason

    def test_issue_comment_no_mention_denied(self) -> None:
        authorized, reason = check_authorization(
            "issue_comment", "octocat", "MEMBER", False,
        )
        assert authorized is False
        assert "No @claude mention" in reason

    def test_issue_comment_bot_with_mention_authorized(self) -> None:
        authorized, reason = check_authorization(
            "issue_comment", "dependabot[bot]", "", True,
        )
        assert authorized is True
        assert "bot allowlist" in reason

    def test_issue_comment_wrong_association_denied(self) -> None:
        authorized, reason = check_authorization(
            "issue_comment", "external", "CONTRIBUTOR", True,
        )
        assert authorized is False
        assert "not in bot allowlist" in reason

    def test_issue_comment_none_association_denied(self) -> None:
        authorized, reason = check_authorization(
            "issue_comment", "stranger", "NONE", True,
        )
        assert authorized is False
        assert "not in allowed list" in reason

    # -- pr_review --

    def test_pr_review_member_with_mention_authorized(self) -> None:
        authorized, _ = check_authorization(
            "pull_request_review", "octocat", "OWNER", True,
        )
        assert authorized is True

    def test_pr_review_comment_member_with_mention_authorized(self) -> None:
        authorized, _ = check_authorization(
            "pull_request_review_comment", "octocat", "COLLABORATOR", True,
        )
        assert authorized is True

    # -- issues --

    def test_issues_member_with_mention_authorized(self) -> None:
        authorized, _ = check_authorization(
            "issues", "octocat", "MEMBER", True,
        )
        assert authorized is True


# ---------------------------------------------------------------------------
# Audit logging
# ---------------------------------------------------------------------------


class TestWriteAuditLog:
    """Tests for audit log writing functions."""

    def test_write_audit_log_creates_file(self, tmp_path: Path) -> None:
        summary_file = tmp_path / "summary.md"
        summary_file.touch()
        write_audit_log(
            str(summary_file),
            "issue_comment",
            "octocat",
            "MEMBER",
            True,
            True,
            "Authorized via author association",
        )
        content = summary_file.read_text()
        assert "Claude Authorization Check" in content
        assert "issue_comment" in content
        assert "octocat" in content
        assert "MEMBER" in content
        assert "True" in content
        assert "Authorized via author association" in content
        assert "Timestamp" in content

    def test_write_audit_log_contains_rules_section(self, tmp_path: Path) -> None:
        summary_file = tmp_path / "summary.md"
        summary_file.touch()
        write_audit_log(
            str(summary_file), "issues", "actor", "OWNER", False, False, "denied",
        )
        content = summary_file.read_text()
        assert "Authorization Rules" in content
        assert "MEMBER" in content
        assert "dependabot[bot]" in content

    def test_write_oversize_audit_log(self, tmp_path: Path) -> None:
        summary_file = tmp_path / "summary.md"
        summary_file.touch()
        write_oversize_audit_log(
            str(summary_file), "issue_comment", "octocat", 2_000_000,
        )
        content = summary_file.read_text()
        assert "Event Body Too Large" in content
        assert "2000000" in content
        assert "issue_comment" in content
        assert "octocat" in content

    def test_write_error_audit_log(self, tmp_path: Path) -> None:
        summary_file = tmp_path / "summary.md"
        summary_file.touch()
        write_error_audit_log(
            str(summary_file), "something broke", "issues", "actor", "MEMBER",
        )
        content = summary_file.read_text()
        assert "ERROR" in content
        assert "something broke" in content


# ---------------------------------------------------------------------------
# CLI / main()
# ---------------------------------------------------------------------------


class TestMain:
    """Tests for main() function via CLI arguments."""

    def test_authorized_member_with_mention(
        self, capsys: CaptureFixture[str], monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
        exit_code = main([
            "--event-name", "issue_comment",
            "--actor", "octocat",
            "--author-association", "MEMBER",
            "--comment-body", "Hey @claude, help me",
        ])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "true"

    def test_denied_no_mention(
        self, capsys: CaptureFixture[str], monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
        exit_code = main([
            "--event-name", "issue_comment",
            "--actor", "octocat",
            "--author-association", "MEMBER",
            "--comment-body", "No mention here",
        ])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "false"

    def test_denied_wrong_association(
        self, capsys: CaptureFixture[str], monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
        exit_code = main([
            "--event-name", "issue_comment",
            "--actor", "external",
            "--author-association", "CONTRIBUTOR",
            "--comment-body", "Hey @claude",
        ])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "false"

    def test_denied_none_association(
        self, capsys: CaptureFixture[str], monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
        exit_code = main([
            "--event-name", "issue_comment",
            "--actor", "stranger",
            "--author-association", "NONE",
            "--comment-body", "@claude help",
        ])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "false"

    def test_workflow_dispatch_member_authorized(
        self, capsys: CaptureFixture[str], monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
        exit_code = main([
            "--event-name", "workflow_dispatch",
            "--actor", "octocat",
            "--author-association", "MEMBER",
        ])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "true"

    def test_workflow_dispatch_nonmember_denied(
        self, capsys: CaptureFixture[str], monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
        exit_code = main([
            "--event-name", "workflow_dispatch",
            "--actor", "external",
            "--author-association", "CONTRIBUTOR",
        ])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "false"

    def test_pr_bot_authorized_without_mention(
        self, capsys: CaptureFixture[str], monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
        exit_code = main([
            "--event-name", "pull_request",
            "--actor", "dependabot[bot]",
            "--author-association", "",
        ])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "true"

    def test_pr_human_with_mention_authorized(
        self, capsys: CaptureFixture[str], monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
        exit_code = main([
            "--event-name", "pull_request",
            "--actor", "octocat",
            "--author-association", "MEMBER",
            "--pr-body", "@claude please review",
        ])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "true"

    def test_pr_human_without_mention_denied(
        self, capsys: CaptureFixture[str], monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
        exit_code = main([
            "--event-name", "pull_request",
            "--actor", "octocat",
            "--author-association", "MEMBER",
            "--pr-body", "No mention",
        ])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "false"

    def test_empty_body_denied(
        self, capsys: CaptureFixture[str], monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
        exit_code = main([
            "--event-name", "issue_comment",
            "--actor", "octocat",
            "--author-association", "MEMBER",
            "--comment-body", "",
        ])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "false"


class TestMainBotAllowlist:
    """Tests for each bot in the allowlist via main()."""

    @pytest.mark.parametrize("bot", list(ALLOWED_BOTS))
    def test_bot_authorized_with_mention(
        self,
        bot: str,
        capsys: CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
        exit_code = main([
            "--event-name", "issue_comment",
            "--actor", bot,
            "--comment-body", "Hey @claude",
        ])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "true", f"Bot {bot} should be authorized"


class TestMainOversizedBody:
    """Tests for oversized body handling."""

    def test_oversized_body_denied_not_error(
        self, capsys: CaptureFixture[str], monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
        big_body = "x" * (MAX_BODY_LENGTH + 1)
        exit_code = main([
            "--event-name", "issue_comment",
            "--actor", "octocat",
            "--author-association", "MEMBER",
            "--comment-body", big_body,
        ])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "false"

    def test_oversized_body_writes_audit_log(
        self,
        tmp_path: Path,
        capsys: CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        summary_file = tmp_path / "summary.md"
        summary_file.touch()
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_file))
        big_body = "x" * (MAX_BODY_LENGTH + 1)
        exit_code = main([
            "--event-name", "issue_comment",
            "--actor", "octocat",
            "--author-association", "MEMBER",
            "--comment-body", big_body,
        ])
        assert exit_code == 0
        content = summary_file.read_text()
        assert "Event Body Too Large" in content

    def test_body_at_exact_limit_not_denied(
        self, capsys: CaptureFixture[str], monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Body at exactly MAX_BODY_LENGTH should not trigger oversize denial."""
        monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
        # Body at exact limit with @claude mention
        body = "@claude " + "x" * (MAX_BODY_LENGTH - len("@claude "))
        exit_code = main([
            "--event-name", "issue_comment",
            "--actor", "octocat",
            "--author-association", "MEMBER",
            "--comment-body", body,
        ])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "true"


class TestMainAuditLogging:
    """Tests for audit log integration via main()."""

    def test_audit_log_written_on_success(
        self,
        tmp_path: Path,
        capsys: CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        summary_file = tmp_path / "summary.md"
        summary_file.touch()
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_file))
        exit_code = main([
            "--event-name", "issue_comment",
            "--actor", "octocat",
            "--author-association", "MEMBER",
            "--comment-body", "@claude help",
        ])
        assert exit_code == 0
        content = summary_file.read_text()
        assert "Claude Authorization Check" in content
        assert "octocat" in content
        assert "MEMBER" in content

    def test_audit_log_written_on_denial(
        self,
        tmp_path: Path,
        capsys: CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        summary_file = tmp_path / "summary.md"
        summary_file.touch()
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_file))
        exit_code = main([
            "--event-name", "issue_comment",
            "--actor", "external",
            "--author-association", "NONE",
            "--comment-body", "no mention",
        ])
        assert exit_code == 0
        content = summary_file.read_text()
        assert "Claude Authorization Check" in content
        assert "False" in content

    def test_no_audit_log_without_env_var(
        self,
        tmp_path: Path,
        capsys: CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
        exit_code = main([
            "--event-name", "issue_comment",
            "--actor", "octocat",
            "--author-association", "MEMBER",
            "--comment-body", "@claude help",
        ])
        assert exit_code == 0
        # No file created, no error


class TestMainAuditFailure:
    """Tests for audit log write failure scenarios."""

    def test_audit_log_failure_returns_exit_1(
        self,
        capsys: CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Point to a non-writable path
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", "/nonexistent/dir/summary.md")
        exit_code = main([
            "--event-name", "issue_comment",
            "--actor", "octocat",
            "--author-association", "MEMBER",
            "--comment-body", "@claude help",
        ])
        assert exit_code == 1

    def test_oversize_audit_failure_returns_exit_1(
        self,
        capsys: CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", "/nonexistent/dir/summary.md")
        big_body = "x" * (MAX_BODY_LENGTH + 1)
        exit_code = main([
            "--event-name", "issue_comment",
            "--actor", "octocat",
            "--author-association", "MEMBER",
            "--comment-body", big_body,
        ])
        assert exit_code == 1

    def test_double_fault_returns_exit_2(
        self,
        capsys: CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When authorization raises AND audit logging fails, exit code is 2."""
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", "/nonexistent/dir/summary.md")

        # Patch extract_body to raise an exception, simulating auth failure
        with patch(
            "tests.workflows.test_claude_authorization.extract_body",
            side_effect=RuntimeError("simulated auth failure"),
        ):
            exit_code = main([
                "--event-name", "issue_comment",
                "--actor", "octocat",
                "--author-association", "MEMBER",
                "--comment-body", "@claude help",
            ])
        assert exit_code == 2
        captured = capsys.readouterr()
        assert captured.out.strip() == "false"

    def test_exception_with_successful_audit_returns_exit_1(
        self,
        tmp_path: Path,
        capsys: CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When authorization raises but audit log succeeds, exit code is 1."""
        summary_file = tmp_path / "summary.md"
        summary_file.touch()
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_file))

        with patch(
            "tests.workflows.test_claude_authorization.extract_body",
            side_effect=RuntimeError("simulated auth failure"),
        ):
            exit_code = main([
                "--event-name", "issue_comment",
                "--actor", "octocat",
                "--author-association", "MEMBER",
                "--comment-body", "@claude help",
            ])
        assert exit_code == 1
        content = summary_file.read_text()
        assert "ERROR" in content
        assert "simulated auth failure" in content

    def test_exception_without_summary_env_returns_exit_1(
        self,
        capsys: CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When authorization raises without GITHUB_STEP_SUMMARY, exit code is 1."""
        monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)

        with patch(
            "tests.workflows.test_claude_authorization.extract_body",
            side_effect=RuntimeError("simulated failure"),
        ):
            exit_code = main([
                "--event-name", "issue_comment",
                "--actor", "octocat",
                "--author-association", "MEMBER",
                "--comment-body", "@claude help",
            ])
        assert exit_code == 1


class TestMainEnvVarDefaults:
    """Tests that CLI args fall back to environment variables."""

    def test_author_association_from_env(
        self, capsys: CaptureFixture[str], monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
        monkeypatch.setenv("AUTHOR_ASSOCIATION", "MEMBER")
        # Don't pass --author-association; the env default triggers
        # but argparse evaluates defaults at parse time, so we need
        # to rebuild the parser. Use main() directly.
        exit_code = main([
            "--event-name", "issue_comment",
            "--actor", "octocat",
            "--comment-body", "@claude help",
        ])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "true"

    def test_comment_body_from_env(
        self, capsys: CaptureFixture[str], monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
        monkeypatch.setenv("COMMENT_BODY", "@claude help")
        exit_code = main([
            "--event-name", "issue_comment",
            "--actor", "octocat",
            "--author-association", "MEMBER",
        ])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "true"


class TestRegexEdgeCases:
    """Focused tests on the @claude regex pattern edge cases."""

    def test_pattern_matches_claude_at_end(self) -> None:
        assert CLAUDE_MENTION_PATTERN.search("text @claude") is not None

    def test_pattern_matches_claude_with_period(self) -> None:
        assert CLAUDE_MENTION_PATTERN.search("@claude.") is not None

    def test_pattern_does_not_match_claudette(self) -> None:
        assert CLAUDE_MENTION_PATTERN.search("@claudette") is None

    def test_pattern_does_not_match_claude123(self) -> None:
        assert CLAUDE_MENTION_PATTERN.search("@claude123") is None

    def test_pattern_does_not_match_claude_underscore(self) -> None:
        assert CLAUDE_MENTION_PATTERN.search("@claude_bot") is None

    def test_pattern_matches_claude_with_hyphen(self) -> None:
        """Hyphen is not a word character, so @claude-something should match @claude."""
        assert CLAUDE_MENTION_PATTERN.search("@claude-ai") is not None

    def test_pattern_matches_multiple_occurrences(self) -> None:
        matches = CLAUDE_MENTION_PATTERN.findall("@claude and @claude")
        assert len(matches) == 2

    def test_pattern_is_case_sensitive(self) -> None:
        """Uppercase variants must NOT match."""
        assert CLAUDE_MENTION_PATTERN.search("@Claude") is None
        assert CLAUDE_MENTION_PATTERN.search("@CLAUDE") is None
        assert CLAUDE_MENTION_PATTERN.search("@cLaUdE") is None


class TestBuildParser:
    """Tests for build_parser function."""

    def test_help_flag_works(self) -> None:
        parser = build_parser()
        with pytest.raises(SystemExit) as exc_info:
            parser.parse_args(["--help"])
        assert exc_info.value.code == 0

    def test_event_name_required(self) -> None:
        parser = build_parser()
        with pytest.raises(SystemExit) as exc_info:
            parser.parse_args(["--actor", "octocat"])
        assert exc_info.value.code == 2

    def test_actor_required(self) -> None:
        parser = build_parser()
        with pytest.raises(SystemExit) as exc_info:
            parser.parse_args(["--event-name", "issues"])
        assert exc_info.value.code == 2

    def test_invalid_event_rejected(self) -> None:
        parser = build_parser()
        with pytest.raises(SystemExit) as exc_info:
            parser.parse_args(["--event-name", "invalid_event", "--actor", "octocat"])
        assert exc_info.value.code == 2

    def test_all_valid_events_accepted(self) -> None:
        parser = build_parser()
        for event in VALID_EVENTS:
            args = parser.parse_args(["--event-name", event, "--actor", "test"])
            assert args.event_name == event
