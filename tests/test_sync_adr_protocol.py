"""Tests for sync_adr_protocol module.

Verifies ADR parsing, requirement counting, and protocol reference checking.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.sync_adr_protocol import (
    AdrRequirements,
    SyncReport,
    check_protocol_reference,
    count_requirements,
    parse_adr_status,
    parse_adr_title,
    scan_adrs,
)


class TestParseAdrTitle:
    """Tests for parse_adr_title function."""

    def test_extracts_title_from_standard_format(self) -> None:
        content = "# ADR-001: Markdown Linting Configuration\n\n## Status\n"
        assert parse_adr_title(content) == "Markdown Linting Configuration"

    def test_extracts_title_without_adr_prefix(self) -> None:
        content = "# Some Title Without ADR Prefix\n"
        assert parse_adr_title(content) == "Some Title Without ADR Prefix"

    def test_returns_unknown_for_empty_content(self) -> None:
        assert parse_adr_title("") == "Unknown"

    def test_returns_unknown_for_no_heading(self) -> None:
        assert parse_adr_title("No heading here\nJust text") == "Unknown"


class TestParseAdrStatus:
    """Tests for parse_adr_status function."""

    def test_extracts_accepted_status(self) -> None:
        content = "# ADR-001\n\n## Status\n\nAccepted\n\n## Date\n"
        assert parse_adr_status(content) == "Accepted"

    def test_extracts_proposed_status(self) -> None:
        content = "# ADR-001\n\n## Status\n\nProposed\n\n## Date\n"
        assert parse_adr_status(content) == "Proposed"

    def test_returns_unknown_for_missing_status(self) -> None:
        content = "# ADR-001\n\n## Date\n\n2026-01-01\n"
        assert parse_adr_status(content) == "Unknown"


class TestCountRequirements:
    """Tests for count_requirements function."""

    def test_counts_must_keywords(self) -> None:
        content = "The agent MUST do X. The agent MUST NOT do Y."
        must, should, may = count_requirements(content)
        assert must == 2
        assert should == 0
        assert may == 0

    def test_counts_should_keywords(self) -> None:
        content = "The agent SHOULD do X. This is RECOMMENDED."
        must, should, may = count_requirements(content)
        assert must == 0
        assert should == 2
        assert may == 0

    def test_counts_may_keywords(self) -> None:
        content = "The agent MAY do X. This is OPTIONAL."
        must, should, may = count_requirements(content)
        assert must == 0
        assert should == 0
        assert may == 2

    def test_counts_mixed_keywords(self) -> None:
        content = "MUST do A. SHOULD do B. MAY do C."
        must, should, may = count_requirements(content)
        assert must == 1
        assert should == 1
        assert may == 1

    def test_counts_shall_as_must(self) -> None:
        content = "SHALL do X. SHALL NOT do Y."
        must, _, _ = count_requirements(content)
        assert must == 2

    def test_counts_required_as_must(self) -> None:
        content = "This is REQUIRED."
        must, _, _ = count_requirements(content)
        assert must == 1

    def test_ignores_lowercase(self) -> None:
        content = "The agent must do X."
        must, should, may = count_requirements(content)
        assert must == 0
        assert should == 0
        assert may == 0

    def test_empty_content(self) -> None:
        must, should, may = count_requirements("")
        assert must == 0
        assert should == 0
        assert may == 0


class TestCheckProtocolReference:
    """Tests for check_protocol_reference function."""

    def test_finds_adr_reference(self) -> None:
        protocol = "Per ADR-043, tools MUST scope to changed files."
        assert check_protocol_reference(protocol, 43) is True

    def test_finds_zero_padded_reference(self) -> None:
        protocol = "See ADR-001 for details."
        assert check_protocol_reference(protocol, 1) is True

    def test_returns_false_for_missing_reference(self) -> None:
        protocol = "Per ADR-043, tools MUST scope to changed files."
        assert check_protocol_reference(protocol, 42) is False

    def test_does_not_match_partial_numbers(self) -> None:
        protocol = "See ADR-043 for details."
        assert check_protocol_reference(protocol, 4) is False


class TestAdrRequirements:
    """Tests for AdrRequirements dataclass."""

    def test_has_enforceable_requirements_true(self) -> None:
        adr = AdrRequirements(
            number=1, title="Test", filepath=Path("x"), status="Accepted", must_count=1
        )
        assert adr.has_enforceable_requirements is True

    def test_has_enforceable_requirements_false(self) -> None:
        adr = AdrRequirements(
            number=1,
            title="Test",
            filepath=Path("x"),
            status="Accepted",
            should_count=1,
        )
        assert adr.has_enforceable_requirements is False

    def test_total_requirements(self) -> None:
        adr = AdrRequirements(
            number=1,
            title="Test",
            filepath=Path("x"),
            status="Accepted",
            must_count=2,
            should_count=3,
            may_count=1,
        )
        assert adr.total_requirements == 6


class TestSyncReport:
    """Tests for SyncReport dataclass."""

    def _make_adr(
        self, number: int, must: int = 0, referenced: bool = False
    ) -> AdrRequirements:
        return AdrRequirements(
            number=number,
            title=f"ADR-{number}",
            filepath=Path(f"ADR-{number}.md"),
            status="Accepted",
            must_count=must,
            referenced_in_protocol=referenced,
        )

    def test_gaps_returns_unreferenced_must_adrs(self) -> None:
        report = SyncReport(
            adrs=[
                self._make_adr(1, must=2, referenced=False),
                self._make_adr(2, must=1, referenced=True),
            ]
        )
        assert len(report.gaps) == 1
        assert report.gaps[0].number == 1

    def test_synced_returns_referenced_must_adrs(self) -> None:
        report = SyncReport(
            adrs=[
                self._make_adr(1, must=2, referenced=True),
                self._make_adr(2, must=0, referenced=True),
            ]
        )
        assert len(report.synced) == 1
        assert report.synced[0].number == 1

    def test_informational_returns_no_must_adrs(self) -> None:
        report = SyncReport(
            adrs=[
                self._make_adr(1, must=0),
                self._make_adr(2, must=1),
            ]
        )
        assert len(report.informational) == 1
        assert report.informational[0].number == 1


class TestScanAdrs:
    """Tests for scan_adrs function."""

    def test_scans_adr_files(self, tmp_path: Path) -> None:
        adr_content = (
            "# ADR-001: Test ADR\n\n"
            "## Status\n\nAccepted\n\n"
            "## Decision\n\nAgents MUST do X.\n"
        )
        (tmp_path / "ADR-001-test.md").write_text(adr_content)
        results = scan_adrs(tmp_path)
        assert len(results) == 1
        assert results[0].number == 1
        assert results[0].title == "Test ADR"
        assert results[0].must_count == 1

    def test_skips_template(self, tmp_path: Path) -> None:
        (tmp_path / "ADR-TEMPLATE.md").write_text("# ADR-NNN: Template\n")
        results = scan_adrs(tmp_path)
        assert len(results) == 0

    def test_empty_directory(self, tmp_path: Path) -> None:
        results = scan_adrs(tmp_path)
        assert len(results) == 0
