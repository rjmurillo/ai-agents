"""Tests for test_skill_passive_compliance.py."""

import sys
import tempfile
from pathlib import Path

import pytest

# Add scripts directory to path (tests moved to root tests/, scripts remain in skill)
repo_root = Path(__file__).parent.parent.parent
scripts_dir = repo_root / ".claude" / "skills" / "context-optimizer" / "scripts"
sys.path.insert(0, str(scripts_dir))

from test_skill_passive_compliance import (  # noqa: E402
    check_imported_files_exist,
    check_no_duplicate_content,
    check_passive_context_knowledge_only,
    check_skill_frontmatter,
    check_skill_has_actions,
    measure_claude_md_single_file,
    run_compliance_checks,
)


@pytest.fixture
def temp_repo():
    """Create a temporary git repository for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir)
        (repo_path / ".git").mkdir()
        yield repo_path


def test_claude_md_single_file_measurement_reports_line_count(temp_repo):
    """A single-file measurement reports its observed line count."""
    claude_md = temp_repo / "CLAUDE.md"
    claude_md.write_text("# Test\n" + ("line\n" * 100))

    result = measure_claude_md_single_file(claude_md)

    assert result.passed
    assert result.severity == "none"
    assert result.details["lineCount"] == 101
    assert "No vendor line limit was applied" in result.message


def test_claude_md_single_file_measurement_ignores_imported_lines(temp_repo):
    """The measurement does not add lines from an imported file."""
    imported = temp_repo / "AGENTS.md"
    imported.write_text("# Imported\n" + ("line\n" * 300))
    claude_md = temp_repo / "CLAUDE.md"
    claude_md.write_text("# Test\n\n@AGENTS.md\n")

    result = measure_claude_md_single_file(claude_md)

    assert result.passed
    assert result.details["lineCount"] == 3


def test_claude_md_single_file_measurement_has_no_200_line_failure(temp_repo):
    """A large CLAUDE.md remains a measurement, not a vendor violation."""
    claude_md = temp_repo / "CLAUDE.md"
    claude_md.write_text("# Test\n" + ("line\n" * 250))

    result = measure_claude_md_single_file(claude_md)

    assert result.passed
    assert result.severity == "none"
    assert result.details["lineCount"] == 251


def test_claude_md_not_found():
    """Test missing CLAUDE.md fails."""
    result = measure_claude_md_single_file(Path("/nonexistent/CLAUDE.md"))

    assert not result.passed
    assert result.severity == "error"


def test_no_imports(temp_repo):
    """Test CLAUDE.md with no imports passes."""
    claude_md = temp_repo / "CLAUDE.md"
    claude_md.write_text("# Test\nNo imports here")

    result = check_imported_files_exist(claude_md, temp_repo)

    assert result.passed
    assert "No @imports found" in result.message


def test_imports_exist(temp_repo):
    """Test all imported files exist passes."""
    (temp_repo / "CRITICAL-CONTEXT.md").write_text("# Critical")
    (temp_repo / "SKILL-QUICK-REF.md").write_text("# Skills")

    claude_md = temp_repo / "CLAUDE.md"
    claude_md.write_text("# Test\n@CRITICAL-CONTEXT.md\n@SKILL-QUICK-REF.md")

    result = check_imported_files_exist(claude_md, temp_repo)

    assert result.passed


def test_import_missing(temp_repo):
    """Test missing imported file fails."""
    claude_md = temp_repo / "CLAUDE.md"
    claude_md.write_text("# Test\n@MISSING-FILE.md")

    result = check_imported_files_exist(claude_md, temp_repo)

    assert not result.passed
    assert "not found" in result.message


def test_passive_context_knowledge_only(temp_repo):
    """Test file with only knowledge passes."""
    file = temp_repo / "KNOWLEDGE.md"
    file.write_text(
        """# Knowledge Document

| Pattern | Description |
|---------|-------------|
| Strategy | Behavioral pattern |
"""
    )

    result = check_passive_context_knowledge_only(file)

    assert result.passed


def test_passive_context_has_actions(temp_repo):
    """Test file with action patterns warns."""
    file = temp_repo / "DOCS.md"
    file.write_text(
        """# Documentation

Run the following command:

```powershell
pwsh ./scripts/Deploy.ps1
```
"""
    )

    result = check_passive_context_knowledge_only(file)

    assert not result.passed
    assert result.severity == "warning"


def test_skill_has_powershell_scripts(temp_repo):
    """Test skill with PowerShell scripts passes."""
    skill_dir = temp_repo / ".claude" / "skills" / "test-skill"
    skill_dir.mkdir(parents=True)

    (skill_dir / "SKILL.md").write_text(
        """---
name: test-skill
description: Test skill
---

# Test Skill

This skill executes scripts.
"""
    )

    scripts_dir = skill_dir / "scripts"
    scripts_dir.mkdir()
    (scripts_dir / "Deploy.py").write_text("# Script")

    result = check_skill_has_actions(skill_dir)

    assert result.passed


def test_skill_has_action_verbs(temp_repo):
    """Test skill with action verbs passes."""
    skill_dir = temp_repo / ".claude" / "skills" / "test-skill"
    skill_dir.mkdir(parents=True)

    (skill_dir / "SKILL.md").write_text(
        """---
name: test-skill
description: Test skill
---

# Test Skill

This skill will:
- Create resources
- Update configurations
- Delete artifacts
"""
    )

    result = check_skill_has_actions(skill_dir)

    assert result.passed


def test_skill_no_actions(temp_repo):
    """Test skill with no action indicators warns."""
    skill_dir = temp_repo / ".claude" / "skills" / "test-skill"
    skill_dir.mkdir(parents=True)

    (skill_dir / "SKILL.md").write_text(
        """---
name: test-skill
description: Test skill
---

# Test Skill

This is just reference documentation.
"""
    )

    result = check_skill_has_actions(skill_dir)

    assert not result.passed
    assert result.severity == "warning"


def test_valid_frontmatter(temp_repo):
    """Test skill with valid frontmatter passes."""
    skill_dir = temp_repo / ".claude" / "skills" / "test-skill"
    skill_dir.mkdir(parents=True)

    (skill_dir / "SKILL.md").write_text(
        """---
name: test-skill
description: A test skill
---

# Test Skill
"""
    )

    result = check_skill_frontmatter(skill_dir)

    assert result.passed


def test_missing_frontmatter(temp_repo):
    """Test skill without frontmatter fails."""
    skill_dir = temp_repo / ".claude" / "skills" / "test-skill"
    skill_dir.mkdir(parents=True)

    (skill_dir / "SKILL.md").write_text("# Test Skill\n\nNo frontmatter here.")

    result = check_skill_frontmatter(skill_dir)

    assert not result.passed


def test_missing_name_field(temp_repo):
    """Test skill without name field fails."""
    skill_dir = temp_repo / ".claude" / "skills" / "test-skill"
    skill_dir.mkdir(parents=True)

    (skill_dir / "SKILL.md").write_text(
        """---
description: Test skill
---

# Test Skill
"""
    )

    result = check_skill_frontmatter(skill_dir)

    assert not result.passed
    assert "name" in result.message.lower()


def test_invalid_name_format(temp_repo):
    """Test skill with invalid name format fails."""
    skill_dir = temp_repo / ".claude" / "skills" / "test-skill"
    skill_dir.mkdir(parents=True)

    (skill_dir / "SKILL.md").write_text(
        """---
name: Test_Skill_123
description: Test skill
---

# Test Skill
"""
    )

    result = check_skill_frontmatter(skill_dir)

    assert not result.passed
    assert "Invalid name format" in result.message


def test_no_duplicates(temp_repo):
    """Test no duplicate content passes."""
    skill_dir = temp_repo / ".claude" / "skills" / "test-skill"
    skill_dir.mkdir(parents=True)

    (skill_dir / "SKILL.md").write_text(
        """---
name: test-skill
description: Test skill
---

# Test Skill

This skill does something unique.
"""
    )

    claude_md = temp_repo / "CLAUDE.md"
    claude_md.write_text("# Project\n\nCompletely different content.")

    result = check_no_duplicate_content(skill_dir, [claude_md])

    assert result.passed


def test_duplicate_content_found(temp_repo):
    """Test duplicate phrases are detected."""
    duplicate_phrase = "This is a very specific and unique phrase that appears in both documents"

    skill_dir = temp_repo / ".claude" / "skills" / "test-skill"
    skill_dir.mkdir(parents=True)

    (skill_dir / "SKILL.md").write_text(
        f"""---
name: test-skill
description: Test skill
---

# Test Skill

{duplicate_phrase}
"""
    )

    claude_md = temp_repo / "CLAUDE.md"
    claude_md.write_text(f"# Project\n\n{duplicate_phrase}")

    result = check_no_duplicate_content(skill_dir, [claude_md])

    assert not result.passed
    assert result.severity == "warning"


def test_full_compliance_check_passes(temp_repo, monkeypatch):
    """Test full compliance check with all passing."""
    monkeypatch.chdir(temp_repo)

    claude_md = temp_repo / "CLAUDE.md"
    claude_md.write_text("# Test\n" + ("line\n" * 50))

    skill_dir = temp_repo / ".claude" / "skills" / "test-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        """---
name: test-skill
description: Test skill with actions
---

Execute: pwsh ./Deploy.ps1
"""
    )

    results = run_compliance_checks(Path(".claude"), Path("CLAUDE.md"))

    assert results.summary["failed"] == 0


def test_full_compliance_check_does_not_fail_large_claude_md(temp_repo, monkeypatch):
    """A large CLAUDE.md is measured without a vendor-limit violation."""
    monkeypatch.chdir(temp_repo)
    (temp_repo / "CLAUDE.md").write_text("# Test\n" + ("line\n" * 250))

    results = run_compliance_checks(Path(".claude"), Path("CLAUDE.md"))

    assert results.summary["failed"] == 0
    assert results.summary["measurements"] == 1
    assert results.scope["claudeMdMeasurementResult"]["lineCount"] == 251


def test_full_compliance_check_missing_claude_md_fails(temp_repo, monkeypatch):
    """A missing CLAUDE.md remains a compliance violation."""
    monkeypatch.chdir(temp_repo)

    results = run_compliance_checks(Path(".claude"), Path("CLAUDE.md"))

    assert results.summary["failed"] > 0
    assert len(results.violations) > 0


def test_action_light_skill_is_never_recommended_for_an_always_on_slot(temp_repo):
    """Issue #3936: an action-light skill routes to disclosure or deletion.

    The old text said "consider moving <skill> to passive context", which
    inverts the Decision Framework: a skill with nothing to execute is a
    candidate for progressive disclosure or removal, never for promotion to
    an always-on slot. The replacement must also cite a document that exists,
    and SKILL-QUICK-REF.md was deleted in #1120.
    """
    skills_dir = temp_repo / "skills"
    quiet_skill = skills_dir / "quiet-skill"
    quiet_skill.mkdir(parents=True)
    (quiet_skill / "SKILL.md").write_text(
        "---\n"
        "name: quiet-skill\n"
        "version: 1.0.0\n"
        "description: Knowledge only\n"
        "---\n\n"
        "# Quiet Skill\n\n"
        "| Term | Meaning |\n"
        "|---|---|\n"
        "| alpha | first |\n"
    )
    claude_md = temp_repo / "CLAUDE.md"
    claude_md.write_text("# Test\n")

    results = run_compliance_checks(skills_dir, claude_md)

    promotions = [
        rec
        for rec in results.recommendations
        if "quiet-skill" in rec and "to passive context" in rec
    ]
    assert promotions == []

    advice = [
        rec for rec in results.recommendations if "quiet-skill" in rec and "no actions" in rec
    ]
    assert len(advice) == 1
    assert "progressive disclosure" in advice[0]
    assert "SKILL-QUICK-REF" not in advice[0]
    assert "Decision Framework" in advice[0]
