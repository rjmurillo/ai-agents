"""Tests for test_skill_passive_compliance.py."""

import sys
import tempfile
from pathlib import Path

import pytest

# Add scripts directory to path
sys.path.insert(
    0, str(Path(__file__).parent.parent / "scripts")
)

from test_skill_passive_compliance import (
    check_claude_md_line_count,
    check_imported_files_exist,
    check_no_duplicate_content,
    check_passive_context_knowledge_only,
    check_skill_frontmatter,
    check_skill_has_actions,
    run_compliance_checks,
)


@pytest.fixture
def temp_repo():
    """Create a temporary git repository for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir)
        (repo_path / ".git").mkdir()
        yield repo_path


def test_claude_md_line_count_under_150(temp_repo):
    """Test CLAUDE.md with under 150 lines passes."""
    claude_md = temp_repo / "CLAUDE.md"
    claude_md.write_text("# Test\n" + ("line\n" * 100))

    result = check_claude_md_line_count(claude_md)

    assert result.passed
    assert result.severity == "none"


def test_claude_md_line_count_150_to_200(temp_repo):
    """Test CLAUDE.md between 150-200 lines warns."""
    claude_md = temp_repo / "CLAUDE.md"
    claude_md.write_text("# Test\n" + ("line\n" * 160))

    result = check_claude_md_line_count(claude_md)

    assert result.passed
    assert result.severity == "warning"


def test_claude_md_line_count_over_200(temp_repo):
    """Test CLAUDE.md over 200 lines fails."""
    claude_md = temp_repo / "CLAUDE.md"
    claude_md.write_text("# Test\n" + ("line\n" * 250))

    result = check_claude_md_line_count(claude_md)

    assert not result.passed
    assert result.severity == "error"
    assert "exceeds 200 limit" in result.message


def test_claude_md_not_found():
    """Test missing CLAUDE.md fails."""
    result = check_claude_md_line_count(Path("/nonexistent/CLAUDE.md"))

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
    claude_md.write_text(
        "# Test\n@CRITICAL-CONTEXT.md\n@SKILL-QUICK-REF.md"
    )

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
    duplicate_phrase = (
        "This is a very specific and unique phrase that appears in both documents"
    )

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


def test_full_compliance_check_violations(temp_repo, monkeypatch):
    """Test full compliance check with violations."""
    monkeypatch.chdir(temp_repo)

    claude_md = temp_repo / "CLAUDE.md"
    claude_md.write_text("# Test\n" + ("line\n" * 250))

    results = run_compliance_checks(Path(".claude"), Path("CLAUDE.md"))

    assert results.summary["failed"] > 0
    assert len(results.violations) > 0
