"""Shared investigation-only allowlist for ADR-034 QA exemption.

Single source of truth for investigation artifact path patterns.
Consumers: .github/scripts/validate_investigation_claims.py diff-mode checks and tests.

See: ADR-034 Investigation Session QA Exemption
"""

from __future__ import annotations

import re


def get_investigation_allowlist() -> list[str]:
    """Return canonical investigation-only allowlist patterns.

    Returns regex patterns anchored to start of path.
    """
    return [
        r"^\.project-toolkit/sessions/",
        r"^\.project-toolkit/analysis/",
        r"^\.project-toolkit/retrospective/",
        r"^\.serena/memories($|/)",
        r"^\.project-toolkit/security/",
        r"^\.project-toolkit/memory/",
        r"^\.project-toolkit/architecture/REVIEW-",
        r"^\.project-toolkit/critique/",
    ]


def get_investigation_allowlist_display() -> list[str]:
    """Return human-readable allowed paths for error messages."""
    return [
        ".project-toolkit/sessions/",
        ".project-toolkit/analysis/",
        ".project-toolkit/retrospective/",
        ".serena/memories/",
        ".project-toolkit/security/",
        ".project-toolkit/memory/",
        ".project-toolkit/architecture/REVIEW-*",
        ".project-toolkit/critique/",
    ]


def test_file_matches_allowlist(file_path: str) -> bool:
    """Test whether a file path matches the investigation allowlist.

    Args:
        file_path: The file path to test (relative to repo root).

    Returns:
        True if the file matches any allowlist pattern.
    """
    normalized = file_path.replace("\\", "/")
    for pattern in get_investigation_allowlist():
        if re.search(pattern, normalized):
            return True
    return False
