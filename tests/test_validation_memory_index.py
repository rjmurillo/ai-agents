"""Tests for scripts.validation.memory_index module.

Validates memory index consistency for tiered memory architecture (ADR-017).
Covers index parsing, file reference checking, keyword density, index format,
duplicate detection, orphan detection, memory-index references, and output formats.
"""

from __future__ import annotations

import subprocess
from collections import Counter
from pathlib import Path
from unittest.mock import patch

import frontmatter
import pytest
import yaml

from scripts.validation.memory_index import (
    DomainIndex,
    IndexEntry,
    _load_base_reference_counts,
    build_parser,
    check_domain_prefix_naming,
    check_duplicate_entries,
    check_file_references,
    check_frontmatter_validity,
    check_index_format,
    check_keyword_density,
    check_memory_index_references,
    check_minimum_keywords,
    check_naming_convention,
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
        path = base / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


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
        result = check_memory_index_references(tmp_path, indices, Counter())
        assert result.passed is False
        assert any("not found" in i for i in result.issues)

    def test_option_like_base_ref_fails_closed(
        self, tmp_path: Path
    ) -> None:
        counts, error = _load_base_reference_counts(
            tmp_path,
            "--octopus",
        )

        assert counts is None
        assert error == "invalid base ref: '--octopus'"

    def test_loads_canonical_base_reference_counts(
        self, tmp_path: Path
    ) -> None:
        memory_path = tmp_path / ".serena" / "memories"
        memory_path.mkdir(parents=True)
        commit_id = "a" * 40
        base_content = (
            "| Keywords | File |\n"
            "|----------|------|\n"
            "| first | [first](skills-copilot-index.md) |\n"
            "| second | [second](skills-copilot-index.md) |\n"
        )
        completed = [
            subprocess.CompletedProcess([], 0, f"{tmp_path}\n", ""),
            subprocess.CompletedProcess([], 0, f"{commit_id}\n", ""),
            subprocess.CompletedProcess([], 0, f"{commit_id}\n", ""),
            subprocess.CompletedProcess([], 0, base_content, ""),
            subprocess.CompletedProcess(
                [],
                0,
                (
                    "100644 blob bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
                    "\t.serena/memories/skills-copilot-index.md\0"
                ),
                "",
            ),
        ]

        with (
            patch.dict(
                "scripts.validation.memory_index.os.environ",
                {
                    "GIT_DIR": "/repo/.git/worktrees/branch",
                    "GIT_INDEX_FILE": "/repo/.git/worktrees/branch/index",
                },
            ),
            patch(
                "scripts.validation.memory_index.subprocess.run",
                side_effect=completed,
            ) as run_mock,
        ):
            counts, error = _load_base_reference_counts(
                memory_path,
                "origin/main",
            )

        assert counts == Counter({"skills-copilot-index": 2})
        assert error is None
        assert run_mock.call_args_list[1].args[0] == [
            "git",
            "rev-parse",
            "--verify",
            "--end-of-options",
            "origin/main^{commit}",
        ]
        assert run_mock.call_args_list[2].args[0] == [
            "git",
            "merge-base",
            "HEAD",
            commit_id,
        ]
        assert "GIT_DIR" not in run_mock.call_args_list[0].kwargs["env"]
        assert "GIT_INDEX_FILE" not in run_mock.call_args_list[0].kwargs["env"]

    @pytest.mark.parametrize(
        ("failure_index", "expected_error"),
        [
            (0, "could not resolve repository root"),
            (1, "could not resolve base ref origin/main"),
            (
                2,
                "could not resolve merge base between HEAD and origin/main",
            ),
            (
                3,
                "could not read .serena/memories/memory-index.md "
                f"at base ref {'a' * 40}",
            ),
            (
                4,
                "could not inspect .serena/memories at base ref "
                f"{'a' * 40}",
            ),
        ],
    )
    def test_git_failure_fails_closed(
        self,
        tmp_path: Path,
        failure_index: int,
        expected_error: str,
    ) -> None:
        memory_path = tmp_path / ".serena" / "memories"
        memory_path.mkdir(parents=True)
        commit_id = "a" * 40
        successful_steps = [
            subprocess.CompletedProcess([], 0, f"{tmp_path}\n", ""),
            subprocess.CompletedProcess([], 0, f"{commit_id}\n", ""),
            subprocess.CompletedProcess([], 0, f"{commit_id}\n", ""),
            subprocess.CompletedProcess([], 0, "", ""),
            subprocess.CompletedProcess([], 0, "", ""),
        ]
        successful_steps[failure_index] = subprocess.CompletedProcess(
            [],
            1,
            "",
            "failed",
        )

        with patch(
            "scripts.validation.memory_index.subprocess.run",
            side_effect=successful_steps[: failure_index + 1],
        ):
            counts, error = _load_base_reference_counts(
                memory_path,
                "origin/main",
            )

        assert counts is None
        assert error == expected_error

    def test_malformed_tree_output_fails_closed(
        self, tmp_path: Path
    ) -> None:
        memory_path = tmp_path / ".serena" / "memories"
        memory_path.mkdir(parents=True)
        commit_id = "a" * 40
        completed = [
            subprocess.CompletedProcess([], 0, f"{tmp_path}\n", ""),
            subprocess.CompletedProcess([], 0, f"{commit_id}\n", ""),
            subprocess.CompletedProcess([], 0, f"{commit_id}\n", ""),
            subprocess.CompletedProcess([], 0, "", ""),
            subprocess.CompletedProcess([], 0, "malformed\0", ""),
        ]

        with patch(
            "scripts.validation.memory_index.subprocess.run",
            side_effect=completed,
        ):
            counts, error = _load_base_reference_counts(
                memory_path,
                "origin/main",
            )

        assert counts is None
        assert error == "could not parse base-ref tree output"

    def test_base_counts_come_from_merge_base_not_base_tip(
        self, tmp_path: Path
    ) -> None:
        repo = tmp_path / "repo"
        memory_path = repo / ".serena" / "memories"
        memory_path.mkdir(parents=True)

        def git(*args: str) -> None:
            subprocess.run(
                ["git", *args],
                cwd=repo,
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )

        def write_index(link_count: int) -> None:
            rows = "".join(
                f"| keywords {index}: [entry {index}](shared.md)\n"
                for index in range(link_count)
            )
            (memory_path / "memory-index.md").write_text(rows)
            (memory_path / "shared.md").write_text("content")

        subprocess.run(
            ["git", "init", "-b", "main", str(repo)],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        git("config", "user.email", "test@example.com")
        git("config", "user.name", "Test User")
        write_index(1)
        git("add", ".")
        git("commit", "-m", "base")
        git("checkout", "-b", "feature")
        git("checkout", "main")
        write_index(2)
        git("add", ".")
        git("commit", "-m", "main duplicate")
        git("checkout", "feature")
        write_index(2)
        git("add", ".")
        git("commit", "-m", "feature duplicate")

        counts, error = _load_base_reference_counts(memory_path, "main")

        assert error is None
        assert counts == Counter({"shared": 1})
        result = check_memory_index_references(
            memory_path,
            [],
            counts,
        )
        assert result.passed is False
        assert result.duplicate_references == ["shared"]

    def test_symbolic_link_in_base_tree_fails_closed(
        self, tmp_path: Path
    ) -> None:
        memory_path = tmp_path / ".serena" / "memories"
        memory_path.mkdir(parents=True)
        commit_id = "a" * 40
        base_content = "| keywords: [entry](shared.md)\n"
        completed = [
            subprocess.CompletedProcess([], 0, f"{tmp_path}\n", ""),
            subprocess.CompletedProcess([], 0, f"{commit_id}\n", ""),
            subprocess.CompletedProcess([], 0, f"{commit_id}\n", ""),
            subprocess.CompletedProcess([], 0, base_content, ""),
            subprocess.CompletedProcess(
                [],
                0,
                (
                    "120000 blob bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
                    "\t.serena/memories/shared.md\0"
                ),
                "",
            ),
        ]

        with patch(
            "scripts.validation.memory_index.subprocess.run",
            side_effect=completed,
        ):
            counts, error = _load_base_reference_counts(
                memory_path,
                "origin/main",
            )

        assert counts is None
        assert error == (
            "base memory-index target is a symbolic link: "
            ".serena/memories/shared.md"
        )

    def test_symbolic_link_ancestor_in_base_tree_fails_closed(
        self, tmp_path: Path
    ) -> None:
        memory_path = tmp_path / ".serena" / "memories"
        memory_path.mkdir(parents=True)
        commit_id = "a" * 40
        base_content = "| keywords: [entry](alias/shared.md)\n"
        completed = [
            subprocess.CompletedProcess([], 0, f"{tmp_path}\n", ""),
            subprocess.CompletedProcess([], 0, f"{commit_id}\n", ""),
            subprocess.CompletedProcess([], 0, f"{commit_id}\n", ""),
            subprocess.CompletedProcess([], 0, base_content, ""),
            subprocess.CompletedProcess(
                [],
                0,
                (
                    "120000 blob bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
                    "\t.serena/memories/alias\0"
                ),
                "",
            ),
        ]

        with patch(
            "scripts.validation.memory_index.subprocess.run",
            side_effect=completed,
        ):
            counts, error = _load_base_reference_counts(
                memory_path,
                "origin/main",
            )

        assert counts is None
        assert error == (
            "base memory-index target is a symbolic link: "
            ".serena/memories/alias/shared.md"
        )

    def test_removed_symlink_component_in_base_tree_fails_closed(
        self, tmp_path: Path
    ) -> None:
        memory_path = tmp_path / ".serena" / "memories"
        memory_path.mkdir(parents=True)
        commit_id = "a" * 40
        base_content = "| keywords: [entry](alias/../shared.md)\n"
        completed = [
            subprocess.CompletedProcess([], 0, f"{tmp_path}\n", ""),
            subprocess.CompletedProcess([], 0, f"{commit_id}\n", ""),
            subprocess.CompletedProcess([], 0, f"{commit_id}\n", ""),
            subprocess.CompletedProcess([], 0, base_content, ""),
            subprocess.CompletedProcess(
                [],
                0,
                (
                    "120000 blob bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
                    "\t.serena/memories/alias\0"
                ),
                "",
            ),
        ]

        with patch(
            "scripts.validation.memory_index.subprocess.run",
            side_effect=completed,
        ):
            counts, error = _load_base_reference_counts(
                memory_path,
                "origin/main",
            )

        assert counts is None
        assert error == (
            "base memory-index target is a symbolic link: "
            ".serena/memories/shared.md"
        )

    def test_valid_references(self, tmp_path: Path) -> None:
        create_memory_structure(tmp_path, {
            "memory-index.md": (
                "| Keywords | File |\n"
                "|----------|------|\n"
                "| test | "
                "[skills-test-index](skills-test-index.md) |\n"
            ),
            "skills-test-index.md": "| Keywords | File |\n",
        })
        indices = [DomainIndex(tmp_path / "skills-test-index.md", "skills-test-index", "test")]
        result = check_memory_index_references(tmp_path, indices, Counter())
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
        result = check_memory_index_references(tmp_path, indices, Counter())
        assert result.passed is False
        assert "skills-test-index" in result.unreferenced_indices

    @pytest.mark.parametrize(
        "decoy",
        [
            "<!-- [entry](skills-test-index.md) -->\n",
            "`[entry](skills-test-index.md)`\n",
            "<a href=\"skills-test-index.md\">entry</a>\n",
        ],
    )
    def test_non_links_do_not_satisfy_completeness(
        self,
        tmp_path: Path,
        decoy: str,
    ) -> None:
        create_memory_structure(tmp_path, {
            "memory-index.md": decoy,
            "skills-test-index.md": "content",
        })
        indices = [
            DomainIndex(
                tmp_path / "skills-test-index.md",
                "skills-test-index",
                "test",
            )
        ]

        result = check_memory_index_references(
            tmp_path,
            indices,
            Counter(),
        )

        assert result.passed is False
        assert result.unreferenced_indices == ["skills-test-index"]

    def test_canonical_reference_link_satisfies_completeness(
        self, tmp_path: Path
    ) -> None:
        create_memory_structure(tmp_path, {
            "memory-index.md": (
                "| keywords: [entry][domain]\n\n"
                "[domain]: ./skills-test-index.md\n"
            ),
            "skills-test-index.md": "content",
        })
        indices = [
            DomainIndex(
                tmp_path / "skills-test-index.md",
                "skills-test-index",
                "test",
            )
        ]

        result = check_memory_index_references(
            tmp_path,
            indices,
            Counter(),
        )

        assert result.passed is True
        assert result.unreferenced_indices == []

    def test_parser_nesting_exhaustion_fails_closed(
        self, tmp_path: Path
    ) -> None:
        quote = ">" * 20 + " "
        create_memory_structure(tmp_path, {
            "memory-index.md": (
                f"{quote}[entry](skills-test-index.md)\n"
            ),
            "skills-test-index.md": "content",
        })
        indices = [
            DomainIndex(
                tmp_path / "skills-test-index.md",
                "skills-test-index",
                "test",
            )
        ]

        result = check_memory_index_references(
            tmp_path,
            indices,
            Counter(),
        )

        assert result.passed is False
        assert any(
            "maxNesting" in issue
            for issue in result.issues
        )

    def test_duplicate_target_path(self, tmp_path: Path) -> None:
        create_memory_structure(tmp_path, {
            "memory-index.md": (
                "| first keywords: [first](shared.md)\n"
                "| second keywords: [second](shared.md)\n"
            ),
            "shared.md": "content",
        })

        result = check_memory_index_references(tmp_path, [], Counter())

        assert result.passed is False
        assert result.duplicate_references == ["shared"]
        assert any("P0 DUPLICATE" in issue for issue in result.issues)

    def test_space_separated_links_count_as_duplicates(
        self, tmp_path: Path
    ) -> None:
        create_memory_structure(tmp_path, {
            "memory-index.md": (
                "| keywords | [one](shared.md) [two](shared.md) |\n"
            ),
            "shared.md": "content",
        })

        result = check_memory_index_references(
            tmp_path,
            [],
            Counter(),
        )

        assert result.passed is False
        assert result.duplicate_references == ["shared"]

    def test_unparsed_file_cell_content_rejected(
        self, tmp_path: Path
    ) -> None:
        create_memory_structure(tmp_path, {
            "memory-index.md": (
                "| keywords | file |\n"
                "|---|---|\n"
                "| keywords | prefix [entry](shared.md) |\n"
            ),
            "shared.md": "content",
        })

        result = check_memory_index_references(
            tmp_path,
            [],
            Counter(),
        )

        assert result.passed is False
        assert any(
            "unparsed content" in issue
            for issue in result.issues
        )

    @pytest.mark.parametrize(
        "reference_content",
        [
            "[two][dup]\n\n[dup]: shared.md\n",
            "[two][]\n\n[two]: shared.md\n",
            "[dup]\n\n[dup]: shared.md\n",
        ],
    )
    def test_reference_links_resolve_and_count(
        self,
        tmp_path: Path,
        reference_content: str,
    ) -> None:
        create_memory_structure(tmp_path, {
            "memory-index.md": (
                "[one](shared.md)\n\n"
                f"{reference_content}"
            ),
            "shared.md": "content",
        })

        result = check_memory_index_references(
            tmp_path,
            [],
            Counter(),
        )

        assert result.passed is False
        assert result.duplicate_references == ["shared"]

    @pytest.mark.parametrize(
        "unsupported_content",
        [
            "| hidden | [two][missing] |\n",
            (
                "| hidden | "
                "[outer [inner](shared.md)](other.md) |\n"
            ),
            (
                "| hidden | "
                "[outer ![inner](shared.md)](other.md) |\n"
            ),
        ],
    )
    def test_unresolved_or_nested_link_syntax_fails_closed(
        self,
        tmp_path: Path,
        unsupported_content: str,
    ) -> None:
        create_memory_structure(tmp_path, {
            "memory-index.md": unsupported_content,
            "shared.md": "content",
            "other.md": "content",
        })

        result = check_memory_index_references(
            tmp_path,
            [],
            Counter(),
        )

        assert result.passed is False
        assert any(
            "unresolved link syntax" in issue
            or "images are unsupported" in issue
            for issue in result.issues
        )

    def test_unsupported_link_syntax_in_code_is_ignored(
        self, tmp_path: Path
    ) -> None:
        create_memory_structure(tmp_path, {
            "memory-index.md": (
                "| direct | [one](shared.md) |\n"
                "`[inline][ref]`\n"
                "```markdown\n"
                "[ref]: shared.md\n"
                "[outer [inner](shared.md)](other.md)\n"
                "```\n"
            ),
            "shared.md": "content",
        })

        result = check_memory_index_references(
            tmp_path,
            [],
            Counter(),
        )

        assert result.passed is True
        assert result.duplicate_references == []

    def test_normal_inline_links_still_pass(
        self, tmp_path: Path
    ) -> None:
        create_memory_structure(tmp_path, {
            "memory-index.md": (
                "| first | [one](shared.md) |\n"
                "| second | [two](other.md) |\n"
            ),
            "shared.md": "content",
            "other.md": "content",
        })

        result = check_memory_index_references(
            tmp_path,
            [],
            Counter(),
        )

        assert result.passed is True

    @pytest.mark.parametrize(
        "multiline_link",
        [
            "[two](\nshared.md\n)",
            '[two](shared.md\n "title")',
        ],
    )
    def test_multiline_link_duplicate_counted(
        self, tmp_path: Path, multiline_link: str
    ) -> None:
        create_memory_structure(tmp_path, {
            "memory-index.md": (
                "| direct: [one](shared.md)\n"
                f"| hidden: {multiline_link}\n"
            ),
            "shared.md": "content",
        })

        result = check_memory_index_references(
            tmp_path,
            [],
            Counter(),
        )

        assert result.passed is False
        assert result.duplicate_references == ["shared"]

    def test_invalid_backtick_fence_does_not_hide_link(
        self, tmp_path: Path
    ) -> None:
        create_memory_structure(tmp_path, {
            "memory-index.md": (
                "| direct: [one](shared.md)\n"
                "``` bad`info\n"
                "| hidden: [two](shared.md)\n"
                "```\n"
            ),
            "shared.md": "content",
        })

        result = check_memory_index_references(
            tmp_path,
            [],
            Counter(),
        )

        assert result.passed is False
        assert result.duplicate_references == ["shared"]

    def test_valid_fences_and_code_spans_ignore_links(
        self, tmp_path: Path
    ) -> None:
        create_memory_structure(tmp_path, {
            "memory-index.md": (
                "| direct: [one](shared.md)\n"
                "`[inline](shared.md)`\n"
                "````markdown\n"
                "[fenced](shared.md)\n"
                "````\n"
                "~~~markdown\n"
                "[tilde](shared.md)\n"
                "~~~\n"
            ),
            "shared.md": "content",
        })

        result = check_memory_index_references(
            tmp_path,
            [],
            Counter(),
        )

        assert result.passed is True

    @pytest.mark.parametrize(
        "raw_html",
        [
            "<span>[hidden](shared.md)</span>",
            "<span><em>[hidden](shared.md)</em></span>",
            "<!-- [hidden](shared.md) -->",
        ],
    )
    def test_raw_html_does_not_contribute_links(
        self,
        tmp_path: Path,
        raw_html: str,
    ) -> None:
        create_memory_structure(tmp_path, {
            "memory-index.md": (
                "| direct: [one](shared.md)\n"
                f"{raw_html}\n"
            ),
            "shared.md": "content",
        })

        result = check_memory_index_references(
            tmp_path,
            [],
            Counter(),
        )

        assert result.passed is True
        assert result.duplicate_references == []

    def test_link_after_void_raw_html_still_counts(
        self, tmp_path: Path
    ) -> None:
        create_memory_structure(tmp_path, {
            "memory-index.md": (
                "| direct: [one](shared.md)\n"
                "<br> [two](shared.md)\n"
            ),
            "shared.md": "content",
        })

        result = check_memory_index_references(
            tmp_path,
            [],
            Counter(),
        )

        assert result.passed is False
        assert result.duplicate_references == ["shared"]

    def test_dot_alias_counts_as_same_target(self, tmp_path: Path) -> None:
        create_memory_structure(tmp_path, {
            "memory-index.md": (
                "| first keywords: [first](shared.md)\n"
                "| second keywords: [second](./shared.md)\n"
            ),
            "shared.md": "content",
        })

        result = check_memory_index_references(tmp_path, [], Counter())

        assert result.passed is False
        assert result.duplicate_references == ["shared"]

    def test_section_relative_alias_counts_as_same_target(
        self, tmp_path: Path
    ) -> None:
        create_memory_structure(tmp_path, {
            "memory-index.md": (
                "| first keywords: [first](shared.md)\n"
                "| second keywords: [second](section/../shared.md)\n"
            ),
            "shared.md": "content",
        })

        result = check_memory_index_references(tmp_path, [], Counter())

        assert result.passed is False
        assert result.duplicate_references == ["shared"]

    def test_case_alias_uses_platform_case_semantics(
        self, tmp_path: Path
    ) -> None:
        create_memory_structure(tmp_path, {
            "memory-index.md": (
                "| first keywords: [first](Shared.md)\n"
                "| second keywords: [second](shared.md)\n"
            ),
            "Shared.md": "content",
            "shared.md": "content",
        })

        with patch(
            "scripts.validation.memory_index.os.path.normcase",
            side_effect=lambda value: value.lower(),
        ):
            result = check_memory_index_references(tmp_path, [], Counter())

        assert result.passed is False
        assert result.duplicate_references == ["shared"]

    @pytest.mark.parametrize(
        ("destination", "decoy_path"),
        [
            ("shared%2Emd", "shared%2Emd.md"),
            ("shared.md(foo)", "shared.md(foo).md"),
            ("shared.md?view", "shared.md?view.md"),
            ("shared.md#section", "shared.md#section.md"),
        ],
    )
    def test_ambiguous_markdown_destination_rejected(
        self,
        tmp_path: Path,
        destination: str,
        decoy_path: str,
    ) -> None:
        decoy = tmp_path / decoy_path
        decoy.parent.mkdir(parents=True, exist_ok=True)
        decoy.write_text("content")
        (tmp_path / "memory-index.md").write_text(
            f"| keywords: [entry]({destination})\n"
        )

        result = check_memory_index_references(
            tmp_path,
            [],
            Counter(),
        )

        assert result.passed is False
        assert any(
            "destination" in issue
            for issue in result.issues
        )
        assert result.duplicate_references == []

    @pytest.mark.parametrize(
        "destination",
        [
            "shared&period;md",
            "<shared.md>",
            'shared.md "title"',
            r"shared\.md",
        ],
    )
    def test_parser_normalized_alias_counts_as_duplicate(
        self, tmp_path: Path, destination: str
    ) -> None:
        create_memory_structure(tmp_path, {
            "memory-index.md": (
                "| direct: [one](shared.md)\n"
                f"| alias: [two]({destination})\n"
            ),
            "shared.md": "content",
        })

        result = check_memory_index_references(
            tmp_path,
            [],
            Counter(),
        )

        assert result.passed is False
        assert result.duplicate_references == ["shared"]

    def test_symbolic_link_target_rejected(
        self, tmp_path: Path
    ) -> None:
        (tmp_path / "target.md").write_text("content")
        (tmp_path / "shared.md").symlink_to("target.md")
        (tmp_path / "memory-index.md").write_text(
            "| keywords: [entry](shared.md)\n"
        )

        result = check_memory_index_references(
            tmp_path,
            [],
            Counter(),
        )

        assert result.passed is False
        assert any(
            "symbolic link" in issue
            for issue in result.issues
        )

    def test_symbolic_link_ancestor_rejected(
        self, tmp_path: Path
    ) -> None:
        target_dir = tmp_path / "target"
        target_dir.mkdir()
        (target_dir / "shared.md").write_text("content")
        (tmp_path / "alias").symlink_to(target_dir, target_is_directory=True)
        (tmp_path / "memory-index.md").write_text(
            "| keywords: [entry](alias/shared.md)\n"
        )

        result = check_memory_index_references(
            tmp_path,
            [],
            Counter(),
        )

        assert result.passed is False
        assert any(
            "symbolic link" in issue
            for issue in result.issues
        )

    @pytest.mark.parametrize(
        ("base_count", "head_count", "expected_pass"),
        [
            (2, 2, True),
            (2, 1, True),
            (1, 2, False),
            (0, 2, False),
            (2, 3, False),
        ],
    )
    def test_duplicate_count_cannot_exceed_base(
        self,
        tmp_path: Path,
        base_count: int,
        head_count: int,
        expected_pass: bool,
    ) -> None:
        file_name = "shared"
        (tmp_path / "shared.md").write_text("content")
        rows = "".join(
            f"| keywords {index}: [entry {index}]({file_name}.md)\n"
            for index in range(head_count)
        )
        (tmp_path / "memory-index.md").write_text(rows)
        base_counts = Counter({file_name: base_count})

        result = check_memory_index_references(
            tmp_path,
            [],
            base_counts,
        )

        assert result.passed is expected_pass
        expected_duplicates = [] if expected_pass else [file_name]
        assert result.duplicate_references == expected_duplicates
        if not expected_pass:
            allowed_count = max(base_count, 1)
            assert any(
                f"{head_count} times, allowed {allowed_count}" in issue
                for issue in result.issues
            )

    @pytest.mark.parametrize(
        "file_name",
        [
            "adr-reference-index",
            "memory/memory-token-efficiency",
            "memory/passive-context-vs-skills-vercel-research",
            "project/project-labels-milestones",
            "skills-copilot-index",
        ],
    )
    def test_inherited_duplicate_alias_exceeding_limit_fails(
        self, tmp_path: Path, file_name: str
    ) -> None:
        target = tmp_path / f"{file_name}.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("content")
        (tmp_path / "memory-index.md").write_text(
            f"| first keywords: [first]({file_name}.md)\n"
            f"| second keywords: [second]({file_name}.md)\n"
            f"| third keywords: [third](./{file_name}.md)\n"
        )

        result = check_memory_index_references(
            tmp_path,
            [],
            Counter({file_name: 2}),
        )

        assert result.passed is False
        assert result.duplicate_references == [file_name]
        assert any(
            "3 times, allowed 2" in issue
            for issue in result.issues
        )

    def test_unreferenced_generic_domain_index(self, tmp_path: Path) -> None:
        """Completeness covers every ADR-017 {domain}-index file."""
        create_memory_structure(tmp_path, {
            "memory-index.md": "| Keywords | File |\n|----------|------|\n",
            "quality-index.md": "| Keywords | File |\n|----------|------|\n",
        })

        result = check_memory_index_references(tmp_path, [], Counter())

        assert result.passed is False
        assert result.unreferenced_indices == ["quality-index"]

    def test_comment_and_link_label_do_not_satisfy_completeness(
        self, tmp_path: Path
    ) -> None:
        """Only an exact lookup target makes a domain index retrievable."""
        create_memory_structure(tmp_path, {
            "memory-index.md": (
                "| hidden: <!-- [quality](quality-index.md) -->\n"
                "| label: [quality-index](other.md)\n"
            ),
            "quality-index.md": "| Keywords | File |\n|----------|------|\n",
            "other.md": "other",
        })

        result = check_memory_index_references(tmp_path, [], Counter())

        assert result.passed is False
        assert result.unreferenced_indices == ["quality-index"]

    def test_broken_reference(self, tmp_path: Path) -> None:
        create_memory_structure(tmp_path, {
            "memory-index.md": (
                "| Keywords | File |\n"
                "|----------|------|\n"
                "| test | nonexistent-file |\n"
            ),
        })
        result = check_memory_index_references(tmp_path, [], Counter())
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
        result = check_memory_index_references(tmp_path, indices, Counter())
        assert result.passed is True
        assert not result.broken_references

    def test_pipe_delimited_format(self, tmp_path: Path) -> None:
        """Pipe-delimited memory-index format is validated correctly."""
        create_memory_structure(tmp_path, {
            "memory-index.md": (
                "# Memory Index\n\n"
                "[Session and Protocol]\n"
                "|session start init: [skills-session-init-index](skills-session-init-index.md)\n"
            ),
            "skills-session-init-index.md": "content",
        })
        indices = [
            DomainIndex(
                tmp_path / "skills-session-init-index.md",
                "skills-session-init-index",
                "session",
            )
        ]
        result = check_memory_index_references(tmp_path, indices, Counter())
        assert result.passed is True
        assert not result.broken_references

    def test_pipe_delimited_broken_reference(self, tmp_path: Path) -> None:
        """Pipe-delimited format detects broken references."""
        create_memory_structure(tmp_path, {
            "memory-index.md": (
                "[Section]\n"
                "|keywords: [nonexistent](nonexistent.md)\n"
            ),
        })
        result = check_memory_index_references(tmp_path, [], Counter())
        assert result.passed is False
        assert "nonexistent" in result.broken_references

    def test_pipe_delimited_multiple_links(self, tmp_path: Path) -> None:
        """Pipe-delimited format with multiple comma-separated links."""
        create_memory_structure(tmp_path, {
            "memory-index.md": (
                "[Section]\n"
                "|keywords: [index-a](index-a.md), [index-b](index-b.md)\n"
            ),
            "index-a.md": "content",
            "index-b.md": "content",
        })
        result = check_memory_index_references(tmp_path, [], Counter())
        assert result.passed is True
        assert not result.broken_references

    def test_duplicate_link_targets_fail(self, tmp_path: Path) -> None:
        """Issue #4705: memory-index must not point at one target twice."""
        create_memory_structure(tmp_path, {
            "memory-index.md": (
                "[Section]\n"
                "|alpha beta: [one](shared.md)\n"
                "|gamma delta: [also one](shared.md)\n"
            ),
            "shared.md": "content",
        })

        result = check_memory_index_references(tmp_path, [])

        assert result.passed is False
        assert "shared" in result.duplicate_references
        assert any("Duplicate memory-index target" in issue for issue in result.issues)

    def test_duplicate_alias_link_targets_fail(self, tmp_path: Path) -> None:
        create_memory_structure(tmp_path, {
            "memory-index.md": (
                "[Section]\n"
                "|alpha beta: [one](shared.md)\n"
                "|gamma delta: [also one](./shared.md)\n"
            ),
            "shared.md": "content",
        })

        result = check_memory_index_references(tmp_path, [])

        assert result.passed is False
        assert "shared" in result.duplicate_references
        assert any("Duplicate memory-index target" in issue for issue in result.issues)

    def test_path_traversal_detected(self, tmp_path: Path) -> None:
        memory_path = tmp_path / "memories"
        create_memory_structure(memory_path, {
            "memory-index.md": (
                "| Keywords | File |\n"
                "|----------|------|\n"
                "| evil | ../outside |\n"
                "| alias | .././outside |\n"
            ),
        })
        (tmp_path / "outside.md").write_text("content")

        result = check_memory_index_references(memory_path, [], Counter())

        assert result.passed is False
        assert any("Path traversal" in i for i in result.issues)
        assert result.duplicate_references == []


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
                "| test | "
                "[skills-test-index](skills-test-index.md) |\n"
            ),
        })
        report = run_validation(tmp_path, "json", Counter())
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
        report = run_validation(tmp_path, "json", Counter())
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
        report = run_validation(tmp_path, "json", Counter())
        assert report.summary.total_domains == 2
        assert "d1" in report.domain_results
        assert "d2" in report.domain_results

    def test_no_domains_no_memory_index(self, tmp_path: Path) -> None:
        """Empty directory with no memory-index.md fails P1 validation."""
        report = run_validation(tmp_path, "json", Counter())
        assert report.passed is False
        assert report.summary.total_domains == 0
        assert report.memory_index_result is not None
        assert any("not found" in i for i in report.memory_index_result.issues)

    def test_no_domains_with_memory_index(self, tmp_path: Path) -> None:
        """Directory with memory-index.md but no domain indices passes."""
        create_memory_structure(tmp_path, {
            "memory-index.md": "| Keywords | File |\n|----------|------|\n",
        })
        report = run_validation(tmp_path, "json", Counter())
        assert report.passed is True
        assert report.summary.total_domains == 0

    def test_orphaned_file_fails_validation(self, tmp_path: Path) -> None:
        """An orphaned file must set report.passed = False (#4313).

        Before this fix, find_orphaned_files() emitted a warning but did not
        set report.passed = False, so memory_index.py --ci exited 0 even
        when orphans were present.
        """
        create_memory_structure(tmp_path, {
            "skills-test-index.md": (
                "| Keywords | File |\n"
                "|----------|------|\n"
                "| alpha beta gamma delta epsilon | test-indexed |\n"
            ),
            "test-indexed.md": "indexed content",
            "test-orphan.md": "not in any index",
            "memory-index.md": (
                "| Keywords | File |\n"
                "|----------|------|\n"
                "| test | [skills-test-index](skills-test-index.md) |\n"
            ),
        })
        report = run_validation(tmp_path, "json", Counter())
        assert report.passed is False, (
            "orphaned file must cause report.passed = False (#4313)"
        )
        assert len(report.orphans) >= 1
        assert any(o.file == "test-orphan" for o in report.orphans)

    def test_no_orphans_passes(self, tmp_path: Path) -> None:
        """All files indexed: validation passes (negative control for #4313)."""
        create_memory_structure(tmp_path, {
            "skills-test-index.md": (
                "| Keywords | File |\n"
                "|----------|------|\n"
                "| alpha beta gamma delta epsilon | test-indexed |\n"
            ),
            "test-indexed.md": "indexed content",
            "memory-index.md": (
                "| Keywords | File |\n"
                "|----------|------|\n"
                "| test | [skills-test-index](skills-test-index.md) |\n"
            ),
        })
        report = run_validation(tmp_path, "json", Counter())
        assert report.passed is True
        assert report.orphans == []

    def test_malformed_frontmatter_fails_validation(self, tmp_path: Path) -> None:
        """A malformed frontmatter file must set report.passed = False (#4918).

        Before this fix, memory_index.py --ci exited 0 even when a memory file
        carried unparseable YAML frontmatter, so the corruption in
        implementation-008 merged silently.
        """
        create_memory_structure(tmp_path, {
            "skills-test-index.md": (
                "| Keywords | File |\n"
                "|----------|------|\n"
                "| alpha beta gamma delta epsilon | test-indexed |\n"
            ),
            "test-indexed.md": (
                "---\n"
                "description: Constraints for artifacts (REQ/DESIGN): read it\n"
                "---\n\n"
                "indexed content\n"
            ),
            "memory-index.md": (
                "| Keywords | File |\n"
                "|----------|------|\n"
                "| test | [skills-test-index](skills-test-index.md) |\n"
            ),
        })
        report = run_validation(tmp_path, "json", Counter())
        assert report.passed is False, (
            "malformed frontmatter must cause report.passed = False (#4918)"
        )
        assert report.frontmatter_validity is not None
        assert report.frontmatter_validity.invalid_files == ["test-indexed.md"]

    def test_valid_frontmatter_passes_validation(self, tmp_path: Path) -> None:
        """Valid frontmatter is the negative control for #4918."""
        create_memory_structure(tmp_path, {
            "skills-test-index.md": (
                "| Keywords | File |\n"
                "|----------|------|\n"
                "| alpha beta gamma delta epsilon | test-indexed |\n"
            ),
            "test-indexed.md": (
                "---\n"
                "description: Constraints for artifacts, read spec first\n"
                "---\n\n"
                "indexed content\n"
            ),
            "memory-index.md": (
                "| Keywords | File |\n"
                "|----------|------|\n"
                "| test | [skills-test-index](skills-test-index.md) |\n"
            ),
        })
        report = run_validation(tmp_path, "json", Counter())
        assert report.passed is True
        assert report.frontmatter_validity is not None
        assert report.frontmatter_validity.passed is True


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
        report = run_validation(tmp_path, "json", Counter())
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
        report = run_validation(tmp_path, "json", Counter())
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
        report = run_validation(tmp_path, "json", Counter())
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

    @pytest.fixture(autouse=True)
    def base_reference_counts(self) -> object:
        with patch(
            "scripts.validation.memory_index._load_base_reference_counts",
            return_value=(Counter(), None),
        ):
            yield

    def test_nonexistent_path_no_ci(
        self, tmp_path: Path
    ) -> None:
        exit_code = main(["--path", str(tmp_path / "missing")])
        assert exit_code == 0

    def test_nonexistent_path_ci(self, tmp_path: Path) -> None:
        exit_code = main(["--path", str(tmp_path / "missing"), "--ci"])
        assert exit_code == 2

    def test_empty_dir_passes(
        self, tmp_path: Path
    ) -> None:
        exit_code = main(["--path", str(tmp_path)])
        assert exit_code == 0

    def test_base_reference_failure_fails_closed(
        self, tmp_path: Path
    ) -> None:
        (tmp_path / "memory-index.md").write_text("")
        with patch(
            "scripts.validation.memory_index._load_base_reference_counts",
            return_value=(None, "base unavailable"),
        ):
            exit_code = main(["--path", str(tmp_path), "--ci"])
        assert exit_code == 2

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
                "| test | "
                "[skills-test-index](skills-test-index.md) |\n"
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

    def test_malformed_frontmatter_ci_fails(self, tmp_path: Path) -> None:
        """The CLI entrypoint must exit 1 on malformed frontmatter (#4918).

        Guards the report-to-CLI wiring: an in-process report failure that never
        reached main() could silently green the gate.
        """
        create_memory_structure(tmp_path, {
            "skills-test-index.md": (
                "| Keywords | File |\n"
                "|----------|------|\n"
                "| alpha beta gamma delta epsilon | test-indexed |\n"
            ),
            "test-indexed.md": (
                "---\n"
                "description: Constraints for artifacts (REQ/DESIGN): read it\n"
                "---\n\n"
                "indexed content\n"
            ),
            "memory-index.md": (
                "| Keywords | File |\n"
                "|----------|------|\n"
                "| test | [skills-test-index](skills-test-index.md) |\n"
            ),
        })
        exit_code = main(["--path", str(tmp_path), "--ci"])
        assert exit_code == 1

    def test_malformed_frontmatter_markdown_reports_file(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Markdown output must name the malformed file, not just FAILED (#4918).

        Without a frontmatter section the markdown report shows a generic
        FAILED status with no filename or remediation.
        """
        create_memory_structure(tmp_path, {
            "skills-test-index.md": (
                "| Keywords | File |\n"
                "|----------|------|\n"
                "| alpha beta gamma delta epsilon | test-indexed |\n"
            ),
            "test-indexed.md": (
                "---\n"
                "description: Constraints for artifacts (REQ/DESIGN): read it\n"
                "---\n\n"
                "indexed content\n"
            ),
            "memory-index.md": (
                "| Keywords | File |\n"
                "|----------|------|\n"
                "| test | [skills-test-index](skills-test-index.md) |\n"
            ),
        })
        exit_code = main(
            ["--path", str(tmp_path), "--format", "markdown", "--ci"]
        )
        assert exit_code == 1
        out = capsys.readouterr().out
        assert "## Malformed Frontmatter" in out
        assert "test-indexed.md" in out

    def test_inherited_memory_index_target_over_limit_ci_fails(
        self, tmp_path: Path
    ) -> None:
        create_memory_structure(tmp_path, {
            "memory-index.md": (
                "| first keywords: [first](skills-copilot-index.md)\n"
                "| second keywords: [second](skills-copilot-index.md)\n"
                "| third keywords: [third](skills-copilot-index.md)\n"
            ),
            "skills-copilot-index.md": "content",
        })

        exit_code = main(["--path", str(tmp_path), "--ci"])

        assert exit_code == 1

    def test_inherited_memory_index_target_at_baseline_ci_passes(
        self, tmp_path: Path
    ) -> None:
        create_memory_structure(tmp_path, {
            "memory-index.md": (
                "| first keywords: [first](skills-copilot-index.md)\n"
                "| second keywords: [second](skills-copilot-index.md)\n"
                "| third keywords: [third](skills-copilot-index.md)\n"
            ),
            "skills-copilot-index.md": "content",
        })

        with patch(
            "scripts.validation.memory_index._load_base_reference_counts",
            return_value=(
                Counter({"skills-copilot-index": 3}),
                None,
            ),
        ):
            exit_code = main(["--path", str(tmp_path), "--ci"])

        assert exit_code == 0

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
                "| test | "
                "[skills-test-index](skills-test-index.md) |\n"
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
    ) -> None:
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
        self, tmp_path: Path
    ) -> None:
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

    def test_defaults(self) -> None:
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


# ---------------------------------------------------------------------------
# check_naming_convention
# ---------------------------------------------------------------------------


class TestCheckNamingConvention:
    """Tests for kebab-case naming convention validation."""

    def test_valid_kebab_case_passes(self, tmp_path: Path) -> None:
        (tmp_path / "valid-memory-name.md").write_text("content")
        (tmp_path / "another-file.md").write_text("content")
        result = check_naming_convention(tmp_path)
        assert result.passed is True
        assert result.violations == []

    def test_uppercase_detected(self, tmp_path: Path) -> None:
        (tmp_path / "SkillForge-observations.md").write_text("content")
        result = check_naming_convention(tmp_path)
        assert result.passed is False
        assert len(result.violations) == 1
        assert "SkillForge-observations.md" in result.violations[0]

    def test_dots_in_name_detected(self, tmp_path: Path) -> None:
        (tmp_path / "roadmap-v0.3.0-items.md").write_text("content")
        result = check_naming_convention(tmp_path)
        assert result.passed is False
        assert len(result.violations) == 1

    def test_underscores_detected(self, tmp_path: Path) -> None:
        (tmp_path / "some_underscore_name.md").write_text("content")
        result = check_naming_convention(tmp_path)
        assert result.passed is False
        assert len(result.violations) == 1

    def test_special_names_excluded(self, tmp_path: Path) -> None:
        (tmp_path / "README.md").write_text("content")
        (tmp_path / "CLAUDE.md").write_text("content")
        result = check_naming_convention(tmp_path)
        assert result.passed is True
        assert result.violations == []

    def test_subdirectory_files_checked(self, tmp_path: Path) -> None:
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (subdir / "Valid-Name.md").write_text("content")
        result = check_naming_convention(tmp_path)
        assert result.passed is False
        assert len(result.violations) == 1
        assert "subdir/Valid-Name.md" in result.violations[0]

    def test_non_kebab_directory_detected(self, tmp_path: Path) -> None:
        subdir = tmp_path / "Sub_Dir"
        subdir.mkdir()
        (subdir / "valid-file.md").write_text("content")
        result = check_naming_convention(tmp_path)
        assert result.passed is False
        assert len(result.violations) == 1
        assert "Sub_Dir/valid-file.md" in result.violations[0]

    def test_special_name_in_non_kebab_directory_detected(self, tmp_path: Path) -> None:
        subdir = tmp_path / "Sub_Dir"
        subdir.mkdir()
        (subdir / "README.md").write_text("content")
        result = check_naming_convention(tmp_path)
        assert result.passed is False
        assert len(result.violations) == 1
        assert "Sub_Dir/README.md" in result.violations[0]

    def test_nonexistent_path_passes(self, tmp_path: Path) -> None:
        result = check_naming_convention(tmp_path / "does-not-exist")
        assert result.passed is True

    def test_empty_directory_passes(self, tmp_path: Path) -> None:
        result = check_naming_convention(tmp_path)
        assert result.passed is True


# ---------------------------------------------------------------------------
# check_frontmatter_validity (issue #4918)
# ---------------------------------------------------------------------------


_VALID_FRONTMATTER = """\
---
title: Valid memory
description: A plain description with no problematic punctuation
---

# Body
"""

# Unquoted value containing a colon-space: yaml reads it as a nested mapping
# and raises. This is the exact corruption repaired in implementation-008.
_MALFORMED_FRONTMATTER = """\
---
title: Broken memory
description: Constraints for spec artifacts (REQ/DESIGN/TASK): read first
---

# Body
"""

# No leading frontmatter block. Optional per issue #4900, must not flag.
_NO_FRONTMATTER = """\
# Plain markdown

Body text with a colon: value that is not frontmatter.
"""

# A horizontal rule appears later in the body, not at the top. Must not flag.
_HR_LATER = """\
# Plain markdown

Intro paragraph.

---

Second section after a horizontal rule.
"""

# Opening delimiter with no closing '---'. frontmatter.loads accepted this as
# empty metadata; the tightened check must flag it (issue #4918).
_UNCLOSED_DELIMITER = """\
---
title: Broken memory
description: never closed

# Body that was meant to follow frontmatter
"""

# Block parses to a YAML list, not a mapping. Must flag (issue #4918).
_LIST_METADATA = """\
---
- one
- two
---

# Body
"""

# Block parses to a bare scalar, not a mapping. Must flag (issue #4918).
_SCALAR_METADATA = """\
---
just a bare string scalar
---

# Body
"""

# Empty frontmatter block carries no metadata and no colon-space corruption.
# It stays valid (issue #4900): frontmatter is optional.
_EMPTY_FRONTMATTER = """\
---
---

# Body
"""

# python-frontmatter's boundary is `^-{3,}\\s*$`, so four dashes open a real
# block for the canonical loader: it raises YAMLError and prints the #4918
# warning. A gate keying on `== "---"` stayed silent on these two shapes, which
# is the false negative a differential probe found (PR #4985 review).
_MALFORMED_FOUR_DASH = """\
----
description: Constraints for spec artifacts (REQ/DESIGN/TASK): read first
----

# Body
"""

_MALFORMED_FIVE_DASH = """\
-----
description: Constraints for spec artifacts (REQ/DESIGN/TASK): read first
-----

# Body
"""

# Opening and closing dash counts differ. The canonical split takes the next
# boundary line whatever its width, so this parses and must not be flagged.
_VALID_MIXED_DASH_WIDTHS = """\
---
title: Valid memory
-----

# Body
"""

# `--- ---` is not a boundary under `^-{3,}\\s*$`: the trailing dashes are not
# whitespace. Plain Markdown, no frontmatter, no violation.
_DASHES_WITH_TRAILING_TEXT = """\
--- ---

Body text with a colon: value that is not frontmatter.
"""


class TestCheckFrontmatterValidity:
    """Tests for YAML frontmatter validity validation (issue #4918)."""

    def test_valid_frontmatter_passes(self, tmp_path: Path) -> None:
        (tmp_path / "valid-memory.md").write_text(_VALID_FRONTMATTER)
        result = check_frontmatter_validity(tmp_path)
        assert result.passed is True
        assert result.invalid_files == []

    def test_malformed_frontmatter_detected(self, tmp_path: Path) -> None:
        (tmp_path / "broken-memory.md").write_text(_MALFORMED_FRONTMATTER)
        result = check_frontmatter_validity(tmp_path)
        assert result.passed is False
        assert result.invalid_files == ["broken-memory.md"]
        assert "Malformed YAML frontmatter" in result.issues[0]
        assert "broken-memory.md" in result.issues[0]

    def test_missing_frontmatter_passes(self, tmp_path: Path) -> None:
        (tmp_path / "plain-memory.md").write_text(_NO_FRONTMATTER)
        result = check_frontmatter_validity(tmp_path)
        assert result.passed is True
        assert result.invalid_files == []

    def test_later_horizontal_rule_passes(self, tmp_path: Path) -> None:
        (tmp_path / "hr-memory.md").write_text(_HR_LATER)
        result = check_frontmatter_validity(tmp_path)
        assert result.passed is True
        assert result.invalid_files == []

    def test_unclosed_delimiter_detected(self, tmp_path: Path) -> None:
        # frontmatter.loads returned empty metadata here; the tightened check
        # must fail on the missing closing delimiter (issue #4918).
        (tmp_path / "unclosed-memory.md").write_text(_UNCLOSED_DELIMITER)
        result = check_frontmatter_validity(tmp_path)
        assert result.passed is False
        assert result.invalid_files == ["unclosed-memory.md"]
        assert "unclosed" in result.issues[0]

    def test_list_metadata_detected(self, tmp_path: Path) -> None:
        # A YAML list is not a metadata mapping; must be flagged (issue #4918).
        (tmp_path / "list-memory.md").write_text(_LIST_METADATA)
        result = check_frontmatter_validity(tmp_path)
        assert result.passed is False
        assert result.invalid_files == ["list-memory.md"]
        assert "must be a mapping" in result.issues[0]

    def test_scalar_metadata_detected(self, tmp_path: Path) -> None:
        # A bare scalar is not a metadata mapping; must be flagged (issue #4918).
        (tmp_path / "scalar-memory.md").write_text(_SCALAR_METADATA)
        result = check_frontmatter_validity(tmp_path)
        assert result.passed is False
        assert result.invalid_files == ["scalar-memory.md"]
        assert "must be a mapping" in result.issues[0]

    def test_empty_frontmatter_block_passes(self, tmp_path: Path) -> None:
        # An empty block carries no corruption; optional frontmatter (#4900).
        (tmp_path / "empty-fm-memory.md").write_text(_EMPTY_FRONTMATTER)
        result = check_frontmatter_validity(tmp_path)
        assert result.passed is True
        assert result.invalid_files == []

    def test_four_dash_delimiter_malformed_detected(self, tmp_path: Path) -> None:
        # Four dashes open a block for python-frontmatter (`^-{3,}\s*$`), so
        # the loader warns while a `== "---"` check stayed silent (PR #4985).
        (tmp_path / "four-dash-memory.md").write_text(_MALFORMED_FOUR_DASH)
        result = check_frontmatter_validity(tmp_path)
        assert result.passed is False
        assert result.invalid_files == ["four-dash-memory.md"]

    def test_five_dash_delimiter_malformed_detected(self, tmp_path: Path) -> None:
        (tmp_path / "five-dash-memory.md").write_text(_MALFORMED_FIVE_DASH)
        result = check_frontmatter_validity(tmp_path)
        assert result.passed is False
        assert result.invalid_files == ["five-dash-memory.md"]

    def test_mixed_delimiter_widths_pass(self, tmp_path: Path) -> None:
        # The canonical split closes at the next boundary of any width, so a
        # `---` open with a `-----` close is valid, not an unclosed block.
        (tmp_path / "mixed-memory.md").write_text(_VALID_MIXED_DASH_WIDTHS)
        result = check_frontmatter_validity(tmp_path)
        assert result.passed is True
        assert result.invalid_files == []

    def test_dashes_with_trailing_text_not_frontmatter(
        self, tmp_path: Path
    ) -> None:
        # Widening the delimiter must not widen it into `--- ---`, which the
        # canonical boundary rejects because `-` is not whitespace.
        (tmp_path / "hr-text-memory.md").write_text(_DASHES_WITH_TRAILING_TEXT)
        result = check_frontmatter_validity(tmp_path)
        assert result.passed is True
        assert result.invalid_files == []

    @pytest.mark.parametrize(
        "content",
        [
            _MALFORMED_FRONTMATTER,
            _MALFORMED_FOUR_DASH,
            _MALFORMED_FIVE_DASH,
        ],
        ids=["three-dash", "four-dash", "five-dash"],
    )
    def test_gate_flags_every_shape_the_loader_warns_about(
        self, tmp_path: Path, content: str
    ) -> None:
        """Differential guard: no false negative against the canonical parser.

        The gate exists to stop what `memory_enhancement verify-all` only warns
        about, so the loader raising `yaml.YAMLError` and the gate staying
        silent is the one failure that makes it decorative. Driving the real
        `frontmatter.loads` here means a future upstream change to
        `FM_BOUNDARY` fails this test rather than silently reopening the gap.
        """
        with pytest.raises(yaml.YAMLError):
            frontmatter.loads(content)

        (tmp_path / "probe-memory.md").write_text(content)
        result = check_frontmatter_validity(tmp_path)
        assert result.passed is False, (
            "canonical loader raised YAMLError but the gate stayed silent"
        )
        assert result.invalid_files == ["probe-memory.md"]

    def test_only_malformed_flagged_in_mixed_tree(self, tmp_path: Path) -> None:
        (tmp_path / "good.md").write_text(_VALID_FRONTMATTER)
        (tmp_path / "plain.md").write_text(_NO_FRONTMATTER)
        (tmp_path / "bad.md").write_text(_MALFORMED_FRONTMATTER)
        result = check_frontmatter_validity(tmp_path)
        assert result.passed is False
        assert result.invalid_files == ["bad.md"]

    def test_subdirectory_files_checked(self, tmp_path: Path) -> None:
        subdir = tmp_path / "implementation"
        subdir.mkdir()
        (subdir / "impl-bad.md").write_text(_MALFORMED_FRONTMATTER)
        result = check_frontmatter_validity(tmp_path)
        assert result.passed is False
        assert result.invalid_files == ["implementation/impl-bad.md"]

    def test_trash_dir_files_checked(self, tmp_path: Path) -> None:
        # The canonical loader (serena_integration.load_memories) scans hidden
        # directories, so a malformed `.trash/*.md` still breaks it. This gate
        # must flag it too, not skip it (PR #4985 review).
        dotdir = tmp_path / ".trash"
        dotdir.mkdir()
        (dotdir / "bad.md").write_text(_MALFORMED_FRONTMATTER)
        result = check_frontmatter_validity(tmp_path)
        assert result.passed is False
        assert result.invalid_files == [".trash/bad.md"]

    def test_readme_and_claude_skipped(self, tmp_path: Path) -> None:
        # The canonical loader skips these two names; this gate skips them too,
        # so a doc file with no frontmatter is never a violation (PR #4985).
        (tmp_path / "README.md").write_text(_MALFORMED_FRONTMATTER)
        (tmp_path / "CLAUDE.md").write_text(_MALFORMED_FRONTMATTER)
        result = check_frontmatter_validity(tmp_path)
        assert result.passed is True
        assert result.invalid_files == []

    def test_nonexistent_path_passes(self, tmp_path: Path) -> None:
        result = check_frontmatter_validity(tmp_path / "does-not-exist")
        assert result.passed is True

    def test_empty_directory_passes(self, tmp_path: Path) -> None:
        result = check_frontmatter_validity(tmp_path)
        assert result.passed is True


# ---------------------------------------------------------------------------
# Enforcement: orphan detection must fail validation (issue #4313)
# ---------------------------------------------------------------------------


class TestOrphanEnforcesFailure:
    """Orphaned files must set report.passed = False."""

    def test_orphan_sets_passed_false(self, tmp_path: Path) -> None:
        """A skill-prefixed file not in any index makes validation fail."""
        create_memory_structure(tmp_path, {
            "memory-index.md": "| Keywords | File |\n|----------|------|\n",
            "skills-orphaned.md": "content",  # skill-prefix, not in any index
        })
        report = run_validation(tmp_path, "json", Counter())
        assert report.passed is False
        assert len(report.orphans) > 0

    def test_no_orphans_does_not_fail(self, tmp_path: Path) -> None:
        """A directory with no orphans and a valid memory-index passes."""
        create_memory_structure(tmp_path, {
            "memory-index.md": "| Keywords | File |\n|----------|------|\n",
        })
        report = run_validation(tmp_path, "json", Counter())
        assert report.passed is True
        assert report.orphans == []
