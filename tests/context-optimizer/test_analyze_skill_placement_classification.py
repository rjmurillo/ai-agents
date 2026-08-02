"""Classification and CLI tests for analyze_skill_placement.

Split out of test_analyze_skill_placement.py, which held both the measurement
primitives and everything built on top of them and crossed the 500-line taste
limit. The seam is the same one the module has: measurement below, decisions and
CLI surface here.
"""


from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

# Add scripts directory to path (tests moved to root tests/, scripts remain in skill)
repo_root = Path(__file__).parent.parent.parent
scripts_dir = repo_root / ".claude" / "skills" / "context-optimizer" / "scripts"
sys.path.insert(0, str(scripts_dir))

from analyze_skill_placement import (  # noqa: E402
    analyze_content,
    get_classification,
    get_hybrid_recommendations,
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


class TestGetClassification:
    """Tests for get_classification function."""

    def test_classifies_tool_heavy_as_skill(self) -> None:
        """Classifies tool-heavy content as Skill."""
        classification, confidence, _ = get_classification(
            tool_calls=10, action_verbs=15, reference_ratio=0.3, user_triggers=5
        )
        assert classification == "Skill"
        assert confidence > 60

    def test_classifies_reference_heavy_as_passive(self) -> None:
        """Reference shape alone still reaches PassiveContext (#3936 coverage)."""
        classification, confidence, reasons = get_classification(
            tool_calls=0, action_verbs=2, reference_ratio=0.9, user_triggers=0
        )
        assert classification == "PassiveContext"
        assert confidence > 60
        assert any("reference content" in r for r in reasons)

    def test_classifies_mixed_as_hybrid(self) -> None:
        """Classifies mixed content as Hybrid."""
        classification, confidence, reasons = get_classification(
            tool_calls=3, action_verbs=6, reference_ratio=0.7, user_triggers=2
        )
        assert classification == "Hybrid"
        assert 50 <= confidence <= 70
        assert any("Mixed indicators" in r for r in reasons)

    def test_returns_confidence_between_0_and_100(self) -> None:
        """Returns confidence between 0 and 100."""
        _, confidence, _ = get_classification(
            tool_calls=20, action_verbs=30, reference_ratio=0.2, user_triggers=10
        )
        assert 0 <= confidence <= 100

    def test_rejects_removed_always_needed_argument(self) -> None:
        """The removed parameter is gone from the signature, not ignored."""
        # Dynamic on purpose: spelling the keyword inline makes mypy reject the
        # call for the very reason under test, which a suppression would hide.
        removed = {"always_needed": 5}
        with pytest.raises(TypeError):
            get_classification(
                tool_calls=0, action_verbs=0, reference_ratio=0.5,
                user_triggers=0, **removed,
            )


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
