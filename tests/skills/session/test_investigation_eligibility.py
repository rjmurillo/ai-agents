"""Tests for test_investigation_eligibility.py (both session and session-qa-eligibility)."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Test the session-qa-eligibility version (they should be identical)
SCRIPT_DIR = (
    Path(__file__).resolve().parents[3]
    / ".claude" / "skills" / "session-qa-eligibility" / "scripts"
)
sys.path.insert(0, str(SCRIPT_DIR))

import test_investigation_eligibility as tie


class TestFileMatchesAllowlist:
    """Tests for file_matches_allowlist function."""

    def test_sessions_match(self):
        assert tie.file_matches_allowlist(".agents/sessions/2026-01-01.json") is True

    def test_analysis_match(self):
        assert tie.file_matches_allowlist(".agents/analysis/report.md") is True

    def test_retrospective_match(self):
        assert tie.file_matches_allowlist(".agents/retrospective/retro.md") is True

    def test_serena_memories_match(self):
        assert tie.file_matches_allowlist(".serena/memories/test.md") is True

    def test_security_match(self):
        assert tie.file_matches_allowlist(".agents/security/scan.json") is True

    def test_memory_match(self):
        assert tie.file_matches_allowlist(".agents/memory/data.json") is True

    def test_architecture_review_match(self):
        assert tie.file_matches_allowlist(".agents/architecture/REVIEW-001.md") is True

    def test_critique_match(self):
        assert tie.file_matches_allowlist(".agents/critique/review.md") is True

    def test_episodes_match(self):
        assert tie.file_matches_allowlist(".agents/memory/episodes/ep1.json") is True

    def test_src_does_not_match(self):
        assert tie.file_matches_allowlist("src/main.py") is False

    def test_scripts_does_not_match(self):
        assert tie.file_matches_allowlist("scripts/validate.ps1") is False

    def test_backslash_normalization(self):
        assert tie.file_matches_allowlist(".agents\\sessions\\test.json") is True


class TestGetStagedFiles:
    """Tests for get_staged_files function."""

    @patch("test_investigation_eligibility.subprocess.run")
    def test_returns_files(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0, stdout=".agents/sessions/test.json\nsrc/main.py\n"
        )
        files, ok = tie.get_staged_files()
        assert ok is True
        assert len(files) == 2

    @patch("test_investigation_eligibility.subprocess.run")
    def test_returns_empty_on_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        files, ok = tie.get_staged_files()
        assert ok is False
        assert files == []

    @patch("test_investigation_eligibility.subprocess.run")
    def test_handles_timeout(self, mock_run):
        from subprocess import TimeoutExpired
        mock_run.side_effect = TimeoutExpired(cmd="git", timeout=10)
        files, ok = tie.get_staged_files()
        assert ok is False
        assert files == []

    @patch("test_investigation_eligibility.subprocess.run")
    def test_skips_empty_lines(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0, stdout=".agents/sessions/test.json\n\n\n"
        )
        files, ok = tie.get_staged_files()
        assert ok is True
        assert len(files) == 1


class TestAllowlistPatterns:
    """Verify all ALLOWLIST_PATTERNS are valid regexes."""

    def test_all_patterns_compile(self):
        import re
        for pattern in tie.ALLOWLIST_PATTERNS:
            re.compile(pattern)

    def test_display_paths_match_patterns(self):
        assert len(tie.ALLOWLIST_PATTERNS) == len(tie.DISPLAY_PATHS)
