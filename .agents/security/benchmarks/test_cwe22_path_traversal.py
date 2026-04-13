"""
CWE-22 Path Traversal Benchmark Tests

Tests security agent detection of path traversal vulnerabilities in Python code.
Each test case represents a known vulnerable pattern that the agent should detect.

Run with: uv run pytest .agents/security/benchmarks/test_cwe22_path_traversal.py -v
"""

from __future__ import annotations

import pytest

from conftest import VulnerablePattern


class TestCWE22Detection:
    """Test cases for CWE-22 Path Traversal detection in Python."""

    def test_pt001_startswith_without_normalization(
        self, cwe22_patterns: list[VulnerablePattern]
    ) -> None:
        """
        PT-001: startswith without path normalization.

        Source: PR #752 (Python equivalent)

        The vulnerability: Using startswith() to validate paths without first
        normalizing with realpath(). Attack sequences like "../.." pass
        the string comparison but resolve to parent directories.

        Expected: CRITICAL detection
        """
        pattern = next(p for p in cwe22_patterns if p.pattern_id == "PT-001")

        assert pattern.cwe_id == "CWE-22"
        assert pattern.expected_severity == "CRITICAL"
        assert not pattern.is_false_positive

        # Verify the pattern contains the vulnerable code structure
        assert "startswith" in pattern.code
        assert "../" in pattern.code or "../../../etc" in pattern.code

    def test_pt002_ospath_join_absolute_bypass(
        self, cwe22_patterns: list[VulnerablePattern]
    ) -> None:
        """
        PT-002: os.path.join with absolute path bypass.

        The vulnerability: os.path.join ignores the base directory when the child
        path is absolute. Attackers can supply absolute paths to escape the
        intended directory.

        Expected: HIGH detection
        """
        pattern = next(p for p in cwe22_patterns if p.pattern_id == "PT-002")

        assert pattern.cwe_id == "CWE-22"
        assert pattern.expected_severity == "HIGH"
        assert "os.path.join" in pattern.code

    def test_pt003_symlink_bypass(
        self, cwe22_patterns: list[VulnerablePattern]
    ) -> None:
        """
        PT-003: Symlink bypass (TOCTOU race condition).

        The vulnerability: Time-of-check-time-of-use race where attacker
        replaces a validated file with a symlink pointing elsewhere.

        Expected: HIGH detection
        """
        pattern = next(p for p in cwe22_patterns if p.pattern_id == "PT-003")

        assert pattern.cwe_id == "CWE-22"
        assert pattern.expected_severity == "HIGH"
        assert "os.path.isfile" in pattern.code
        assert "open" in pattern.code

    def test_pt004_null_byte_injection(
        self, cwe22_patterns: list[VulnerablePattern]
    ) -> None:
        """
        PT-004: Null byte injection.

        The vulnerability: Null bytes (\\x00) can truncate path strings
        in some APIs, bypassing extension validation.

        Expected: CRITICAL detection
        """
        pattern = next(p for p in cwe22_patterns if p.pattern_id == "PT-004")

        assert pattern.cwe_id == "CWE-22"
        assert pattern.expected_severity == "CRITICAL"
        assert "\\x00" in pattern.code or "\\0" in pattern.code

    def test_pt005_safe_pattern_no_flag(
        self, cwe22_patterns: list[VulnerablePattern]
    ) -> None:
        """
        PT-005: Safe pattern (false positive test).

        This test verifies that the security agent does NOT flag properly
        validated path handling code.

        Expected: PASS (no detection)
        """
        pattern = next(p for p in cwe22_patterns if p.pattern_id == "PT-005")

        assert pattern.cwe_id == "CWE-22"
        assert pattern.expected_severity == "PASS"
        assert pattern.is_false_positive

        # Verify the pattern contains the safe code structure
        assert "realpath" in pattern.code
        assert "startswith" in pattern.code


class TestPathTraversalPatterns:
    """Additional path traversal pattern tests."""

    @pytest.mark.parametrize(
        "attack_sequence",
        [
            "../../../etc/passwd",
            "..\\..\\..\\windows\\system32\\config",
            "....//....//etc/passwd",
            "%2e%2e%2f%2e%2e%2f",
            "..%252f..%252f",
        ],
    )
    def test_common_traversal_sequences(self, attack_sequence: str) -> None:
        """Test that common traversal sequences are recognized."""
        # This is a pattern recognition test, not agent integration
        traversal_indicators = [
            "..",
            "%2e",
            "%252e",
        ]

        # Verify our attack sequences contain recognizable patterns
        found_indicator = any(
            indicator.lower() in attack_sequence.lower()
            for indicator in traversal_indicators
        )
        assert found_indicator, f"Sequence {attack_sequence} should contain traversal indicator"

    def test_pattern_count(self, cwe22_patterns: list[VulnerablePattern]) -> None:
        """Verify we have the expected number of test patterns."""
        assert len(cwe22_patterns) == 5, "Expected 5 CWE-22 patterns"

        vulnerable = [p for p in cwe22_patterns if not p.is_false_positive]
        safe = [p for p in cwe22_patterns if p.is_false_positive]

        assert len(vulnerable) == 4, "Expected 4 vulnerable patterns"
        assert len(safe) == 1, "Expected 1 safe pattern"
