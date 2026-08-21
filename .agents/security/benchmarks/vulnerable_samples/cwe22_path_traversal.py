"""
CWE-22 Path Traversal Vulnerable Samples

Purpose: Security agent benchmark testing
Source: Issue #756 Security Agent Detection Gaps Remediation

DO NOT USE IN PRODUCTION - These are intentionally vulnerable examples
"""

from __future__ import annotations

import os
from pathlib import Path


# =============================================================================
# PT-001: startswith() without path normalization
# =============================================================================
# VULNERABLE: CWE-22 startswith without realpath normalization
# EXPECTED: CRITICAL - Path traversal via .. sequences
# SOURCE: PR #752 Export-ClaudeMemMemories.ps1:115 (Python equivalent)


def export_data_insecure(output_file: str, memories_dir: str = "/app/memories") -> None:
    """
    VULNERABLE: startswith does string comparison before path resolution.

    Attack: output_file = "../../../etc/passwd"
    String comparison passes because the string starts with ".."
    but after resolution, it escapes to parent directories.
    """
    # VULNERABLE: String comparison without path normalization
    if not output_file.startswith(memories_dir):
        print(f"Warning: Output file should be in {memories_dir}")
        # WARNING ONLY - continues execution, attack succeeds

    # Would write to arbitrary location
    with open(output_file, "w") as f:
        f.write("sensitive data")


# =============================================================================
# PT-002: os.path.join with absolute path bypass
# =============================================================================
# VULNERABLE: CWE-22 os.path.join ignores base when child is absolute
# EXPECTED: HIGH - Absolute path bypass
# SOURCE: Synthetic


def get_config_insecure(user_input: str, safe_dir: str = "/app/config") -> str | None:
    """
    VULNERABLE: os.path.join ignores safe_dir when user_input is absolute.

    Attack: user_input = "/etc/passwd"
    Result: full_path becomes "/etc/passwd", not under safe_dir
    """
    # VULNERABLE: os.path.join ignores base when child is absolute
    full_path = os.path.join(safe_dir, user_input)

    if os.path.exists(full_path):
        with open(full_path) as f:
            return f.read()
    return None


# =============================================================================
# PT-003: Symlink bypass (TOCTOU)
# =============================================================================
# VULNERABLE: CWE-22/CWE-367 Symlink race condition
# EXPECTED: HIGH - Time-of-check-time-of-use race
# SOURCE: Synthetic


def read_file_insecure(user_path: str) -> str | None:
    """
    VULNERABLE: Gap between check and use allows symlink swap.

    Attack:
    1. Attacker creates legitimate file
    2. Script passes os.path.isfile() check
    3. Attacker replaces file with symlink to /etc/shadow
    4. open() follows symlink
    """
    # VULNERABLE: TOCTOU race condition
    if os.path.isfile(user_path):
        # Race window: attacker can replace file with symlink here
        with open(user_path) as f:  # Follows symlink to arbitrary file
            return f.read()
    return None


# =============================================================================
# PT-004: Null byte injection
# =============================================================================
# VULNERABLE: CWE-22 Null byte path truncation
# EXPECTED: CRITICAL - Null byte bypasses extension validation
# SOURCE: Synthetic


def process_upload_insecure(filename: str, upload_dir: str = "/app/uploads") -> str | None:
    """
    VULNERABLE: Null byte truncates path in some APIs.

    Attack: filename = "../../etc/passwd\x00.txt"
    Extension check sees ".txt"
    Some filesystem APIs stop at null byte
    """
    # VULNERABLE: Null byte can truncate path validation
    _, extension = os.path.splitext(filename)

    if extension == ".txt":
        full_path = os.path.join(upload_dir, filename)
        # Would process arbitrary file
        if os.path.exists(full_path):
            with open(full_path) as f:
                return f.read()
    return None


# =============================================================================
# PT-005: SAFE PATTERN - Proper path validation
# =============================================================================
# SAFE: Correct path validation with realpath
# EXPECTED: PASS - This should NOT be flagged
# SOURCE: GitHubCore.psm1 Test-SafeFilePath (Python equivalent)


def test_safe_file_path(path: str, allowed_root: str) -> bool:
    """
    SAFE: Normalize paths BEFORE comparison.

    Uses os.path.realpath to resolve all symlinks and relative components
    before comparing paths.
    """
    # SAFE: Normalize paths before comparison
    normalized_path = os.path.realpath(path)
    normalized_root = os.path.realpath(allowed_root)

    # SAFE: Proper path containment check
    return normalized_path.startswith(normalized_root + os.sep) or normalized_path == normalized_root


def export_data_secure(output_file: str, memories_dir: str = "/app/memories") -> None:
    """SAFE: Uses validated path helper."""
    # SAFE: Uses validated path helper
    if not test_safe_file_path(output_file, memories_dir):
        raise ValueError(f"Path traversal attempt detected: {output_file} is outside {memories_dir}")

    with open(output_file, "w") as f:
        f.write("sensitive data")


# =============================================================================
# PT-006: Path traversal via Path object without validation
# =============================================================================
# VULNERABLE: CWE-22 Path object manipulation without validation
# EXPECTED: HIGH - Path traversal via parent references
# SOURCE: Synthetic


def get_document_insecure(doc_name: str, docs_dir: str = "/app/docs") -> str | None:
    """
    VULNERABLE: Path object allows traversal without explicit validation.

    Attack: doc_name = "../../../etc/passwd"
    Path concatenation resolves .. sequences
    """
    # VULNERABLE: Path concatenation without validation
    doc_path = Path(docs_dir) / doc_name

    if doc_path.exists():
        return doc_path.read_text()
    return None
