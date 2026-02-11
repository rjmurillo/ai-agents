"""Tests for scripts.validation.memory_index module.

Validates memory index consistency for tiered memory architecture (ADR-017).
Covers index parsing, file reference checking, keyword density, index format,
duplicate detection, orphan detection, memory-index references, and output formats.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.validation.memory_index import (
    DomainIndex,
    IndexEntry,
    build_parser,
    check_domain_prefix_naming,
    check_duplicate_entries,
    check_file_references,
    check_index_format,
    check_keyword_density,
    check_memory_index_references,
    check_minimum_keywords,
    find_domain_indices,
    find_orphaned_files,
    format_json,
    format_markdown,
    main,
    parse_index_entries,
    run_validation,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def create_memory_structure(
    base: Path, files: dict[str, str]
) -> None:
    """Create test memory files from a dictionary."""
    base.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        (base / name).write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# parse_index_entries
# ---------------------------------------------------------------------------


class TestParseIndexEntries:
    """Tests for parsing domain index files."""

    def test_parses_valid_entries(self, tmp_path: Path) -> None:
        index = tmp_path / "skills-test-index.md"
        index.write_text(
            "| Keywords | File |\n"
            "|----------|------|\n"
            "| alpha beta gamma | test-skill-one |\n"
            "| delta epsilon | test-skill-two |\n"
        )
        entries = parse_index_entries(index)
        assert len(entries) == 2
        assert entries[0].file_name == "test-skill-one"
        assert entries[0].keywords == ["alpha", "beta", "gamma"]

    def test_skips_header_and_separator(self, tmp_path: Path) -> None:
        index = tmp_path / "skills-test-index.md"
        index.write_text(
            "| Keywords | File |\n"
            "|----------|------|\n"
            "| keyword1 | skill-file |\n"
        )
        entries = parse_index_entries(index)
        assert len(entries) == 1

    def test_parses_markdown_links(self, tmp_path: Path) -> None:
        index = tmp_path / "skills-test-index.md"
        index.write_text(
            "| Keywords | File |\n"
            "|----------|------|\n"
            "| alpha beta | [link-test](link-test.md) |\n"
        )
        entries = parse_index_entries(index)
        assert entries[0].file_name == "link-test"

    def test_skips_malformed_rows(self, tmp_path: Path) -> None:
        index = tmp_path / "skills-test-index.md"
        index.write_text(
            "| Keywords | File |\n"
            "|----------|------|\n"
            "| valid | valid-skill |\n"
            "Not a table row\n"
            "| also valid | another-skill |\n"
        )
        entries = parse_index_entries(index)
        assert len(entries) == 2

    def test_nonexistent_file_returns_empty(self, tmp_path: Path) -> None:
        entries = parse_index_entries(tmp_path / "nonexistent.md")
        assert entries == []

    def test_header_only_returns_empty(self, tmp_path: Path) -> None:
        index = tmp_path / "skills-test-index.md"
        index.write_text(
            "| Keywords | File |\n"
            "|----------|------|\n"
        )
        entries = parse_index_entries(index)
        assert entries == []


# ---------------------------------------------------------------------------
# find_domain_indices
# ---------------------------------------------------------------------------


class TestFindDomainIndices:
    """Tests for finding domain index files."""

    def test_finds_indices(self, tmp_path: Path) -> None:
        (tmp_path / "skills-test-index.md").write_text("content")
        (tmp_path / "skills-other-index.md").write_text("content")
        indices = find_domain_indices(tmp_path)
        assert len(indices) == 2
        domains = {i.domain for i in indices}
        assert "test" in domains
        assert "other" in domains

    def test_nonexistent_path(self, tmp_path: Path) -> None:
        indices = find_domain_indices(tmp_path / "missing")
        assert indices == []

    def test_no_matching_files(self, tmp_path: Path) -> None:
        (tmp_path / "readme.md").write_text("not an index")
        indices = find_domain_indices(tmp_path)
        assert indices == []

    def test_domain_extraction(self, tmp_path: Path) -> None:
        (tmp_path / "skills-multi-word-index.md").write_text("c")
        indices = find_domain_indices(tmp_path)
        assert indices[0].domain == "multi-word"


# ---------------------------------------------------------------------------
# check_file_references
# ---------------------------------------------------------------------------


class TestCheckFileReferences:
    """Tests for file reference validation (P0)."""

    def test_all_files_exist(self, tmp_path: Path) -> None:
        (tmp_path / "test-one.md").write_text("c")
        entries = [IndexEntry(["a"], "test-one", "a")]
        result = check_file_references(entries, tmp_path)
        assert result.passed is True
        assert result.valid_files == ["test-one"]

    def test_missing_files_detected(self, tmp_path: Path) -> None:
        entries = [IndexEntry(["a"], "missing-skill", "a")]
        result = check_file_references(entries, tmp_path)
        assert result.passed is False
        assert "missing-skill" in result.missing_files
        assert any("Missing file" in i for i in result.issues)

    def test_skill_prefix_violation(self, tmp_path: Path) -> None:
        (tmp_path / "skill-bad.md").write_text("c")
        entries = [IndexEntry(["a"], "skill-bad", "a")]
        result = check_file_references(entries, tmp_path)
        assert result.passed is False
        assert "skill-bad" in result.naming_violations
        assert any("ADR-017 violation" in i for i in result.issues)

    def test_skillbook_is_not_skill_prefix(self, tmp_path: Path) -> None:
        (tmp_path / "skillbook-one.md").write_text("c")
        entries = [IndexEntry(["a"], "skillbook-one", "a")]
        result = check_file_references(entries, tmp_path)
        assert result.passed is True
        assert result.naming_violations == []

    def test_mixed_valid_and_invalid(self, tmp_path: Path) -> None:
        (tmp_path / "valid-entry.md").write_text("c")
        (tmp_path / "skill-bad.md").write_text("c")
        (tmp_path / "another-valid.md").write_text("c")
        entries = [
            IndexEntry(["a"], "valid-entry", "a"),
            IndexEntry(["b"], "skill-bad", "b"),
            IndexEntry(["c"], "another-valid", "c"),
        ]
        result = check_file_references(entries, tmp_path)
        assert result.passed is False
        assert len(result.naming_violations) == 1
        assert "valid-entry" in result.valid_files
        assert "another-valid" in result.valid_files

    def test_skill_prefix_missing_file(self, tmp_path: Path) -> None:
        entries = [IndexEntry(["a"], "skill-ghost", "a")]
        result = check_file_references(entries, tmp_path)
        assert result.passed is False
        assert "skill-ghost" in result.naming_violations
        assert "skill-ghost" in result.missing_files
        assert len(result.issues) == 2

    def test_path_traversal_detected(self, tmp_path: Path) -> None:
        entries = [IndexEntry(["a"], "../../../../etc/passwd", "a")]
        result = check_file_references(entries, tmp_path)
        assert result.passed is False
        assert any("Path traversal" in i for i in result.issues)


# ---------------------------------------------------------------------------
# check_keyword_density
# ---------------------------------------------------------------------------


class TestCheckKeywordDensity:
    """Tests for keyword density/uniqueness validation (P0)."""

    def test_fully_unique_keywords(self) -> None:
        entries = [
            IndexEntry(["alpha", "beta", "gamma"], "skill-one", ""),
            IndexEntry(["delta", "epsilon", "zeta"], "skill-two", ""),
        ]
        result = check_keyword_density(entries)
        assert result.passed is True
        assert result.densities["skill-one"] == 1.0
        assert result.densities["skill-two"] == 1.0

    def test_low_uniqueness_fails(self) -> None:
        entries = [
            IndexEntry(
                ["shared", "keyword", "overlap", "common", "alpha"],
                "skill-one", "",
            ),
            IndexEntry(
                ["shared", "keyword", "overlap", "common", "beta"],
                "skill-two", "",
            ),
        ]
        result = check_keyword_density(entries)
        assert result.passed is False
        # Each has 1/5 = 20% unique
        assert result.densities["skill-one"] == 0.2
        assert result.densities["skill-two"] == 0.2

    def test_single_entry_100_percent(self) -> None:
        entries = [IndexEntry(["alpha", "beta"], "single", "")]
        result = check_keyword_density(entries)
        assert result.passed is True
        assert result.densities["single"] == 1.0

    def test_empty_entries(self) -> None:
        result = check_keyword_density([])
        assert result.passed is True

    def test_case_insensitive_matching(self) -> None:
        entries = [
            IndexEntry(["Alpha", "BETA", "gamma"], "skill-one", ""),
            IndexEntry(["ALPHA", "beta", "GAMMA"], "skill-two", ""),
        ]
        result = check_keyword_density(entries)
        assert result.passed is False

    def test_empty_keywords_handled(self) -> None:
        entries = [
            IndexEntry([], "empty-keywords", ""),
            IndexEntry(["alpha"], "has-keywords", ""),
        ]
        result = check_keyword_density(entries)
        assert result.densities["empty-keywords"] == 0.0


# ---------------------------------------------------------------------------
# check_index_format
# ---------------------------------------------------------------------------


class TestCheckIndexFormat:
    """Tests for pure lookup table format validation (P0)."""

    def test_pure_table_passes(self, tmp_path: Path) -> None:
        index = tmp_path / "index.md"
        index.write_text(
            "| Keywords | File |\n"
            "|----------|------|\n"
            "| alpha beta | skill-one |\n"
        )
        result = check_index_format(index)
        assert result.passed is True
        assert not result.issues

    def test_title_detected(self, tmp_path: Path) -> None:
        index = tmp_path / "index.md"
        index.write_text(
            "# Skills Index\n\n"
            "| Keywords | File |\n"
            "|----------|------|\n"
            "| alpha | skill |\n"
        )
        result = check_index_format(index)
        assert result.passed is False
        assert any("Title detected" in i for i in result.issues)
        assert 1 in result.violation_lines

    def test_metadata_block_detected(self, tmp_path: Path) -> None:
        index = tmp_path / "index.md"
        index.write_text(
            "**Last Updated**: 2025-12-28\n"
            "**Status**: Active\n\n"
            "| Keywords | File |\n"
            "|----------|------|\n"
            "| alpha | skill |\n"
        )
        result = check_index_format(index)
        assert result.passed is False
        assert any("Metadata block detected" in i for i in result.issues)
        assert len(result.violation_lines) == 2

    def test_navigation_section_detected(self, tmp_path: Path) -> None:
        index = tmp_path / "index.md"
        index.write_text(
            "Parent: memory-index\n\n"
            "| Keywords | File |\n"
            "|----------|------|\n"
            "| alpha | skill |\n"
        )
        result = check_index_format(index)
        assert result.passed is False
        assert any("Navigation section detected" in i for i in result.issues)

    def test_prose_after_table_detected(self, tmp_path: Path) -> None:
        index = tmp_path / "index.md"
        index.write_text(
            "| Keywords | File |\n"
            "|----------|------|\n"
            "| alpha | skill |\n\n"
            "This is some prose text.\n"
        )
        result = check_index_format(index)
        assert result.passed is False
        assert any("Non-table content detected" in i for i in result.issues)

    def test_empty_lines_between_rows_allowed(self, tmp_path: Path) -> None:
        index = tmp_path / "index.md"
        index.write_text(
            "| Keywords | File |\n"
            "|----------|------|\n"
            "| alpha | skill-one |\n"
            "\n"
            "| beta | skill-two |\n"
        )
        result = check_index_format(index)
        assert result.passed is True

    def test_heading_level_2_detected(self, tmp_path: Path) -> None:
        index = tmp_path / "index.md"
        index.write_text(
            "## Secondary Heading\n\n"
            "| Keywords | File |\n"
            "|----------|------|\n"
            "| alpha | skill |\n"
        )
        result = check_index_format(index)
        assert result.passed is False

    def test_nonexistent_file_passes(self, tmp_path: Path) -> None:
        result = check_index_format(tmp_path / "missing.md")
        assert result.passed is True

    def test_multiple_violations(self, tmp_path: Path) -> None:
        index = tmp_path / "index.md"
        index.write_text(
            "# Title\n\n"
            "**Status**: Active\n\n"
            "| Keywords | File |\n"
            "|----------|------|\n"
            "| alpha | skill |\n\n"
            "Some prose.\n"
        )
        result = check_index_format(index)
        assert result.passed is False
        assert len(result.violation_lines) >= 3


# ---------------------------------------------------------------------------
# check_duplicate_entries
# ---------------------------------------------------------------------------


class TestCheckDuplicateEntries:
    """Tests for duplicate entry detection (P0)."""

    def test_no_duplicates(self) -> None:
        entries = [
            IndexEntry(["a"], "skill-one", ""),
            IndexEntry(["b"], "skill-two", ""),
        ]
        result = check_duplicate_entries(entries)
        assert result.passed is True

    def test_duplicate_detected(self) -> None:
        entries = [
            IndexEntry(["a"], "skill-one", ""),
            IndexEntry(["b"], "skill-one", ""),
        ]
        result = check_duplicate_entries(entries)
        assert result.passed is False
        assert "skill-one" in result.duplicates


# ---------------------------------------------------------------------------
# check_minimum_keywords
# ---------------------------------------------------------------------------


class TestCheckMinimumKeywords:
    """Tests for minimum keyword count validation (P2)."""

    def test_sufficient_keywords(self) -> None:
        entries = [IndexEntry(["a", "b", "c", "d", "e"], "skill", "")]
        result = check_minimum_keywords(entries, min_keywords=5)
        assert result.passed is True

    def test_insufficient_keywords(self) -> None:
        entries = [IndexEntry(["a", "b"], "skill", "")]
        result = check_minimum_keywords(entries, min_keywords=5)
        assert result.passed is False
        assert any("Insufficient keywords" in i for i in result.issues)


# ---------------------------------------------------------------------------
# check_domain_prefix_naming
# ---------------------------------------------------------------------------


class TestCheckDomainPrefixNaming:
    """Tests for domain prefix naming validation (P2)."""

    def test_correct_prefix(self) -> None:
        entries = [IndexEntry(["a"], "test-skill", "")]
        result = check_domain_prefix_naming(entries, domain="test")
        assert result.passed is True

    def test_wrong_prefix(self) -> None:
        entries = [IndexEntry(["a"], "other-skill", "")]
        result = check_domain_prefix_naming(entries, domain="test")
        assert result.passed is False
        assert any("Naming violation" in i for i in result.issues)


# ---------------------------------------------------------------------------
# check_memory_index_references
# ---------------------------------------------------------------------------


class TestCheckMemoryIndexReferences:
    """Tests for memory-index reference validation (P1)."""

    def test_missing_memory_index(self, tmp_path: Path) -> None:
        indices = [DomainIndex(tmp_path / "skills-test-index.md", "skills-test-index", "test")]
        result = check_memory_index_references(tmp_path, indices)
        assert result.passed is False
        assert any("not found" in i for i in result.issues)

    def test_valid_references(self, tmp_path: Path) -> None:
        create_memory_structure(tmp_path, {
            "memory-index.md": (
                "| Keywords | File |\n"
                "|----------|------|\n"
                "| test | skills-test-index |\n"
            ),
            "skills-test-index.md": "| Keywords | File |\n",
        })
        indices = [DomainIndex(tmp_path / "skills-test-index.md", "skills-test-index", "test")]
        result = check_memory_index_references(tmp_path, indices)
        assert result.passed is True

    def test_unreferenced_domain_index(self, tmp_path: Path) -> None:
        create_memory_structure(tmp_path, {
            "memory-index.md": (
                "| Keywords | File |\n"
                "|----------|------|\n"
            ),
            "skills-test-index.md": "content",
        })
        indices = [DomainIndex(tmp_path / "skills-test-index.md", "skills-test-index", "test")]
        result = check_memory_index_references(tmp_path, indices)
        assert result.passed is False
        assert "skills-test-index" in result.unreferenced_indices

    def test_broken_reference(self, tmp_path: Path) -> None:
        create_memory_structure(tmp_path, {
            "memory-index.md": (
                "| Keywords | File |\n"
                "|----------|------|\n"
                "| test | nonexistent-file |\n"
            ),
        })
        result = check_memory_index_references(tmp_path, [])
        assert result.passed is False
        assert "nonexistent-file" in result.broken_references

    def test_markdown_link_in_memory_index(self, tmp_path: Path) -> None:
        create_memory_structure(tmp_path, {
            "memory-index.md": (
                "| Keywords | File |\n"
                "|----------|------|\n"
                "| test | [skills-test-index](skills-test-index.md) |\n"
            ),
            "skills-test-index.md": "content",
        })
        indices = [DomainIndex(tmp_path / "skills-test-index.md", "skills-test-index", "test")]
        result = check_memory_index_references(tmp_path, indices)
        assert result.passed is True
        assert not result.broken_references

    def test_path_traversal_detected(self, tmp_path: Path) -> None:
        create_memory_structure(tmp_path, {
            "memory-index.md": (
                "| Keywords | File |\n"
                "|----------|------|\n"
                "| evil | ../../../../etc/passwd |\n"
            ),
        })
        result = check_memory_index_references(tmp_path, [])
        assert result.passed is False
        assert any("Path traversal" in i for i in result.issues)


# ---------------------------------------------------------------------------
# find_orphaned_files
# ---------------------------------------------------------------------------


class TestFindOrphanedFiles:
    """Tests for orphan detection (P1)."""

    def test_no_orphans(self, tmp_path: Path) -> None:
        create_memory_structure(tmp_path, {
            "skills-test-index.md": (
                "| Keywords | File |\n"
                "|----------|------|\n"
                "| alpha | test-skill |\n"
            ),
            "test-skill.md": "content",
        })
        indices = find_domain_indices(tmp_path)
        orphans = find_orphaned_files(indices, tmp_path)
        assert orphans == []

    def test_skill_prefix_orphan_detected(self, tmp_path: Path) -> None:
        create_memory_structure(tmp_path, {
            "skills-test-index.md": (
                "| Keywords | File |\n"
                "|----------|------|\n"
                "| alpha | test-valid |\n"
            ),
            "test-valid.md": "content",
            "skill-orphan.md": "orphaned",
        })
        indices = find_domain_indices(tmp_path)
        orphans = find_orphaned_files(indices, tmp_path)
        skill_orphans = [o for o in orphans if o.domain == "INVALID"]
        assert len(skill_orphans) == 1
        assert skill_orphans[0].file == "skill-orphan"

    def test_domain_prefix_orphan_detected(self, tmp_path: Path) -> None:
        create_memory_structure(tmp_path, {
            "skills-test-index.md": (
                "| Keywords | File |\n"
                "|----------|------|\n"
                "| alpha | test-indexed |\n"
            ),
            "test-indexed.md": "content",
            "test-unindexed.md": "orphaned",
        })
        indices = find_domain_indices(tmp_path)
        orphans = find_orphaned_files(indices, tmp_path)
        assert any(o.file == "test-unindexed" and o.domain == "test" for o in orphans)

    def test_indexed_skill_prefix_not_orphan(self, tmp_path: Path) -> None:
        create_memory_structure(tmp_path, {
            "skills-test-index.md": (
                "| Keywords | File |\n"
                "|----------|------|\n"
                "| alpha | skill-indexed |\n"
            ),
            "skill-indexed.md": "content",
        })
        indices = find_domain_indices(tmp_path)
        orphans = find_orphaned_files(indices, tmp_path)
        assert not any(o.file == "skill-indexed" for o in orphans)

    def test_skillbook_not_flagged_as_invalid(self, tmp_path: Path) -> None:
        create_memory_structure(tmp_path, {
            "skills-test-index.md": (
                "| Keywords | File |\n"
                "|----------|------|\n"
                "| alpha | test-valid |\n"
            ),
            "test-valid.md": "content",
            "skillbook-unindexed.md": "not skill- prefix",
        })
        indices = find_domain_indices(tmp_path)
        orphans = find_orphaned_files(indices, tmp_path)
        invalid_orphans = [o for o in orphans if o.domain == "INVALID"]
        assert not any(o.file == "skillbook-unindexed" for o in invalid_orphans)

    def test_skill_prefix_no_domain_index(self, tmp_path: Path) -> None:
        create_memory_structure(tmp_path, {
            "skill-no-domain.md": "orphan with no domain index",
        })
        orphans = find_orphaned_files([], tmp_path)
        assert len(orphans) == 1
        assert orphans[0].domain == "INVALID"

    def test_multiple_skill_prefix_orphans(self, tmp_path: Path) -> None:
        create_memory_structure(tmp_path, {
            "skills-test-index.md": (
                "| Keywords | File |\n"
                "|----------|------|\n"
                "| alpha | test-indexed |\n"
            ),
            "test-indexed.md": "content",
            "skill-orphan-one.md": "orphan 1",
            "skill-orphan-two.md": "orphan 2",
            "skill-orphan-three.md": "orphan 3",
        })
        indices = find_domain_indices(tmp_path)
        orphans = find_orphaned_files(indices, tmp_path)
        skill_orphans = [o for o in orphans if o.domain == "INVALID"]
        assert len(skill_orphans) == 3


# ---------------------------------------------------------------------------
# run_validation (integration)
# ---------------------------------------------------------------------------


class TestRunValidation:
    """Integration tests for the full validation pipeline."""

    def test_valid_structure_passes(self, tmp_path: Path) -> None:
        create_memory_structure(tmp_path, {
            "skills-test-index.md": (
                "| Keywords | File |\n"
                "|----------|------|\n"
                "| alpha beta gamma delta epsilon | test-skill-one |\n"
                "| zeta eta theta iota kappa | test-skill-two |\n"
            ),
            "test-skill-one.md": "content",
            "test-skill-two.md": "content",
            "memory-index.md": (
                "| Keywords | File |\n"
                "|----------|------|\n"
                "| test | skills-test-index |\n"
            ),
        })
        report = run_validation(tmp_path, "json")
        assert report.passed is True
        assert report.summary.total_domains == 1
        assert report.summary.missing_files == 0

    def test_missing_files_fail(self, tmp_path: Path) -> None:
        create_memory_structure(tmp_path, {
            "skills-broken-index.md": (
                "| Keywords | File |\n"
                "|----------|------|\n"
                "| alpha beta | missing-skill |\n"
            ),
        })
        report = run_validation(tmp_path, "json")
        assert report.passed is False
        assert report.summary.missing_files == 1

    def test_multiple_domains(self, tmp_path: Path) -> None:
        create_memory_structure(tmp_path, {
            "skills-d1-index.md": (
                "| Keywords | File |\n"
                "|----------|------|\n"
                "| alpha | d1-skill |\n"
            ),
            "skills-d2-index.md": (
                "| Keywords | File |\n"
                "|----------|------|\n"
                "| beta | d2-skill |\n"
            ),
            "d1-skill.md": "c",
            "d2-skill.md": "c",
        })
        report = run_validation(tmp_path, "json")
        assert report.summary.total_domains == 2
        assert "d1" in report.domain_results
        assert "d2" in report.domain_results

    def test_no_domains_no_memory_index(self, tmp_path: Path) -> None:
        """Empty directory with no memory-index.md fails P1 validation."""
        report = run_validation(tmp_path, "json")
        assert report.passed is False
        assert report.summary.total_domains == 0
        assert report.memory_index_result is not None
        assert any("not found" in i for i in report.memory_index_result.issues)

    def test_no_domains_with_memory_index(self, tmp_path: Path) -> None:
        """Directory with memory-index.md but no domain indices passes."""
        create_memory_structure(tmp_path, {
            "memory-index.md": "| Keywords | File |\n|----------|------|\n",
        })
        report = run_validation(tmp_path, "json")
        assert report.passed is True
        assert report.summary.total_domains == 0


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------


class TestFormatMarkdown:
    """Tests for markdown output format."""

    def test_contains_header(self, tmp_path: Path) -> None:
        create_memory_structure(tmp_path, {
            "skills-test-index.md": (
                "| Keywords | File |\n"
                "|----------|------|\n"
                "| alpha | test-skill |\n"
            ),
            "test-skill.md": "c",
        })
        report = run_validation(tmp_path, "json")
        md = format_markdown(report)
        assert "# Memory Index Validation Report" in md
        assert "| Metric | Value |" in md

    def test_includes_domain_results(self, tmp_path: Path) -> None:
        create_memory_structure(tmp_path, {
            "skills-test-index.md": (
                "| Keywords | File |\n"
                "|----------|------|\n"
                "| alpha | test-skill |\n"
            ),
            "test-skill.md": "c",
        })
        report = run_validation(tmp_path, "json")
        md = format_markdown(report)
        assert "## Domain: test" in md


class TestFormatJson:
    """Tests for JSON output format."""

    def test_valid_json(self, tmp_path: Path) -> None:
        import json
        create_memory_structure(tmp_path, {
            "skills-test-index.md": (
                "| Keywords | File |\n"
                "|----------|------|\n"
                "| alpha | test-skill |\n"
            ),
            "test-skill.md": "c",
        })
        report = run_validation(tmp_path, "json")
        json_str = format_json(report)
        data = json.loads(json_str)
        assert "passed" in data
        assert "summary" in data
        assert "domain_results" in data


# ---------------------------------------------------------------------------
# main / CLI
# ---------------------------------------------------------------------------


class TestMain:
    """Tests for main() entry point and CLI behavior."""

    def test_nonexistent_path_no_ci(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("CI", raising=False)
        exit_code = main(["--path", str(tmp_path / "missing")])
        assert exit_code == 0

    def test_nonexistent_path_ci(self, tmp_path: Path) -> None:
        exit_code = main(["--path", str(tmp_path / "missing"), "--ci"])
        assert exit_code == 2

    def test_empty_dir_passes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("CI", raising=False)
        exit_code = main(["--path", str(tmp_path)])
        assert exit_code == 0

    def test_valid_structure_ci_passes(self, tmp_path: Path) -> None:
        create_memory_structure(tmp_path, {
            "skills-test-index.md": (
                "| Keywords | File |\n"
                "|----------|------|\n"
                "| alpha beta gamma delta epsilon | test-skill |\n"
            ),
            "test-skill.md": "c",
            "memory-index.md": (
                "| Keywords | File |\n"
                "|----------|------|\n"
                "| test | skills-test-index |\n"
            ),
        })
        exit_code = main(["--path", str(tmp_path), "--ci"])
        assert exit_code == 0

    def test_missing_files_ci_fails(self, tmp_path: Path) -> None:
        create_memory_structure(tmp_path, {
            "skills-broken-index.md": (
                "| Keywords | File |\n"
                "|----------|------|\n"
                "| alpha | missing-skill |\n"
            ),
        })
        exit_code = main(["--path", str(tmp_path), "--ci"])
        assert exit_code == 1

    def test_json_format(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        import json
        create_memory_structure(tmp_path, {
            "skills-test-index.md": (
                "| Keywords | File |\n"
                "|----------|------|\n"
                "| alpha | test-skill |\n"
            ),
            "test-skill.md": "c",
            "memory-index.md": (
                "| Keywords | File |\n"
                "|----------|------|\n"
                "| test | skills-test-index |\n"
            ),
        })
        exit_code = main([
            "--path", str(tmp_path),
            "--format", "json",
        ])
        assert exit_code == 0
        output = capsys.readouterr().out
        data = json.loads(output)
        assert data["passed"] is True

    def test_markdown_format(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("CI", raising=False)
        create_memory_structure(tmp_path, {
            "skills-test-index.md": (
                "| Keywords | File |\n"
                "|----------|------|\n"
                "| alpha | test-skill |\n"
            ),
            "test-skill.md": "c",
        })
        exit_code = main([
            "--path", str(tmp_path),
            "--format", "markdown",
        ])
        assert exit_code == 0
        output = capsys.readouterr().out
        assert "# Memory Index Validation Report" in output

    def test_console_format(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("CI", raising=False)
        create_memory_structure(tmp_path, {
            "skills-test-index.md": (
                "| Keywords | File |\n"
                "|----------|------|\n"
                "| alpha | test-skill |\n"
            ),
            "test-skill.md": "c",
        })
        exit_code = main(["--path", str(tmp_path), "--format", "console"])
        assert exit_code == 0


class TestBuildParser:
    """Tests for argument parser construction."""

    def test_defaults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("CI", raising=False)
        parser = build_parser()
        args = parser.parse_args([])
        assert args.path == ".serena/memories"
        assert args.ci is False
        assert args.output_format == "console"
        assert args.fix_orphans is False

    def test_ci_flag(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--ci"])
        assert args.ci is True

    def test_format_choices(self) -> None:
        parser = build_parser()
        for fmt in ("console", "markdown", "json"):
            args = parser.parse_args(["--format", fmt])
            assert args.output_format == fmt

    def test_env_var_defaults(self) -> None:
        with patch.dict(
            "os.environ",
            {"MEMORY_PATH": "/custom/path", "CI": "true"},
        ):
            parser = build_parser()
            args = parser.parse_args([])
            assert args.path == "/custom/path"
            assert args.ci is True
