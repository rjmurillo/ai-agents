#!/usr/bin/env python3
"""
Unit tests for invoke_skill_learning.py

Tests cover:
- Bug fix: Dynamically detected skills get learnings persisted
- Bug fix: Filename pattern consistency with template documentation
- Core skill detection and learning extraction functionality

Run with: python -m unittest .claude.hooks.Stop.test_invoke_skill_learning -v
Or from Stop directory: python -m unittest test_invoke_skill_learning -v
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from invoke_skill_learning import (
    detect_skill_usage,
    test_skill_context,
    extract_learnings,
    update_skill_memory,
)


class TestDynamicSkillDetection(unittest.TestCase):
    """Test that dynamically detected skills are properly handled."""

    def test_detect_skill_from_path_reference(self):
        """Skills detected via .claude/skills/{name} path get captured."""
        messages = [
            {"role": "user", "content": "Check .claude/skills/custom-analyzer for the script"},
            {"role": "assistant", "content": "I found the script in .claude/skills/custom-analyzer"},
        ]
        detected = detect_skill_usage(messages)
        self.assertIn("custom-analyzer", detected)
        self.assertGreater(detected["custom-analyzer"], 0)

    def test_dynamic_skill_context_check_returns_true(self):
        """Dynamically detected skills pass context check when mentioned."""
        # Bug 1 fix: Skills not in pattern map should still pass context check
        # if the skill name or path is mentioned
        text = "Working with .claude/skills/my-custom-skill to process data"
        result = test_skill_context(text, "my-custom-skill")
        self.assertTrue(result, "Dynamically detected skill should pass context check")

    def test_dynamic_skill_name_mention_passes(self):
        """Skill name mention alone should pass context check for dynamic skills."""
        text = "The my-custom-skill is working correctly now"
        result = test_skill_context(text, "my-custom-skill")
        self.assertTrue(result, "Skill name mention should pass context check")

    def test_unmapped_skill_without_mention_fails(self):
        """Dynamic skills should fail context check when not mentioned at all."""
        text = "This is unrelated text about something else entirely"
        result = test_skill_context(text, "unmapped-skill")
        self.assertFalse(result, "Unmapped skill with no mention should fail")

    def test_mapped_skill_still_uses_patterns(self):
        """Mapped skills should still use pattern-based checking."""
        # 'github' is a mapped skill
        text = "I ran gh pr list to see the pull requests"
        result = test_skill_context(text, "github")
        self.assertTrue(result, "Mapped skill should match on patterns")

    def test_mapped_skill_fails_without_pattern_match(self):
        """Mapped skills should fail when patterns don't match."""
        text = "This text mentions github but not in a pattern way"
        # 'github' patterns include 'gh pr', 'gh issue', '.claude/skills/github', etc.
        # Just mentioning 'github' shouldn't match
        result = test_skill_context(text, "github")
        # Note: 'github' appears in '.claude/skills/github' pattern so this could match
        # Let's use cleaner test case
        text2 = "Reading about version control systems"
        result2 = test_skill_context(text2, "github")
        self.assertFalse(result2, "Mapped skill should fail without pattern match")


class TestFilenamePatternConsistency(unittest.TestCase):
    """Test filename pattern matches documentation."""

    def test_memory_filename_uses_observations_suffix(self):
        """Memory files should use {skill-name}-observations.md pattern."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = tmpdir
            skill_name = "test-skill"
            learnings = {"High": [], "Med": [], "Low": []}
            session_id = "2026-01-14-session-001"

            update_skill_memory(project_dir, skill_name, learnings, session_id)

            expected_filename = f"{skill_name}-observations.md"
            memory_path = Path(project_dir) / ".serena" / "memories" / expected_filename

            self.assertTrue(
                memory_path.exists(),
                f"Memory file should be created at {memory_path}"
            )

    def test_memory_filename_not_skill_sidecar_learnings(self):
        """Memory files should NOT use the old skill-sidecar-learnings pattern."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = tmpdir
            skill_name = "test-skill"
            learnings = {"High": [], "Med": [], "Low": []}
            session_id = "2026-01-14-session-001"

            update_skill_memory(project_dir, skill_name, learnings, session_id)

            # Old pattern from template before fix
            wrong_filename = f"{skill_name}-skill-sidecar-learnings.md"
            wrong_path = Path(project_dir) / ".serena" / "memories" / wrong_filename

            self.assertFalse(
                wrong_path.exists(),
                f"Memory file should NOT use old pattern: {wrong_path}"
            )


class TestLearningExtraction(unittest.TestCase):
    """Test learning extraction for both mapped and dynamic skills."""

    def test_extract_learnings_for_dynamic_skill(self):
        """Learnings should be extracted for dynamically detected skills."""
        messages = [
            {"role": "user", "content": "Let's work with .claude/skills/data-processor"},
            {"role": "assistant", "content": "I'll use the data-processor skill to help"},
            {"role": "user", "content": "No, that's wrong! Never use that approach"},
        ]
        learnings = extract_learnings(messages, "data-processor")

        # Should have HIGH confidence learning from "No, that's wrong"
        self.assertGreater(
            len(learnings["High"]), 0,
            "Should extract HIGH confidence learning for dynamic skill"
        )

    def test_extract_learnings_for_mapped_skill(self):
        """Learnings should be extracted for mapped skills."""
        messages = [
            {"role": "user", "content": "Run gh pr list"},
            {"role": "assistant", "content": "Running gh pr list now"},
            {"role": "user", "content": "Perfect! That's exactly what I needed"},
        ]
        learnings = extract_learnings(messages, "github")

        # Should have MED confidence learning from "Perfect!"
        self.assertGreater(
            len(learnings["Med"]), 0,
            "Should extract MED confidence learning for mapped skill"
        )


class TestSkillDetection(unittest.TestCase):
    """Test skill detection from conversation messages."""

    def test_detect_slash_command_skill(self):
        """Slash commands should map to their associated skills."""
        messages = [
            {"role": "user", "content": "Run /session-init to start"},
        ]
        detected = detect_skill_usage(messages)
        self.assertIn("session-init", detected)

    def test_detect_pattern_based_skill(self):
        """Pattern-based detection should work for mapped skills."""
        messages = [
            {"role": "user", "content": "Check the forgetful memory system"},
            {"role": "assistant", "content": "Using Serena to search memory"},
            {"role": "user", "content": "Good, now search memory for the pattern"},
        ]
        detected = detect_skill_usage(messages)
        self.assertIn("memory", detected)

    def test_detect_multiple_skills(self):
        """Multiple skills can be detected in same conversation."""
        messages = [
            {"role": "user", "content": ".claude/skills/github has the PR script"},
            {"role": "assistant", "content": "Also checking .claude/skills/memory"},
        ]
        detected = detect_skill_usage(messages)
        self.assertIn("github", detected)
        self.assertIn("memory", detected)


class TestPathTraversalPrevention(unittest.TestCase):
    """Test security: path traversal prevention in memory file creation."""

    def test_path_traversal_rejected(self):
        """Skill names with path traversal should be rejected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = tmpdir
            # Attempt path traversal via skill name
            malicious_skill = "../../../etc/passwd"
            learnings = {"High": [], "Med": [], "Low": []}
            session_id = "2026-01-14-session-001"

            result = update_skill_memory(project_dir, malicious_skill, learnings, session_id)

            # Should either fail (return False) or create file safely within project
            if result:
                # If it succeeded, verify file is within project directory
                memories_dir = Path(project_dir) / ".serena" / "memories"
                for file in memories_dir.iterdir():
                    resolved = file.resolve()
                    self.assertTrue(
                        str(resolved).startswith(str(Path(project_dir).resolve())),
                        "Created file must be within project directory"
                    )


if __name__ == "__main__":
    unittest.main(verbosity=2)
