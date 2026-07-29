"""Tests for sync_adr_protocol module.

Verifies ADR parsing, requirement counting, and protocol reference checking.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

from scripts.sync_adr_protocol import (
    DANGLING_WORDS,
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

    def test_extracts_bold_inline_status(self) -> None:
        """ADR-005 and ADR-055 spell status as a bold header line."""
        content = (
            "# ADR-005: PowerShell-Only\n\n"
            "**Status**: Superseded by [ADR-042](./ADR-042-python-migration-strategy.md)\n"
            "**Date**: 2025-12-18\n"
        )
        assert parse_adr_status(content) == (
            "Superseded by [ADR-042](./ADR-042-python-migration-strategy.md)"
        )

    def test_extracts_frontmatter_status(self) -> None:
        """ADR-073 introduced machine-readable lifecycle frontmatter."""
        content = "---\nid: ADR-073\nstatus: accepted\n---\n\n# ADR-073\n\n## Context\n"
        assert parse_adr_status(content) == "accepted"

    def test_frontmatter_wins_over_prose(self) -> None:
        """The enum is the lifecycle value; prose sections are unbounded."""
        content = (
            "---\nstatus: superseded\n---\n\n"
            "# ADR-004\n\n## Status\n\nAccepted (2026-01-01). Long debate summary.\n"
        )
        assert parse_adr_status(content) == "superseded"

    def test_frontmatter_status_is_unquoted(self) -> None:
        """A quoted YAML scalar must not carry its quotes into the report."""
        content = '---\nstatus: "accepted"\n---\n\n# ADR-066\n'
        assert parse_adr_status(content) == "accepted"

    def test_frontmatter_tolerates_crlf_and_a_trailing_space(self) -> None:
        """The sibling reader compares stripped fence lines; so must this one."""
        assert parse_adr_status("---\r\nstatus: accepted\r\n---\r\n\r\n# A\r\n") == "accepted"
        assert parse_adr_status("---  \nstatus: accepted\n---\n\n# A\n") == "accepted"

    def test_frontmatter_strips_an_inline_comment(self) -> None:
        content = "---\nstatus: accepted  # backfilled 2026-07-20\n---\n\n# A\n"
        assert parse_adr_status(content) == "accepted"

    def test_non_scalar_frontmatter_status_falls_through(self) -> None:
        """A list, a mapping, or an empty value is not a lifecycle state."""
        for value in ("[a, b]", "{k: v}", "", "|", ">"):
            content = f"---\nstatus: {value}\n---\n\n# A\n\n## Status\n\nProposed\n"
            assert parse_adr_status(content) == "Proposed", value

    def test_ignores_an_indented_status_key(self) -> None:
        """Only a top-level frontmatter key is lifecycle state."""
        content = "---\nmeta:\n  status: sneaky\n---\n\n# A\n\n## Status\n\nProposed\n"
        assert parse_adr_status(content) == "Proposed"

    def test_horizontal_rule_is_not_frontmatter(self) -> None:
        content = "Some prose.\n\n---\n\nMore prose.\n"
        assert parse_adr_status(content) == "Unknown"

    def test_frontmatter_without_closing_delimiter_is_ignored(self) -> None:
        content = "---\nstatus: accepted\n\n# ADR-001\n\n## Status\n\nProposed\n"
        assert parse_adr_status(content) == "Proposed"

    def test_ignores_status_mention_in_body(self) -> None:
        """A bold Status line below the first heading is prose, not state."""
        content = "# ADR-001\n\n## Context\n\n**Status**: COMPLETE\n"
        assert parse_adr_status(content) == "Unknown"

    def test_ignores_status_key_outside_frontmatter(self) -> None:
        """A body line reading 'status: ...' is prose, not lifecycle state."""
        content = "# ADR-001\n\n## Context\n\nThe report prints status: Unknown for these.\n"
        assert parse_adr_status(content) == "Unknown"

    def test_joins_a_status_wrapped_across_lines(self) -> None:
        """ADR-004 wraps its status; reading one line truncates it."""
        content = "# ADR-004\n\n## Status\n\nSuperseded by\n[ADR-086](ADR-086.md) on 2026-07-20.\n"
        assert parse_adr_status(content) == "Superseded by [ADR-086](ADR-086.md) on 2026-07-20."

    def test_join_stops_at_a_subheading(self) -> None:
        """A '###' inside the section is structure, not status."""
        content = "# A\n\n## Status\n\nAccepted\n### Sub-note\nNot the status\n"
        assert parse_adr_status(content) == "Accepted"

    def test_bold_emphasis_is_not_a_list_marker(self) -> None:
        """ADR-039 opens its status with '**PROVISIONAL**'."""
        content = "# A\n\n## Status\n\n**PROVISIONAL** (2026-01-03 to 2026-01-17)\n"
        assert parse_adr_status(content) == "**PROVISIONAL** (2026-01-03 to 2026-01-17)"

    def test_empty_status_section_falls_through(self) -> None:
        """An empty '## Status' must not report the next heading as the status."""
        content = "# ADR-001\n\n## Status\n\n## Date\n\n2026-01-01\n"
        assert parse_adr_status(content) == "Unknown"


class TestStatusParsingCoversTheRealCorpus:
    """Guards the spelling drift that made 17 of 90 ADRs unreadable.

    ADR-073 flagged this exact risk against ``sync_adr_protocol.py``
    ("Confirm no prose-status assumption breaks") and the confirmation was
    never run. These tests are that confirmation, pinned to the corpus.
    """

    def test_no_committed_adr_reports_unknown_status(self) -> None:
        adr_dir = Path(__file__).resolve().parents[1] / ".agents" / "architecture"
        unreadable = [
            path.name
            for path in sorted(adr_dir.glob("ADR-*.md"))
            if path.name != "ADR-TEMPLATE.md"
            and parse_adr_status(path.read_text(encoding="utf-8")) == "Unknown"
        ]
        assert not unreadable, f"ADRs with unreadable status: {unreadable}"

    def test_superseded_status_is_preserved_verbatim(self) -> None:
        """A superseded ADR must not read as active state to a consumer."""
        adr_dir = Path(__file__).resolve().parents[1] / ".agents" / "architecture"
        adr_005 = adr_dir / "ADR-005-powershell-only-scripting.md"
        status = parse_adr_status(adr_005.read_text(encoding="utf-8"))
        assert status.lower().startswith("superseded"), status

    def test_no_status_is_truncated_mid_sentence(self) -> None:
        """ADR-004 wraps its status; a line-at-a-time read ends on 'Superseded by'."""
        adr_dir = Path(__file__).resolve().parents[1] / ".agents" / "architecture"
        dangling = DANGLING_WORDS
        truncated = [
            f"{path.name}: {status}"
            for path in sorted(adr_dir.glob("ADR-*.md"))
            if path.name != "ADR-TEMPLATE.md"
            and (status := parse_adr_status(path.read_text(encoding="utf-8")))
            and status.rstrip().split()[-1].lower() in dangling
        ]
        assert not truncated, f"statuses ending on a dangling word: {truncated}"


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

    def test_skips_symlink_outside_directory(self, tmp_path: Path) -> None:
        """CWE-22: symlinks resolving outside the ADR directory are skipped."""
        outside = tmp_path / "outside"
        outside.mkdir()
        secret = outside / "ADR-099-secret.md"
        secret.write_text("# ADR-099: Secret\n\n## Status\n\nAccepted\n")
        adr_dir = tmp_path / "adrs"
        adr_dir.mkdir()
        (adr_dir / "ADR-099-secret.md").symlink_to(secret)
        results = scan_adrs(adr_dir)
        assert len(results) == 0


class TestRunsOnAStdlibOnlyInterpreter:
    """CONTRIBUTING.md and SESSION-PROTOCOL.md document invoking this script
    as bare ``python3``, which resolves outside the project venv. A
    third-party import would turn a missing optional dependency into a tool
    that never starts."""

    def test_imports_nothing_outside_the_standard_library(self) -> None:
        script = Path(__file__).resolve().parents[1] / "scripts" / "sync_adr_protocol.py"
        tree = ast.parse(script.read_text(encoding="utf-8"))
        imported = {
            (node.module or "").split(".")[0]
            if isinstance(node, ast.ImportFrom)
            else alias.name.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.Import | ast.ImportFrom)
            for alias in getattr(node, "names", [None]) or [None]
        }
        outside = sorted(imported - set(sys.stdlib_module_names) - {"", "__future__"})
        assert not outside, f"third-party imports break the documented entrypoint: {outside}"

    def test_runs_with_site_packages_disabled(self) -> None:
        """python3 -S is the closest reproduction of an interpreter with no
        PyYAML on sys.path."""
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [sys.executable, "-S", str(root / "scripts" / "sync_adr_protocol.py")],
            capture_output=True,
            text=True,
            cwd=root,
        )
        assert "ModuleNotFoundError" not in result.stderr, result.stderr
        assert "[Unknown]" not in result.stdout
