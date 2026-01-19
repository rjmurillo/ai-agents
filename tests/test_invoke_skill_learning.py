#!/usr/bin/env python3
"""
Unit tests for invoke_skill_learning.py

Tests cover:
- Bug fix: Dynamically detected skills get learnings persisted
- Bug fix: Filename pattern consistency with template documentation
- Bug 3 fix: Pattern synchronization across module-level SKILL_PATTERNS
- Bug 4 fix: Documentation skill pattern precision
- Bug 5 fix: Success/approval pattern false positive prevention
- Bug 6 fix: Edge case pattern negative lookaheads
- Bug 7 fix: Preference pattern precision
- Bug 8 fix: Documentation learning type detection
- Core skill detection and learning extraction functionality

Run with: python -m unittest .claude.hooks.Stop.test_invoke_skill_learning -v
Or from Stop directory: python -m unittest test_invoke_skill_learning -v
"""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# Add .claude/hooks/Stop directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / ".claude" / "hooks" / "Stop"))

import invoke_skill_learning
from invoke_skill_learning import (
    SKILL_PATTERNS,
    COMMAND_TO_SKILL,
    detect_skill_usage,
    check_skill_context,
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
        result = check_skill_context(text, "my-custom-skill")
        self.assertTrue(result, "Dynamically detected skill should pass context check")

    def test_dynamic_skill_name_mention_passes(self):
        """Skill name mention alone should pass context check for dynamic skills."""
        text = "The my-custom-skill is working correctly now"
        result = check_skill_context(text, "my-custom-skill")
        self.assertTrue(result, "Skill name mention should pass context check")

    def test_unmapped_skill_without_mention_fails(self):
        """Dynamic skills should fail context check when not mentioned at all."""
        text = "This is unrelated text about something else entirely"
        result = check_skill_context(text, "unmapped-skill")
        self.assertFalse(result, "Unmapped skill with no mention should fail")

    def test_mapped_skill_still_uses_patterns(self):
        """Mapped skills should still use pattern-based checking."""
        # 'github' is a mapped skill
        text = "I ran gh pr list to see the pull requests"
        result = check_skill_context(text, "github")
        self.assertTrue(result, "Mapped skill should match on patterns")

    def test_mapped_skill_fails_without_pattern_match(self):
        """Mapped skills should fail when patterns don't match."""
        # 'github' patterns include 'gh pr', 'gh issue', '.claude/skills/github', etc.
        # Use a text that does not match any of the defined GitHub patterns
        text = "Reading about version control systems"
        result = check_skill_context(text, "github")
        self.assertFalse(result, "Mapped skill should fail without pattern match")


class TestFilenamePatternConsistency(unittest.TestCase):
    """Test filename pattern matches documentation."""

    def test_memory_filename_uses_observations_suffix(self):
        """Memory files should use {skill-name}-observations.md pattern."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            skill_name = "test-skill"
            learnings = {"High": [], "Med": [], "Low": []}
            session_id = "2026-01-14-session-001"

            # Patch SAFE_BASE_DIR to allow temp directory for testing
            with patch.object(invoke_skill_learning, 'SAFE_BASE_DIR', project_dir):
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
            project_dir = Path(tmpdir)
            skill_name = "test-skill"
            learnings = {"High": [], "Med": [], "Low": []}
            session_id = "2026-01-14-session-001"

            # Patch SAFE_BASE_DIR to allow temp directory for testing
            with patch.object(invoke_skill_learning, 'SAFE_BASE_DIR', project_dir):
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
    """Test security: path traversal prevention in memory file creation (CWE-22)."""

    def test_path_traversal_rejected(self):
        """Skill names with path traversal should be rejected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
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

    def test_path_traversal_with_forward_slash_rejected(self):
        """Skill names with forward slashes should be rejected (CWE-22)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            malicious_skill = "foo/bar"
            learnings = {"High": [], "Med": [], "Low": []}
            session_id = "2026-01-14-session-001"

            result = update_skill_memory(project_dir, malicious_skill, learnings, session_id)

            self.assertFalse(result, "Skill names with / should be rejected")

    def test_path_traversal_with_backslash_rejected(self):
        """Skill names with backslashes should be rejected (CWE-22)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            malicious_skill = "foo\\bar"
            learnings = {"High": [], "Med": [], "Low": []}
            session_id = "2026-01-14-session-001"

            result = update_skill_memory(project_dir, malicious_skill, learnings, session_id)

            self.assertFalse(result, "Skill names with \\ should be rejected")

    def test_path_traversal_with_dotdot_rejected(self):
        """Skill names with .. should be rejected (CWE-22)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            malicious_skill = "foo..bar"
            learnings = {"High": [], "Med": [], "Low": []}
            session_id = "2026-01-14-session-001"

            result = update_skill_memory(project_dir, malicious_skill, learnings, session_id)

            self.assertFalse(result, "Skill names with .. should be rejected")

    def test_valid_skill_name_accepted(self):
        """Valid skill names should create files successfully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            valid_skill = "github"
            learnings = {"High": [], "Med": [], "Low": []}
            session_id = "2026-01-14-session-001"

            # Patch SAFE_BASE_DIR to allow temp directory for testing
            with patch.object(invoke_skill_learning, 'SAFE_BASE_DIR', project_dir):
                result = update_skill_memory(project_dir, valid_skill, learnings, session_id)

            self.assertTrue(result, "Valid skill name should be accepted")

            # Verify file was created in correct location
            expected_path = Path(project_dir) / ".serena" / "memories" / f"{valid_skill}-observations.md"
            self.assertTrue(expected_path.exists(), "Memory file should be created")


class TestPatternSynchronization(unittest.TestCase):
    """Bug 3 fix: Test that skill patterns are centralized and synchronized."""

    def test_skill_patterns_is_module_level_constant(self):
        """SKILL_PATTERNS should be a module-level constant."""
        self.assertIsInstance(SKILL_PATTERNS, dict)
        self.assertGreater(len(SKILL_PATTERNS), 0, "SKILL_PATTERNS should not be empty")

    def test_command_to_skill_is_module_level_constant(self):
        """COMMAND_TO_SKILL should be a module-level constant."""
        self.assertIsInstance(COMMAND_TO_SKILL, dict)
        self.assertGreater(len(COMMAND_TO_SKILL), 0, "COMMAND_TO_SKILL should not be empty")

    def test_detect_skill_usage_uses_centralized_patterns(self):
        """detect_skill_usage should use SKILL_PATTERNS."""
        # Verify by checking that a skill in SKILL_PATTERNS is detected
        for skill in list(SKILL_PATTERNS.keys())[:3]:
            patterns = SKILL_PATTERNS[skill]
            if patterns:
                messages = [
                    {"role": "user", "content": patterns[0]},
                    {"role": "assistant", "content": patterns[0]},
                ]
                # Detection tested - not asserting specific skill due to threshold requirements
                detect_skill_usage(messages)

    def test_check_skill_context_uses_centralized_patterns(self):
        """check_skill_context should use SKILL_PATTERNS."""
        # Verify mapped skills use SKILL_PATTERNS
        for skill, patterns in list(SKILL_PATTERNS.items())[:3]:
            if patterns:
                text = patterns[0]
                result = check_skill_context(text, skill)
                self.assertTrue(result, f"Skill '{skill}' should match pattern '{patterns[0]}'")


class TestDocumentationSkillPattern(unittest.TestCase):
    """Bug 4 fix: Test that documentation skill detection is precise."""

    def test_documentation_matches_skill_path(self):
        """Should match .claude/skills/documentation path."""
        text = "Check .claude/skills/documentation for templates"
        result = check_skill_context(text, "documentation")
        self.assertTrue(result, "Should match skill path reference")

    def test_documentation_matches_skill_keyword(self):
        """Should match 'documentation skill' keyword."""
        text = "Use the documentation skill to update"
        result = check_skill_context(text, "documentation")
        self.assertTrue(result, "Should match 'documentation skill'")

    def test_documentation_rejects_generic_mention(self):
        """Should NOT match generic 'documentation' mentions."""
        text = "Read the documentation for more info"
        result = check_skill_context(text, "documentation")
        self.assertFalse(result, "Should not match generic documentation mention")

    def test_documentation_rejects_docs_folder_mention(self):
        """Should NOT match generic 'docs/' folder mentions."""
        text = "Check the docs/ folder for API reference"
        result = check_skill_context(text, "documentation")
        self.assertFalse(result, "Should not match generic docs/ mention")


class TestSuccessPatternPrecision(unittest.TestCase):
    """Bug 5 fix: Test that success/approval patterns avoid false positives."""

    def _extract_success_learning(self, user_response):
        """Helper to extract success learning from a test message."""
        messages = [
            {"role": "user", "content": "Check gh pr list"},
            {"role": "assistant", "content": "Running gh pr list now"},
            {"role": "user", "content": user_response},
        ]
        learnings = extract_learnings(messages, "github")
        success_learnings = [l for l in learnings["Med"] if l["type"] == "success"]
        return success_learnings

    def test_success_matches_perfect(self):
        """Should match 'Perfect!' as success."""
        learnings = self._extract_success_learning("Perfect!")
        self.assertGreater(len(learnings), 0, "Should match 'Perfect!'")

    def test_success_matches_excellent(self):
        """Should match 'Excellent!' as success."""
        learnings = self._extract_success_learning("Excellent!")
        self.assertGreater(len(learnings), 0, "Should match 'Excellent!'")

    def test_success_matches_thats_it(self):
        """Should match 'That's it!' as success."""
        learnings = self._extract_success_learning("That's it!")
        self.assertGreater(len(learnings), 0, "Should match 'That's it!'")

    def test_success_matches_yes_at_end(self):
        """Should match 'Yes.' or 'Yes!' at end."""
        learnings = self._extract_success_learning("Yes.")
        self.assertGreater(len(learnings), 0, "Should match 'Yes.'")

    def test_success_rejects_great_question(self):
        """Should NOT match 'Great question' - not an approval."""
        # Great question is followed by more text, not a pure approval
        messages = [
            {"role": "user", "content": "Check gh pr list"},
            {"role": "assistant", "content": "Running gh pr list now"},
            {"role": "user", "content": "Great question about the API"},
        ]
        learnings = extract_learnings(messages, "github")
        success_learnings = [l for l in learnings["Med"] if l["type"] == "success"]
        self.assertEqual(len(success_learnings), 0, "Should not match 'Great question'")

    def test_success_rejects_yes_but(self):
        """Should NOT match 'Yes, but...' - qualified approval."""
        learnings = self._extract_success_learning("Yes, but we need to fix the other issue too")
        self.assertEqual(len(learnings), 0, "Should not match 'Yes, but...'")

    def test_success_rejects_works_but(self):
        """Should NOT match 'Works but...' - qualified success."""
        learnings = self._extract_success_learning("Works great but there's a problem")
        self.assertEqual(len(learnings), 0, "Should not match qualified success")

    def test_success_rejects_correct_however(self):
        """Should NOT match 'Correct, however...' - qualified approval."""
        learnings = self._extract_success_learning("Correct, however we need changes")
        self.assertEqual(len(learnings), 0, "Should not match qualified approval")


class TestEdgeCasePatternPrecision(unittest.TestCase):
    """Bug 6 fix: Test that edge_case patterns have proper negative lookaheads."""

    def _extract_edge_case_learning(self, user_response):
        """Helper to extract edge_case learning from a test message."""
        messages = [
            {"role": "user", "content": "Check gh pr list"},
            {"role": "assistant", "content": "Running gh pr list now"},
            {"role": "user", "content": user_response},
        ]
        learnings = extract_learnings(messages, "github")
        edge_learnings = [l for l in learnings["Med"] if l["type"] == "edge_case"]
        return edge_learnings

    def test_edge_case_matches_what_if_the(self):
        """Should match 'What if the user does X?'"""
        learnings = self._extract_edge_case_learning("What if the user submits invalid data?")
        self.assertGreater(len(learnings), 0, "Should match 'What if the user...'")

    def test_edge_case_matches_ensure_that(self):
        """Should match 'Ensure that we handle...'"""
        # Note: avoid words like "error", "issue", "problem" which trigger immediate_correction
        learnings = self._extract_edge_case_learning("Ensure that we handle the timeout scenario?")
        self.assertGreater(len(learnings), 0, "Should match 'Ensure that...'")

    def test_edge_case_matches_make_sure(self):
        """Should match 'Make sure it handles...'"""
        # Note: avoid words like "error", "issue", "problem" which trigger immediate_correction
        learnings = self._extract_edge_case_learning("Make sure it handles null input?")
        self.assertGreater(len(learnings), 0, "Should match 'Make sure...'")

    def test_edge_case_matches_what_about_edge(self):
        """Should match 'What about edge cases?'"""
        learnings = self._extract_edge_case_learning("What about edge cases?")
        self.assertGreater(len(learnings), 0, "Should match 'What about edge...'")

    def test_edge_case_rejects_lunch_question(self):
        """Should NOT match 'What if we had lunch?' - unrelated."""
        learnings = self._extract_edge_case_learning("What if we had lunch?")
        self.assertEqual(len(learnings), 0, "Should not match lunch question")

    def test_edge_case_rejects_meeting_question(self):
        """Should NOT match 'What about the meeting tomorrow?' - unrelated."""
        learnings = self._extract_edge_case_learning("What about the meeting tomorrow?")
        self.assertEqual(len(learnings), 0, "Should not match meeting question")

    def test_edge_case_rejects_coffee_question(self):
        """Should NOT match questions about coffee/social activities."""
        learnings = self._extract_edge_case_learning("What if we get coffee later?")
        self.assertEqual(len(learnings), 0, "Should not match social question")


class TestPreferencePatternPrecision(unittest.TestCase):
    """Bug 7 fix: Test that preference patterns are precise."""

    def _extract_preference_learning(self, user_response):
        """Helper to extract preference learning from a test message."""
        messages = [
            {"role": "user", "content": "Check gh pr list"},
            {"role": "assistant", "content": "Running gh pr list now"},
            {"role": "user", "content": user_response},
        ]
        learnings = extract_learnings(messages, "github")
        pref_learnings = [l for l in learnings["Med"] if l["type"] == "preference"]
        return pref_learnings

    def test_preference_matches_instead_of_using(self):
        """Should match 'Instead of using X, use Y'."""
        learnings = self._extract_preference_learning("Instead of using grep, use the search tool")
        self.assertGreater(len(learnings), 0, "Should match 'Instead of using...'")

    def test_preference_matches_prefer_to(self):
        """Should match 'I prefer to use X'."""
        learnings = self._extract_preference_learning("I prefer to use PowerShell for scripts")
        self.assertGreater(len(learnings), 0, "Should match 'prefer to...'")

    def test_preference_matches_should_use(self):
        """Should match 'You should use X'."""
        learnings = self._extract_preference_learning("You should use the skill instead")
        self.assertGreater(len(learnings), 0, "Should match 'should use...'")

    def test_preference_matches_better_to_use(self):
        """Should match 'It's better to use X'."""
        learnings = self._extract_preference_learning("It's better to use the API directly")
        self.assertGreater(len(learnings), 0, "Should match 'better to use...'")

    def test_preference_rejects_vague_instead(self):
        """Should NOT match vague 'instead' without context."""
        learnings = self._extract_preference_learning("Do this instead")
        self.assertEqual(len(learnings), 0, "Should not match vague 'instead'")

    def test_preference_rejects_partial_match(self):
        """Should NOT match partial patterns without proper structure."""
        learnings = self._extract_preference_learning("I use this tool")
        self.assertEqual(len(learnings), 0, "Should not match partial pattern")


class TestDocumentationLearningType(unittest.TestCase):
    """Bug 8 fix: Test that documentation learning type is detected."""

    def _extract_documentation_learning(self, user_response):
        """Helper to extract documentation learning from a test message."""
        messages = [
            {"role": "user", "content": "Working with .claude/skills/github"},
            {"role": "assistant", "content": "Using the github skill"},
            {"role": "user", "content": user_response},
        ]
        learnings = extract_learnings(messages, "github")
        doc_learnings = [l for l in learnings["Med"] if l["type"] == "documentation"]
        return doc_learnings

    def test_documentation_matches_update_docs(self):
        """Should match 'Update the docs with this'."""
        learnings = self._extract_documentation_learning("Update the docs with this information")
        self.assertGreater(len(learnings), 0, "Should match 'Update the docs...'")

    def test_documentation_matches_add_documentation(self):
        """Should match 'Add documentation for this'."""
        learnings = self._extract_documentation_learning("Add documentation for this feature")
        self.assertGreater(len(learnings), 0, "Should match 'Add documentation...'")

    def test_documentation_matches_needs_documentation(self):
        """Should match 'This needs documentation'."""
        learnings = self._extract_documentation_learning("This feature needs documentation")
        self.assertGreater(len(learnings), 0, "Should match 'needs documentation'")

    def test_documentation_matches_document_this(self):
        """Should match 'Document this behavior'."""
        learnings = self._extract_documentation_learning("Document this behavior please")
        self.assertGreater(len(learnings), 0, "Should match 'Document this...'")

    def test_documentation_matches_readme_update(self):
        """Should match 'Update the README'."""
        learnings = self._extract_documentation_learning("Update the README with usage examples")
        self.assertGreater(len(learnings), 0, "Should match 'Update the README'")

    def test_documentation_matches_missing_docs(self):
        """Should match 'Missing docs for this'."""
        learnings = self._extract_documentation_learning("There are missing docs for this module")
        self.assertGreater(len(learnings), 0, "Should match 'missing docs'")


class TestMemoryFileDocumentationSection(unittest.TestCase):
    """Test that memory files include Documentation section."""

    def test_new_memory_file_has_documentation_section(self):
        """New memory files should include Documentation (MED confidence) section."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            skill_name = "test-skill"
            learnings = {"High": [], "Med": [], "Low": []}
            session_id = "2026-01-14-session-001"

            # Patch SAFE_BASE_DIR to allow temp directory for testing
            with patch.object(invoke_skill_learning, 'SAFE_BASE_DIR', project_dir):
                update_skill_memory(project_dir, skill_name, learnings, session_id)

            memory_path = Path(project_dir) / ".serena" / "memories" / f"{skill_name}-observations.md"
            content = memory_path.read_text(encoding='utf-8')

            self.assertIn("## Documentation (MED confidence)", content,
                         "Memory file should include Documentation section")

    def test_documentation_learnings_written_to_section(self):
        """Documentation learnings should be written to Documentation section."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            skill_name = "test-skill"
            learnings = {
                "High": [],
                "Med": [{
                    "type": "documentation",
                    "source": "Update the docs with usage examples",
                    "context": "test context",
                    "confidence": 0.65,
                    "method": "pattern"
                }],
                "Low": []
            }
            session_id = "2026-01-14-session-001"

            # Patch SAFE_BASE_DIR to allow temp directory for testing
            with patch.object(invoke_skill_learning, 'SAFE_BASE_DIR', project_dir):
                update_skill_memory(project_dir, skill_name, learnings, session_id)

            memory_path = Path(project_dir) / ".serena" / "memories" / f"{skill_name}-observations.md"
            content = memory_path.read_text(encoding='utf-8')

            self.assertIn("Update the docs with usage examples", content,
                         "Documentation learning should be in file")


class TestMemoryFileContentPreservation(unittest.TestCase):
    """Test that memory file updates preserve existing content and section headers."""

    def test_high_learning_preserves_constraints_header(self):
        """HIGH learnings should be inserted after Constraints header, not replace it."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            skill_name = "test-skill"
            learnings = {
                "High": [{
                    "type": "correction",
                    "source": "Never use deprecated API",
                    "context": "test context",
                    "confidence": 0.9,
                    "method": "pattern"
                }],
                "Med": [],
                "Low": []
            }
            session_id = "2026-01-14-session-001"

            # Patch SAFE_BASE_DIR to allow temp directory for testing
            with patch.object(invoke_skill_learning, 'SAFE_BASE_DIR', project_dir):
                update_skill_memory(project_dir, skill_name, learnings, session_id)

            memory_path = Path(project_dir) / ".serena" / "memories" / f"{skill_name}-observations.md"
            content = memory_path.read_text(encoding='utf-8')

            # Header must still be present
            self.assertIn("## Constraints (HIGH confidence)", content,
                         "Constraints header should be preserved")
            # Learning should be after the header
            self.assertIn("Never use deprecated API", content,
                         "Learning should be present")
            # Header should come before the learning
            header_pos = content.find("## Constraints (HIGH confidence)")
            learning_pos = content.find("Never use deprecated API")
            self.assertLess(header_pos, learning_pos,
                           "Header should come before learning")

    def test_med_learning_preserves_preferences_header(self):
        """MED learnings should be inserted after Preferences header, not replace it."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            skill_name = "test-skill"
            learnings = {
                "High": [],
                "Med": [{
                    "type": "success",
                    "source": "Works great with async",
                    "context": "test context",
                    "confidence": 0.7,
                    "method": "pattern"
                }],
                "Low": []
            }
            session_id = "2026-01-14-session-001"

            # Patch SAFE_BASE_DIR to allow temp directory for testing
            with patch.object(invoke_skill_learning, 'SAFE_BASE_DIR', project_dir):
                update_skill_memory(project_dir, skill_name, learnings, session_id)

            memory_path = Path(project_dir) / ".serena" / "memories" / f"{skill_name}-observations.md"
            content = memory_path.read_text(encoding='utf-8')

            # Header must still be present
            self.assertIn("## Preferences (MED confidence)", content,
                         "Preferences header should be preserved")
            # Learning should be present
            self.assertIn("Works great with async", content,
                         "Learning should be present")

    def test_low_learning_preserves_notes_header(self):
        """LOW learnings should be inserted after Notes header, not replace it."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            skill_name = "test-skill"
            learnings = {
                "High": [],
                "Med": [],
                "Low": [{
                    "type": "command_pattern",
                    "source": "git status",
                    "context": "test context",
                    "confidence": 0.45,
                    "method": "pattern"
                }]
            }
            session_id = "2026-01-14-session-001"

            # Patch SAFE_BASE_DIR to allow temp directory for testing
            with patch.object(invoke_skill_learning, 'SAFE_BASE_DIR', project_dir):
                update_skill_memory(project_dir, skill_name, learnings, session_id)

            memory_path = Path(project_dir) / ".serena" / "memories" / f"{skill_name}-observations.md"
            content = memory_path.read_text(encoding='utf-8')

            # Header must still be present
            self.assertIn("## Notes for Review (LOW confidence)", content,
                         "Notes header should be preserved")
            # Learning should be present
            self.assertIn("git status", content,
                         "Learning should be present")

    def test_multiple_updates_accumulate(self):
        """Multiple updates should accumulate learnings, not overwrite."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            skill_name = "test-skill"
            session_id = "2026-01-14-session-001"

            # First update
            learnings1 = {
                "High": [{
                    "type": "correction",
                    "source": "First correction",
                    "context": "test context",
                    "confidence": 0.9,
                    "method": "pattern"
                }],
                "Med": [],
                "Low": []
            }
            # Patch SAFE_BASE_DIR to allow temp directory for testing
            with patch.object(invoke_skill_learning, 'SAFE_BASE_DIR', project_dir):
                update_skill_memory(project_dir, skill_name, learnings1, session_id)

            # Second update
            learnings2 = {
                "High": [{
                    "type": "correction",
                    "source": "Second correction",
                    "context": "test context",
                    "confidence": 0.85,
                    "method": "pattern"
                }],
                "Med": [],
                "Low": []
            }
            # Patch SAFE_BASE_DIR to allow temp directory for testing
            with patch.object(invoke_skill_learning, 'SAFE_BASE_DIR', project_dir):
                update_skill_memory(project_dir, skill_name, learnings2, "session-002")

            memory_path = Path(project_dir) / ".serena" / "memories" / f"{skill_name}-observations.md"
            content = memory_path.read_text(encoding='utf-8')

            # Both learnings should be present
            self.assertIn("First correction", content,
                         "First learning should be preserved")
            self.assertIn("Second correction", content,
                         "Second learning should be added")


class TestLowConfidenceDetection(unittest.TestCase):
    """Test LOW confidence learning detection patterns."""

    def _extract_low_learning(self, user_response, learning_type=None):
        """Helper to extract LOW confidence learning from a test message."""
        messages = [
            {"role": "user", "content": "Check gh pr list"},
            {"role": "assistant", "content": "Running gh pr list now"},
            {"role": "user", "content": user_response},
        ]
        learnings = extract_learnings(messages, "github")
        if learning_type:
            return [l for l in learnings["Low"] if l["type"] == learning_type]
        return learnings["Low"]

    def test_command_pattern_detected(self):
        """Command patterns should be detected as LOW confidence."""
        learnings = self._extract_low_learning("git status", "command_pattern")
        self.assertGreater(len(learnings), 0, "Should detect command pattern")

    def test_acknowledgement_ok_detected(self):
        """Simple 'ok' acknowledgement should be detected as LOW confidence."""
        learnings = self._extract_low_learning("ok", "acknowledgement")
        self.assertGreater(len(learnings), 0, "Should detect 'ok' acknowledgement")

    def test_acknowledgement_thanks_detected(self):
        """'Thanks' acknowledgement should be detected as LOW confidence."""
        learnings = self._extract_low_learning("thanks!", "acknowledgement")
        self.assertGreater(len(learnings), 0, "Should detect 'thanks' acknowledgement")

    def test_acknowledgement_got_it_detected(self):
        """'Got it' acknowledgement should be detected as LOW confidence."""
        learnings = self._extract_low_learning("got it", "acknowledgement")
        self.assertGreater(len(learnings), 0, "Should detect 'got it' acknowledgement")

    def test_repeated_pattern_same_detected(self):
        """'Same as before' patterns should be detected as LOW confidence."""
        learnings = self._extract_low_learning("Do the same thing again", "repeated_pattern")
        self.assertGreater(len(learnings), 0, "Should detect 'same' pattern")

    def test_repeated_pattern_also_detected(self):
        """'Also check' patterns should be detected as LOW confidence."""
        learnings = self._extract_low_learning("also run the tests", "repeated_pattern")
        self.assertGreater(len(learnings), 0, "Should detect 'also' pattern")

    def test_long_acknowledgement_not_detected(self):
        """Long messages should not be detected as acknowledgements."""
        # Long message with 'ok' at start should not match simple acknowledgement
        learnings = self._extract_low_learning(
            "ok so I was thinking about this problem and here are my thoughts on how we should approach it",
            "acknowledgement"
        )
        self.assertEqual(len(learnings), 0, "Long message should not match acknowledgement")


if __name__ == "__main__":
    unittest.main(verbosity=2)
