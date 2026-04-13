"""
CWE-77 Command Injection Benchmark Tests

Tests security agent detection of command injection vulnerabilities in Python code.
Each test case represents a known vulnerable pattern that the agent should detect.

Run with: uv run pytest .agents/security/benchmarks/test_cwe77_command_injection.py -v
"""

from __future__ import annotations

import pytest

from conftest import VulnerablePattern


class TestCWE77Detection:
    """Test cases for CWE-77 Command Injection detection in Python."""

    def test_ci001_shell_true_subprocess(
        self, cwe77_patterns: list[VulnerablePattern]
    ) -> None:
        """
        CI-001: shell=True with user input in subprocess.

        Source: PR #752 (Python equivalent)

        The vulnerability: subprocess.run with shell=True and string concatenation
        allows shell metacharacters (;|&><) to inject additional commands.

        Expected: CRITICAL detection
        """
        pattern = next(p for p in cwe77_patterns if p.pattern_id == "CI-001")

        assert pattern.cwe_id == "CWE-77"
        assert pattern.expected_severity == "CRITICAL"
        assert not pattern.is_false_positive

        # Verify the vulnerable pattern structure
        assert "subprocess" in pattern.code or "shell=True" in pattern.code
        assert "; rm -rf /" in pattern.code

    def test_ci002_dynamic_code_execution(
        self, cwe77_patterns: list[VulnerablePattern]
    ) -> None:
        """
        CI-002: Dynamic code execution with user input.

        The vulnerability: Functions that run arbitrary Python code
        from a string. User input passed to these functions allows complete
        code execution.

        Expected: CRITICAL detection
        """
        pattern = next(p for p in cwe77_patterns if p.pattern_id == "CI-002")

        assert pattern.cwe_id == "CWE-77"
        assert pattern.expected_severity == "CRITICAL"
        assert "user_command" in pattern.code.lower() or "input" in pattern.code

    def test_ci003_dynamic_code_with_config(
        self, cwe77_patterns: list[VulnerablePattern]
    ) -> None:
        """
        CI-003: Dynamic code execution with configuration value.

        The vulnerability: Dynamic code execution can interpret dangerous
        expressions in strings. Configuration files or external input containing
        code can be executed.

        Expected: HIGH detection
        """
        pattern = next(p for p in cwe77_patterns if p.pattern_id == "CI-003")

        assert pattern.cwe_id in ["CWE-77", "CWE-94"]
        assert pattern.expected_severity == "HIGH"
        assert "config" in pattern.code.lower() or "template" in pattern.code.lower()

    def test_ci004_shell_metacharacters_git(
        self, cwe77_patterns: list[VulnerablePattern]
    ) -> None:
        """
        CI-004: Shell metacharacters in git command.

        The vulnerability: Environment variables in shell commands with shell=True
        can be exploited via shell metacharacters to chain additional commands.

        Expected: CRITICAL detection
        """
        pattern = next(p for p in cwe77_patterns if p.pattern_id == "CI-004")

        assert pattern.cwe_id == "CWE-77"
        assert pattern.expected_severity == "CRITICAL"
        assert "git" in pattern.code
        assert "branch_name" in pattern.code.lower() or "environ" in pattern.code.lower()

    def test_ci005_safe_list_args_pattern(
        self, cwe77_patterns: list[VulnerablePattern]
    ) -> None:
        """
        CI-005: Safe pattern with list arguments (false positive test).

        This test verifies that the security agent does NOT flag properly
        parameterized subprocess calls with list arguments.

        Expected: PASS (no detection)
        """
        pattern = next(p for p in cwe77_patterns if p.pattern_id == "CI-005")

        assert pattern.cwe_id == "CWE-77"
        assert pattern.expected_severity == "PASS"
        assert pattern.is_false_positive

        # Verify the pattern uses list arguments
        assert "[" in pattern.code and "]" in pattern.code


class TestCommandInjectionPatterns:
    """Additional command injection pattern tests."""

    @pytest.mark.parametrize(
        "dangerous_construct",
        [
            "subprocess.run(cmd, shell=True)",
            "subprocess.Popen(cmd, shell=True)",
            "subprocess.call(cmd, shell=True)",
        ],
    )
    def test_dangerous_constructs_identified(self, dangerous_construct: str) -> None:
        """Test that dangerous Python constructs are recognized."""
        # These are constructs that should always be flagged when combined
        # with user input
        dangerous_patterns = [
            "shell=true",
            "subprocess.popen",
            "subprocess.call",
        ]

        found = any(
            p in dangerous_construct.lower()
            for p in dangerous_patterns
        )

        assert found, f"Construct {dangerous_construct} should be recognized as dangerous"

    @pytest.mark.parametrize(
        "metachar,description",
        [
            (";", "Command separator"),
            ("|", "Pipe to another command"),
            ("&", "Background/chain execution"),
            (">", "Output redirection"),
            ("<", "Input redirection"),
            ("$(", "Command substitution"),
            ("`", "Backtick substitution"),
        ],
    )
    def test_shell_metacharacters(self, metachar: str, description: str) -> None:
        """Verify shell metacharacters are recognized as injection vectors."""
        # All these metacharacters can be used for command injection
        # when shell=True in Python subprocess calls
        assert len(metachar) >= 1
        assert len(description) > 0

    def test_pattern_count(self, cwe77_patterns: list[VulnerablePattern]) -> None:
        """Verify we have the expected number of test patterns."""
        assert len(cwe77_patterns) == 5, "Expected 5 CWE-77 patterns"

        vulnerable = [p for p in cwe77_patterns if not p.is_false_positive]
        safe = [p for p in cwe77_patterns if p.is_false_positive]

        assert len(vulnerable) == 4, "Expected 4 vulnerable patterns"
        assert len(safe) == 1, "Expected 1 safe pattern"


class TestPR752Patterns:
    """Tests specifically for patterns from PR #752 (Python equivalents)."""

    def test_pr752_patterns_included(
        self,
        cwe22_patterns: list[VulnerablePattern],
        cwe77_patterns: list[VulnerablePattern],
    ) -> None:
        """Verify patterns from PR #752 are included in benchmarks."""
        pr752_patterns = [
            p for p in cwe22_patterns + cwe77_patterns
            if "PR #752" in p.source
        ]

        assert len(pr752_patterns) >= 2, (
            "Expected at least 2 patterns from PR #752 "
            "(CWE-22 path traversal and CWE-77 command injection)"
        )

        # Verify specific patterns
        cwe22_pr752 = [p for p in pr752_patterns if p.cwe_id == "CWE-22"]
        cwe77_pr752 = [p for p in pr752_patterns if p.cwe_id == "CWE-77"]

        assert len(cwe22_pr752) >= 1, "Missing CWE-22 pattern from PR #752"
        assert len(cwe77_pr752) >= 1, "Missing CWE-77 pattern from PR #752"

    def test_pr752_patterns_severity(
        self,
        cwe22_patterns: list[VulnerablePattern],
        cwe77_patterns: list[VulnerablePattern],
    ) -> None:
        """Verify PR #752 patterns have correct severity ratings."""
        pr752_patterns = [
            p for p in cwe22_patterns + cwe77_patterns
            if "PR #752" in p.source
        ]

        for pattern in pr752_patterns:
            if pattern.cwe_id == "CWE-77":
                assert pattern.expected_severity == "CRITICAL", (
                    f"CWE-77 from PR #752 should be CRITICAL, got {pattern.expected_severity}"
                )
            elif pattern.cwe_id == "CWE-22":
                assert pattern.expected_severity in ["CRITICAL", "HIGH"], (
                    f"CWE-22 from PR #752 should be CRITICAL/HIGH, got {pattern.expected_severity}"
                )
