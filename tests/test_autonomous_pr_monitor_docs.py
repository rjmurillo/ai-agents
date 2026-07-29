"""Regression guards for autonomous PR monitor runbook claims."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNBOOK = REPO_ROOT / "docs" / "autonomous-pr-monitor.md"


def _runbook_text() -> str:
    return RUNBOOK.read_text(encoding="utf-8")


def _stale_cache_section() -> str:
    text = _runbook_text()
    start = text.index("### Stale merge-state cache")
    end = text.index("## Branch Update Against Main", start)
    return text[start:end]


def test_stale_cache_refresh_documents_unchanged_ref_path() -> None:
    section = _stale_cache_section()

    assert "Already up to date." in section
    assert "Everything up-to-date" in section
    assert "remote ref is unchanged" in section
    assert "update-branch" in section
    assert "expected_head_sha" in section


def test_stale_cache_refresh_no_longer_claims_no_op_push_refreshes_ref() -> None:
    section = _stale_cache_section()

    assert "After the push, GitHub recomputes mergeability from the fresh ref" not in section
    assert "no-op when already an ancestor and harmless otherwise" not in section


def test_runbook_avoids_banned_comprehensive_term() -> None:
    text = _runbook_text().lower()

    assert "comprehensive" not in text
