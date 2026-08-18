"""Validate that script names in patterns.md resolve to shipped files."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parents[3]
PATTERNS_MD = (
    REPO_ROOT
    / ".claude"
    / "skills"
    / "github-url-intercept"
    / "references"
    / "patterns.md"
)
GITHUB_SCRIPTS_DIR = REPO_ROOT / ".claude" / "skills" / "github" / "scripts"


def _extract_script_names(text: str) -> list[str]:
    """Extract Python script names referenced as commands in patterns.md.

    Matches scripts after arrow indicators or in table Script columns,
    excluding example file paths in URLs.
    """
    # Scripts after → arrows (e.g., "→ get_pr_context.py --pull-request 123")
    arrow_refs = re.findall(r"→\s+([\w-]+\.py)", text)
    # Scripts in table cells (column after |)
    table_refs = re.findall(r"\|\s+([\w-]+\.py)\b", text)
    return arrow_refs + table_refs


def _find_script(name: str) -> Path | None:
    """Locate a script anywhere under the github skills scripts directory."""
    for path in GITHUB_SCRIPTS_DIR.rglob(name):
        return path
    return None


@pytest.fixture()
def pattern_scripts() -> list[str]:
    content = PATTERNS_MD.read_text()
    return _extract_script_names(content)


def test_patterns_md_exists() -> None:
    assert PATTERNS_MD.is_file(), f"Missing: {PATTERNS_MD}"


def test_all_referenced_scripts_exist(pattern_scripts: list[str]) -> None:
    """Every .py script named in patterns.md must exist in the github skill."""
    missing: list[str] = []
    for name in set(pattern_scripts):
        if _find_script(name) is None:
            missing.append(name)
    assert not missing, f"Scripts referenced in patterns.md but not found: {missing}"


def test_no_powershell_references() -> None:
    """No .ps1 references should remain in patterns.md."""
    content = PATTERNS_MD.read_text()
    ps1_refs = re.findall(r"\b[\w-]+\.ps1\b", content)
    assert not ps1_refs, f"PowerShell references remain: {ps1_refs}"
