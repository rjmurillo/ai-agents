"""Tests for SkillForge validate-skill.py structural validator.

Covers P0 remediation items from critique review (issue #1380):
- P0-2: Description word count validation
- P0-3: Trigger phrase character validation (CWE-94)
- P0-2 (threshold): Trigger count range alignment (1-5 not 3-5)
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from typing import Any

# Add the SkillForge scripts directory to the import path
_scripts_dir = os.path.join(
    os.path.dirname(__file__),
    "..",
    ".claude",
    "skills",
    "SkillForge",
    "scripts",
)
sys.path.insert(0, os.path.abspath(_scripts_dir))

# Import uses hyphenated filename, so use importlib
_spec = importlib.util.spec_from_file_location(
    "validate_skill",
    os.path.join(os.path.abspath(_scripts_dir), "validate-skill.py"),
)
assert _spec is not None and _spec.loader is not None
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
SkillValidator = _mod.SkillValidator


def _make_skill(tmp_path: Path, content: str) -> Any:
    """Create a skill directory with SKILL.md and return a validator."""
    skill_dir = tmp_path / "test-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")
    # Change to tmp_path so CWE-22 path check passes
    orig = os.getcwd()
    os.chdir(tmp_path)
    try:
        validator = SkillValidator(str(skill_dir))
    finally:
        os.chdir(orig)
    return validator


# ---------------------------------------------------------------------------
# P0-2: Description word count validation
# ---------------------------------------------------------------------------


class TestDescriptionWordCount:
    """Verify minimum word count check on description field."""

    def test_short_description_fails(self, tmp_path: Path) -> None:
        content = (
            "---\nname: test-skill\ndescription: Too short\n---\n"
            "# Title\n## Triggers\n`one` `two` `three`\n"
            "## Process\nSteps.\n## Verification\n- [ ] a\n- [ ] b\n"
        )
        v = _make_skill(tmp_path, content)
        v.load_skill()
        v.parse_frontmatter()
        v.validate_frontmatter()
        assert any("too short" in e.lower() for e in v.errors), (
            f"Expected word count error, got: {v.errors}"
        )

    def test_adequate_description_passes(self, tmp_path: Path) -> None:
        content = (
            "---\nname: test-skill\n"
            "description: This is a valid description with enough words\n"
            "---\n# Title\n## Triggers\n`one` `two` `three`\n"
            "## Process\nSteps.\n## Verification\n- [ ] a\n- [ ] b\n"
        )
        v = _make_skill(tmp_path, content)
        v.load_skill()
        v.parse_frontmatter()
        v.validate_frontmatter()
        word_errors = [e for e in v.errors if "word" in e.lower()]
        assert not word_errors, f"Unexpected word count error: {word_errors}"

    def test_exactly_five_words_passes(self, tmp_path: Path) -> None:
        content = "---\nname: test-skill\ndescription: One two three four five\n---\n# Title\n"
        v = _make_skill(tmp_path, content)
        v.load_skill()
        v.parse_frontmatter()
        v.validate_frontmatter()
        word_errors = [e for e in v.errors if "word" in e.lower()]
        assert not word_errors

    def test_four_words_fails(self, tmp_path: Path) -> None:
        content = "---\nname: test-skill\ndescription: One two three four\n---\n# Title\n"
        v = _make_skill(tmp_path, content)
        v.load_skill()
        v.parse_frontmatter()
        v.validate_frontmatter()
        assert any("4 words" in e for e in v.errors)


# ---------------------------------------------------------------------------
# P0-3: Trigger phrase character validation (CWE-94)
# ---------------------------------------------------------------------------


class TestTriggerCharacterValidation:
    """Verify unsafe characters in trigger phrases are rejected."""

    def test_safe_triggers_pass(self, tmp_path: Path) -> None:
        content = (
            "---\nname: test-skill\ndescription: A valid skill for testing triggers\n---\n"
            "# Title\n## Triggers\n`run tests` `check quality` `validate code`\n"
            "## Process\nSteps.\n## Verification\n- [ ] a\n- [ ] b\n"
        )
        v = _make_skill(tmp_path, content)
        v.load_skill()
        v.parse_frontmatter()
        v.validate_triggers()
        char_errors = [e for e in v.errors if "unsafe characters" in e]
        assert not char_errors, f"Unexpected error: {char_errors}"

    def test_injection_backtick_content_rejected(self, tmp_path: Path) -> None:
        content = (
            "---\nname: test-skill\ndescription: A valid skill for testing triggers\n---\n"
            "# Title\n## Triggers\n`safe phrase` `; rm -rf /` `another safe`\n"
            "## Process\nSteps.\n## Verification\n- [ ] a\n- [ ] b\n"
        )
        v = _make_skill(tmp_path, content)
        v.load_skill()
        v.parse_frontmatter()
        v.validate_triggers()
        assert any("unsafe characters" in e for e in v.errors), (
            f"Expected unsafe character error, got: {v.errors}"
        )

    def test_shell_metacharacters_rejected(self, tmp_path: Path) -> None:
        content = (
            "---\nname: test-skill\ndescription: A valid skill for testing triggers\n---\n"
            "# Title\n## Triggers\n`run && exploit` `pipe | attack` `$(command)`\n"
            "## Process\nSteps.\n## Verification\n- [ ] a\n- [ ] b\n"
        )
        v = _make_skill(tmp_path, content)
        v.load_skill()
        v.parse_frontmatter()
        v.validate_triggers()
        assert any("unsafe characters" in e for e in v.errors)


# ---------------------------------------------------------------------------
# Trigger count threshold alignment (1-5 instead of 3-5)
# ---------------------------------------------------------------------------


class TestTriggerCountThreshold:
    """Verify trigger count accepts 1-5 range per standard alignment."""

    def test_single_trigger_passes(self, tmp_path: Path) -> None:
        content = (
            "---\nname: test-skill\ndescription: A valid skill for testing triggers\n---\n"
            "# Title\n## Triggers\n`single trigger phrase`\n"
            "## Process\nSteps.\n## Verification\n- [ ] a\n- [ ] b\n"
        )
        v = _make_skill(tmp_path, content)
        v.load_skill()
        v.parse_frontmatter()
        v.validate_triggers()
        count_errors = [e for e in v.errors if "trigger phrases" in e]
        assert not count_errors, f"Single trigger should pass: {count_errors}"

    def test_two_triggers_pass(self, tmp_path: Path) -> None:
        content = (
            "---\nname: test-skill\ndescription: A valid skill for testing triggers\n---\n"
            "# Title\n## Triggers\n`first trigger` `second trigger`\n"
            "## Process\nSteps.\n## Verification\n- [ ] a\n- [ ] b\n"
        )
        v = _make_skill(tmp_path, content)
        v.load_skill()
        v.parse_frontmatter()
        v.validate_triggers()
        count_errors = [e for e in v.errors if "trigger phrases" in e]
        assert not count_errors

    def test_five_triggers_pass(self, tmp_path: Path) -> None:
        content = (
            "---\nname: test-skill\ndescription: A valid skill for testing triggers\n---\n"
            "# Title\n## Triggers\n`a` `b` `c` `d` `e`\n"
            "## Process\nSteps.\n## Verification\n- [ ] a\n- [ ] b\n"
        )
        v = _make_skill(tmp_path, content)
        v.load_skill()
        v.parse_frontmatter()
        v.validate_triggers()
        count_errors = [e for e in v.errors if "trigger phrases" in e]
        assert not count_errors

    def test_six_triggers_fail(self, tmp_path: Path) -> None:
        content = (
            "---\nname: test-skill\ndescription: A valid skill for testing triggers\n---\n"
            "# Title\n## Triggers\n`a` `b` `c` `d` `e` `f`\n"
            "## Process\nSteps.\n## Verification\n- [ ] a\n- [ ] b\n"
        )
        v = _make_skill(tmp_path, content)
        v.load_skill()
        v.parse_frontmatter()
        v.validate_triggers()
        assert any("1-5" in e for e in v.errors)

    def test_zero_triggers_fail(self, tmp_path: Path) -> None:
        content = (
            "---\nname: test-skill\ndescription: A valid skill for testing triggers\n---\n"
            "# Title\n## Triggers\nNo backtick phrases here.\n"
            "## Process\nSteps.\n## Verification\n- [ ] a\n- [ ] b\n"
        )
        v = _make_skill(tmp_path, content)
        v.load_skill()
        v.parse_frontmatter()
        v.validate_triggers()
        assert any("1-5" in e for e in v.errors)


# ---------------------------------------------------------------------------
# size-exception frontmatter property acceptance (skill_size escape hatch)
# ---------------------------------------------------------------------------


class TestSizeExceptionProperty:
    """The `size-exception` escape hatch must pass frontmatter allow-listing.

    The blocking `scripts/validation/skill_size.py` gate requires a top-level
    `size-exception: true` to exempt a >500-line SKILL.md, so the structural
    validator must accept that key. Otherwise the two blocking gates deadlock
    and no oversized skill can be committed.
    """

    def test_size_exception_true_is_allowed(self, tmp_path: Path) -> None:
        content = (
            "---\nname: test-skill\n"
            "description: A valid skill declaring a justified size exception\n"
            "size-exception: true\n---\n"
            "# Title\n## Process\nSteps.\n## Verification\n- [ ] a\n"
        )
        v = _make_skill(tmp_path, content)
        v.load_skill()
        v.parse_frontmatter()
        v.validate_frontmatter()
        unexpected = [e for e in v.errors if "Unexpected frontmatter" in e]
        assert not unexpected, f"size-exception should be allowed, got: {v.errors}"

    def test_unknown_property_still_rejected(self, tmp_path: Path) -> None:
        content = (
            "---\nname: test-skill\n"
            "description: A valid skill with an unknown frontmatter property\n"
            "not-a-real-key: true\n---\n"
            "# Title\n## Process\nSteps.\n## Verification\n- [ ] a\n"
        )
        v = _make_skill(tmp_path, content)
        v.load_skill()
        v.parse_frontmatter()
        v.validate_frontmatter()
        assert any("Unexpected frontmatter" in e for e in v.errors), (
            f"unknown key must still be rejected, got: {v.errors}"
        )
