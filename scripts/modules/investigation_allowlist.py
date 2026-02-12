"""Shared investigation-only allowlist for ADR-034 QA exemption.

Single source of truth for investigation artifact path patterns.
Consumers: validate_session_json.py, session skill, session-qa-eligibility skill.

See: ADR-034 Investigation Session QA Exemption
"""

from __future__ import annotations

import re


def get_investigation_allowlist() -> list[str]:
    """Return canonical investigation-only allowlist patterns.

    Returns regex patterns anchored to start of path.
    """
    return [
        r"^\.agents/sessions/",
        r"^\.agents/analysis/",
        r"^\.agents/retrospective/",
        r"^\.serena/memories($|/)",
        r"^\.agents/security/",
        r"^\.agents/memory/",
        r"^\.agents/architecture/REVIEW-",
        r"^\.agents/critique/",
        r"^\.agents/memory/episodes/",
    ]


def get_investigation_allowlist_display() -> list[str]:
    """Return human-readable allowed paths for error messages."""
    return [
        ".agents/sessions/",
        ".agents/analysis/",
        ".agents/retrospective/",
        ".serena/memories/",
        ".agents/security/",
        ".agents/memory/",
        ".agents/architecture/REVIEW-*",
        ".agents/critique/",
        ".agents/memory/episodes/",
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
