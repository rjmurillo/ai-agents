"""Tests for analyze_skill_placement module.

These tests verify the skill/passive context classification functionality including:
- Tool call detection
- Action verb counting
- Reference vs procedural content ratio
- Classification logic (Skill, PassiveContext, Hybrid)
- Hybrid recommendations
- JSON output structure

Exit Codes:
    0: Success - All tests passed
    1: Error - One or more tests failed (set by pytest framework)

See: ADR-035 Exit Code Standardization
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Add scripts directory to path (tests moved to root tests/, scripts remain in skill)
repo_root = Path(__file__).parent.parent.parent
scripts_dir = repo_root / ".claude" / "skills" / "context-optimizer" / "scripts"
sys.path.insert(0, str(scripts_dir))

from analyze_skill_placement import (  # noqa: E402
    analyze_content,
    detect_user_trigger_patterns,
    get_skill_content,
    measure_action_verbs,
    measure_reference_content,
    measure_tool_calls,
)

# Sample content for testing
SKILL_CONTENT = """# GitHub Operations

## Process

1. Execute gh pr create command
2. Run gh issue close operation
3. Trigger gh workflow dispatch
4. Create new branch with git checkout
5. Commit changes using git commit
6. Push to remote via git push
7. Delete old branches

Use Bash tool to execute commands.
Write files with PowerShell.
Read configuration data.
Update issue status.
Modify PR labels.
"""

PASSIVE_CONTENT = """# Memory Hierarchy

Reference data for memory systems:

| System | Priority | Location |
|--------|----------|----------|
| Serena | 1 | .serena/memories/ |
| Forgetful | 2 | ~/.local/share/forgetful/ |

Always check memories before reasoning.
Framework knowledge for session protocol.
"""

HYBRID_CONTENT = """# PR Comment Responder

## Routing Rules

Classify comments by sentiment and type:

| Pattern | Route To |
|---------|----------|
| CWE-(\\d+) | security-scan |
| E(\\d+) | style-enforcement |

## Process

1. Run Get-UnaddressedComments.ps1
2. Execute Post-PRCommentReply.ps1 for each comment
3. Trigger security scan if CWE detected
"""


class TestGetSkillContent:
    """Tests for get_skill_content function."""

    def _patch_repo_root(self, monkeypatch: pytest.MonkeyPatch, root: Path) -> None:
        """Patch validate_path_within_repo to use tmp_path as repo root."""
        from path_validation import validate_path_within_repo as _orig

        def _validate_in_tmp(path: Path, repo_root: Path | None = None) -> Path:
            # path_validation ships untyped, so the call is Any; rebuilding the
            # Path is idempotent and keeps the annotation honest.
            return Path(_orig(path, repo_root=root))

        monkeypatch.setattr(
            "analyze_skill_placement.validate_path_within_repo", _validate_in_tmp
        )

    def test_reads_skill_md_from_directory(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Reads SKILL.md from directory path."""
        self._patch_repo_root(monkeypatch, tmp_path)
        skill_dir = tmp_path / "test-skill"
        skill_dir.mkdir()
        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text("# Test Skill")

        result = get_skill_content(skill_dir)

        assert result == "# Test Skill"

    def test_reads_skill_md_file_directly(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Reads SKILL.md file directly."""
        self._patch_repo_root(monkeypatch, tmp_path)
        skill_md = tmp_path / "SKILL.md"
        skill_md.write_text("# Direct Read")

        result = get_skill_content(skill_md)

        assert result == "# Direct Read"

    def test_raises_file_not_found_for_missing_skill_md(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Raises FileNotFoundError if SKILL.md missing in directory."""
        self._patch_repo_root(monkeypatch, tmp_path)
        skill_dir = tmp_path / "empty-skill"
        skill_dir.mkdir()

        with pytest.raises(FileNotFoundError, match="SKILL.md not found"):
            get_skill_content(skill_dir)

    def test_raises_value_error_for_non_md_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Raises ValueError if path is not .md file."""
        self._patch_repo_root(monkeypatch, tmp_path)
        txt_file = tmp_path / "test.txt"
        txt_file.write_text("test")

        with pytest.raises(ValueError, match="must be a directory or .md file"):
            get_skill_content(txt_file)


class TestMeasureToolCalls:
    """Tests for measure_tool_calls function."""

    def test_detects_bash_tool_calls(self) -> None:
        """Detects Bash tool calls."""
        count = measure_tool_calls("Use Bash() to run commands")
        assert count > 0

    def test_detects_read_write_edit_calls(self) -> None:
        """Detects Read, Write, Edit calls."""
        count = measure_tool_calls("Read file, Write content, Edit section")
        assert count >= 3

    def test_detects_gh_commands(self) -> None:
        """Detects gh commands."""
        count = measure_tool_calls("Run gh pr create and gh issue close")
        assert count >= 2

    def test_detects_git_commands(self) -> None:
        """Detects git commands."""
        count = measure_tool_calls("Execute git commit and git push")
        assert count >= 2

    def test_detects_powershell_cmdlets(self) -> None:
        """Detects PowerShell cmdlets."""
        count = measure_tool_calls("Invoke-Command and Set-Content and New-Item")
        assert count >= 3

    def test_returns_zero_for_no_tool_calls(self) -> None:
        """Returns zero for text with no tool calls."""
        count = measure_tool_calls("This is just plain text with no commands")
        assert count == 0


class TestMeasureActionVerbs:
    """Tests for measure_action_verbs function."""

    def test_detects_common_action_verbs(self) -> None:
        """Detects common action verbs."""
        count = measure_action_verbs("create update delete execute run modify")
        assert count >= 6

    def test_detects_git_related_action_verbs(self) -> None:
        """Detects git-related action verbs."""
        count = measure_action_verbs("commit push merge changes")
        assert count >= 3

    def test_detects_issue_pr_action_verbs(self) -> None:
        """Detects issue/PR action verbs."""
        count = measure_action_verbs("close open trigger generate validate")
        assert count >= 5

    def test_returns_zero_for_passive_language(self) -> None:
        """Returns zero for passive language."""
        count = measure_action_verbs("Reference data is available for retrieval")
        assert count == 0

    def test_is_case_insensitive(self) -> None:
        """Is case insensitive."""
        count = measure_action_verbs("CREATE Update DELETE")
        assert count >= 3


class TestMeasureReferenceContent:
    """Tests for measure_reference_content function."""

    def test_detects_tables_as_reference_content(self) -> None:
        """Detects tables as reference content."""
        text = """
| Column1 | Column2 |
|---------|---------|
| Value1  | Value2  |
"""
        ratio = measure_reference_content(text)
        assert ratio > 0.5

    def test_detects_lists_as_reference_content(self) -> None:
        """Detects lists as reference content."""
        text = """
- Item one
- Item two
* Item three
"""
        ratio = measure_reference_content(text)
        assert ratio > 0.5

    def test_detects_code_blocks_as_reference_content(self) -> None:
        """Detects code blocks as reference content."""
        text = """
```powershell
Get-Content file.txt
```
"""
        ratio = measure_reference_content(text)
        assert ratio > 0

    def test_detects_numbered_steps_as_procedural(self) -> None:
        """Detects numbered steps as procedural."""
        text = """
1. First step
2. Second step
3. Third step
"""
        ratio = measure_reference_content(text)
        assert ratio < 0.5

    def test_detects_phases_as_procedural(self) -> None:
        """Detects phases as procedural."""
        text = "Phase 1: Setup, Phase 2: Execution, Phase 3: Cleanup"
        ratio = measure_reference_content(text)
        assert ratio < 0.5

    def test_returns_neutral_for_empty_content(self) -> None:
        """Returns neutral for empty content."""
        ratio = measure_reference_content("")
        assert ratio == 0.5


class TestUserTriggerPatternDetection:
    """Tests for detect_user_trigger_patterns function."""

    def test_detects_when_user_patterns(self) -> None:
        """Detects 'when user' patterns."""
        count = detect_user_trigger_patterns("When user requests a feature")
        assert count > 0

    def test_detects_triggered_by_patterns(self) -> None:
        """Detects 'triggered by' patterns."""
        count = detect_user_trigger_patterns("Triggered by user action")
        assert count > 0

    def test_detects_slash_commands(self) -> None:
        """Detects slash commands."""
        count = detect_user_trigger_patterns("Use /commit or /push commands")
        assert count >= 2

    def test_detects_explicit_request_patterns(self) -> None:
        """Detects explicit request patterns."""
        count = detect_user_trigger_patterns("On explicit request from user")
        assert count > 0

    def test_returns_zero_for_always_on_content(self) -> None:
        """Returns zero for always-on content."""
        count = detect_user_trigger_patterns("This framework is always available")
        assert count == 0


class TestAdmissionIsNotPatternMatched:
    """Issue #3936: always-on vocabulary must not push content toward passive.

    SKILL.md routes what the model already knows to progressive disclosure or
    nowhere; scoring "always" and "mandatory" toward passive inverted that.
    """

    def test_always_on_vocabulary_alone_does_not_reach_passive(self) -> None:
        """Vocabulary must not carry weak reference shape (0.67) into passive."""
        content = (
            "# Memory Hierarchy\n\n"
            "- Always apply this policy. Every turn the agent must verify.\n"
            "- Mandatory for all: framework knowledge and reference data.\n"
            "1. Decision framework and routing rules stay constantly persistent.\n"
        )

        result = analyze_content(content, detailed=True)

        assert result["classification"] != "PassiveContext"
        assert "Always-needed" not in result["reasoning"]

    def test_known_principles_digest_is_not_promoted_by_vocabulary(self) -> None:
        """Same body scores identically with and without the always-on words."""
        body = (
            "# Unified Software Engineering\n\n"
            "- Prefer small cohesive functions\n"
            "- Validate the diff before review\n"
        )
        loaded = body + "- Always mandatory framework knowledge and routing rules\n"

        plain_result = analyze_content(body)
        loaded_result = analyze_content(loaded)

        assert loaded_result["classification"] == plain_result["classification"]
        assert loaded_result["confidence"] == plain_result["confidence"]
        assert loaded_result["reasoning"] == plain_result["reasoning"]

    def test_detailed_metrics_expose_no_always_needed_key(self) -> None:
        """The JSON contract no longer carries an always-needed metric."""
        metrics = analyze_content(HYBRID_CONTENT, detailed=True)["metrics"]

        assert metrics is not None
        assert "always_needed" not in metrics
