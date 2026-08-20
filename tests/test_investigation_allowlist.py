"""Tests for scripts.modules.investigation_allowlist module."""

from __future__ import annotations

from scripts.modules.investigation_allowlist import (
    get_investigation_allowlist,
    get_investigation_allowlist_display,
)
from scripts.modules.investigation_allowlist import (
    test_file_matches_allowlist as file_matches_allowlist,
)


class TestGetInvestigationAllowlist:
    def test_returns_non_empty_list(self) -> None:
        result = get_investigation_allowlist()
        assert len(result) > 0

    def test_patterns_are_anchored(self) -> None:
        for pattern in get_investigation_allowlist():
            assert pattern.startswith("^"), f"Pattern not anchored: {pattern}"


class TestGetInvestigationAllowlistDisplay:
    def test_returns_non_empty_list(self) -> None:
        result = get_investigation_allowlist_display()
        assert len(result) > 0

    def test_same_count_as_allowlist(self) -> None:
        assert len(get_investigation_allowlist()) == len(get_investigation_allowlist_display())


class TestFileMatchesAllowlist:
    def test_matches_sessions_path(self) -> None:
        assert file_matches_allowlist(".agents/sessions/log.json") is True

    def test_matches_analysis_path(self) -> None:
        assert file_matches_allowlist(".agents/analysis/report.md") is True

    def test_matches_serena_memories(self) -> None:
        assert file_matches_allowlist(".serena/memories/test.md") is True

    def test_rejects_source_code(self) -> None:
        assert file_matches_allowlist("src/main.py") is False

    def test_rejects_scripts(self) -> None:
        assert file_matches_allowlist("scripts/build.py") is False

    def test_normalizes_backslashes(self) -> None:
        assert file_matches_allowlist(".agents\\sessions\\log.json") is True

    def test_matches_architecture_review(self) -> None:
        assert file_matches_allowlist(".agents/architecture/REVIEW-001.md") is True

    def test_rejects_architecture_adr(self) -> None:
        assert file_matches_allowlist(".agents/architecture/ADR-001.md") is False
