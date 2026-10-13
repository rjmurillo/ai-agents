"""Contract tests for the fix-ci.md 'Required check never reported' section (issue #5162)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_FIX_CI = _REPO_ROOT / ".claude" / "skills" / "github" / "fix-ci.md"
_HEADING = "## Required check never reported"
_ANCHOR = "(#required-check-never-reported)"


@pytest.fixture(scope="module")
def doc() -> str:
    return _FIX_CI.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def section(doc: str) -> str:
    start = doc.index(_HEADING)
    match = re.search(r"^## ", doc[start + len(_HEADING) :], flags=re.MULTILINE)
    end = start + len(_HEADING) + match.start() if match else len(doc)
    return doc[start:end]


def test_section_exists_once(doc: str) -> None:
    assert doc.count(_HEADING) == 1


def test_phase_two_links_to_section(doc: str) -> None:
    assert _ANCHOR in doc.split("### Phase 3")[0]


def test_section_names_the_detection_fields(section: str) -> None:
    assert "MissingRequiredChecks" in section
    assert "MissingRequired" in section
    assert "get_pr_checks.py" in section
    assert "why_pr_blocked.py" in section


def test_section_gives_close_reopen_recovery(section: str) -> None:
    assert "close_pr.py" in section
    assert "Reopen" in section
    assert "without a new commit" in section.lower()


def test_section_points_at_the_reopened_trigger_contract(section: str) -> None:
    contract = "tests/workflows/test_pull_request_reopened_triggers.py"
    assert contract in section
    assert (_REPO_ROOT / contract).is_file()


def test_section_documents_edited_fallback(section: str) -> None:
    assert "If a check is still missing" in section
    assert "edited" in section
    assert "synchronize" in section


def test_section_avoids_raw_gh(section: str) -> None:
    assert not re.search(r"\bgh (pr|issue|api)\b", section)


def test_section_has_no_em_or_en_dash(section: str) -> None:
    assert "—" not in section
    assert "–" not in section
