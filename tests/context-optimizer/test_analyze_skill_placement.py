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

import json
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

# Add scripts directory to path
scripts_dir = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(scripts_dir))

from analyze_skill_placement import (  # noqa: E402
    analyze_content,
    detect_always_needed_patterns,
    detect_user_trigger_patterns,
    get_classification,
    get_hybrid_recommendations,
    get_skill_content,
    measure_action_verbs,
    measure_reference_content,
    measure_tool_calls,
)

if TYPE_CHECKING:
    pass


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

    def test_reads_skill_md_from_directory(self, tmp_path: Path) -> None:
        """Reads SKILL.md from directory path."""
        skill_dir = tmp_path / "test-skill"
        skill_dir.mkdir()
        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text("# Test Skill")

        result = get_skill_content(skill_dir)

        assert result == "# Test Skill"

    def test_reads_skill_md_file_directly(self, tmp_path: Path) -> None:
        """Reads SKILL.md file directly."""
        skill_md = tmp_path / "SKILL.md"
        skill_md.write_text("# Direct Read")

        result = get_skill_content(skill_md)

        assert result == "# Direct Read"

    def test_raises_file_not_found_for_missing_skill_md(
        self, tmp_path: Path
    ) -> None:
        """Raises FileNotFoundError if SKILL.md missing in directory."""
        skill_dir = tmp_path / "empty-skill"
        skill_dir.mkdir()

        with pytest.raises(FileNotFoundError, match="SKILL.md not found"):
            get_skill_content(skill_dir)

    def test_raises_value_error_for_non_md_file(self, tmp_path: Path) -> None:
        """Raises ValueError if path is not .md file."""
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


class TestAlwaysNeededPatternDetection:
    """Tests for detect_always_needed_patterns function."""

    def test_detects_always_keyword(self) -> None:
        """Detects 'always' keyword."""
        count = detect_always_needed_patterns("Always check this before proceeding")
        assert count > 0

    def test_detects_every_turn_patterns(self) -> None:
        """Detects 'every turn' patterns."""
        count = detect_always_needed_patterns("Every turn the agent must verify")
        assert count > 0

    def test_detects_mandatory_keyword(self) -> None:
        """Detects 'mandatory' keyword."""
        count = detect_always_needed_patterns("This is mandatory for all operations")
        assert count > 0

    def test_detects_framework_knowledge_patterns(self) -> None:
        """Detects framework knowledge patterns."""
        count = detect_always_needed_patterns("Framework knowledge and reference data")
        assert count >= 2

    def test_detects_routing_rules_patterns(self) -> None:
        """Detects routing rules patterns."""
        count = detect_always_needed_patterns("Decision framework and routing rules")
        assert count >= 2

    def test_returns_zero_for_on_demand_content(self) -> None:
        """Returns zero for on-demand content."""
        count = detect_always_needed_patterns("User requests this when needed")
        assert count == 0


class TestGetClassification:
    """Tests for get_classification function."""

    def test_classifies_tool_heavy_as_skill(self) -> None:
        """Classifies tool-heavy content as Skill."""
        classification, confidence, _ = get_classification(
            tool_calls=10, action_verbs=15, reference_ratio=0.3,
            user_triggers=5, always_needed=0
        )
        assert classification == "Skill"
        assert confidence > 60

    def test_classifies_reference_heavy_as_passive(self) -> None:
        """Classifies reference-heavy content as PassiveContext."""
        classification, confidence, _ = get_classification(
            tool_calls=0, action_verbs=2, reference_ratio=0.9,
            user_triggers=0, always_needed=5
        )
        assert classification == "PassiveContext"
        assert confidence > 60

    def test_classifies_mixed_as_hybrid(self) -> None:
        """Classifies mixed content as Hybrid."""
        classification, confidence, reasons = get_classification(
            tool_calls=3, action_verbs=6, reference_ratio=0.7,
            user_triggers=2, always_needed=2
        )
        assert classification == "Hybrid"
        assert 50 <= confidence <= 70
        assert any("Mixed indicators" in r for r in reasons)

    def test_returns_confidence_between_0_and_100(self) -> None:
        """Returns confidence between 0 and 100."""
        _, confidence, _ = get_classification(
            tool_calls=20, action_verbs=30, reference_ratio=0.2,
            user_triggers=10, always_needed=0
        )
        assert 0 <= confidence <= 100


class TestGetHybridRecommendations:
    """Tests for get_hybrid_recommendations function."""

    def test_returns_none_for_non_hybrid(self) -> None:
        """Returns None for non-hybrid classification."""
        result = get_hybrid_recommendations(SKILL_CONTENT, "Skill")
        assert result is None

    def test_provides_recommendations_for_hybrid(self) -> None:
        """Provides recommendations for hybrid classification."""
        result = get_hybrid_recommendations(HYBRID_CONTENT, "Hybrid")
        assert result is not None
        assert "Passive" in result
        assert "Skill" in result

    def test_detects_routing_rules_as_passive(self) -> None:
        """Detects routing rules as passive content."""
        result = get_hybrid_recommendations(HYBRID_CONTENT, "Hybrid")
        assert result is not None
        assert any("Routing" in item for item in result["Passive"])

    def test_detects_script_references_as_skill(self) -> None:
        """Detects script references as skill content."""
        result = get_hybrid_recommendations(HYBRID_CONTENT, "Hybrid")
        assert result is not None
        assert any(".ps1" in item for item in result["Skill"])


class TestAnalyzeContent:
    """Tests for analyze_content function."""

    def test_classifies_skill_content(self) -> None:
        """Classifies skill content correctly."""
        result = analyze_content(SKILL_CONTENT)
        assert result["classification"] == "Skill"

    def test_classifies_passive_content(self) -> None:
        """Classifies passive content correctly."""
        result = analyze_content(PASSIVE_CONTENT)
        assert result["classification"] == "PassiveContext"

    def test_classifies_hybrid_content(self) -> None:
        """Classifies hybrid content correctly."""
        result = analyze_content(HYBRID_CONTENT)
        assert result["classification"] == "Hybrid"

    def test_includes_metrics_when_detailed(self) -> None:
        """Includes metrics when detailed flag set."""
        result = analyze_content(SKILL_CONTENT, detailed=True)
        assert result["metrics"] is not None
        assert "tool_calls" in result["metrics"]
        assert "action_verbs" in result["metrics"]
        assert "reference_content_ratio" in result["metrics"]

    def test_excludes_metrics_by_default(self) -> None:
        """Excludes metrics by default."""
        result = analyze_content(SKILL_CONTENT)
        assert result["metrics"] is None

    def test_includes_recommendations_for_hybrid(self) -> None:
        """Includes recommendations for hybrid content."""
        result = analyze_content(HYBRID_CONTENT)
        assert result["recommendations"] is not None

    def test_handles_empty_content_gracefully(self) -> None:
        """Handles empty content gracefully."""
        result = analyze_content("")
        assert result["classification"] in ["Skill", "PassiveContext", "Hybrid"]


class TestCLI:
    """Tests for command-line interface."""

    def test_exits_with_0_on_success(self, tmp_path: Path) -> None:
        """Exits with 0 on successful analysis."""
        script = scripts_dir / "analyze_skill_placement.py"
        result = subprocess.run(
            [sys.executable, str(script), "-c", SKILL_CONTENT],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0

    def test_exits_with_1_on_error(self) -> None:
        """Exits with 1 on error."""
        script = scripts_dir / "analyze_skill_placement.py"
        result = subprocess.run(
            [sys.executable, str(script), "-p", "/nonexistent/path"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1

    def test_outputs_valid_json(self) -> None:
        """Outputs valid JSON."""
        script = scripts_dir / "analyze_skill_placement.py"
        result = subprocess.run(
            [sys.executable, str(script), "-c", SKILL_CONTENT],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert "classification" in data
        assert "confidence" in data
        assert "reasoning" in data
