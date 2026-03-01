"""Tests for validate_memory_tier.py ADR-017 memory tier validation."""

from __future__ import annotations

from pathlib import Path

from scripts.validate_memory_tier import (
    ValidationResult,
    extract_file_references,
    main,
    validate_domain_index_format,
    validate_memory_tier,
    validate_references_exist,
)


class TestExtractFileReferences:
    def test_extracts_markdown_links(self) -> None:
        content = "| kw1 | [name](foo/bar.md) |"
        refs = extract_file_references(content)
        assert refs == ["foo/bar.md"]

    def test_extracts_multiple_links(self) -> None:
        content = "[a](one.md) text [b](two/three.md)"
        refs = extract_file_references(content)
        assert refs == ["one.md", "two/three.md"]

    def test_ignores_non_md_links(self) -> None:
        content = "[link](page.html) [other](doc.md)"
        refs = extract_file_references(content)
        assert refs == ["doc.md"]


class TestValidateReferencesExist:
    def test_rejects_path_traversal(self, tmp_path: Path) -> None:
        refs = ["../../etc/passwd.md"]
        result = ValidationResult()
        validate_references_exist(refs, tmp_path, "test-source.md", result)
        assert not result.is_valid
        assert "path traversal" in result.errors[0]

    def test_allows_valid_subpath(self, tmp_path: Path) -> None:
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "valid.md").write_text("ok", encoding="utf-8")
        result = ValidationResult()
        validate_references_exist(["sub/valid.md"], tmp_path, "src.md", result)
        assert result.is_valid


class TestValidateDomainIndexFormat:
    def test_valid_pure_table(self, tmp_path: Path) -> None:
        index = tmp_path / "skills-testing-index.md"
        index.write_text(
            "| Keywords | File |\n"
            "|----------|------|\n"
            "| kw1 kw2 | [name](testing/test-skill.md) |\n",
            encoding="utf-8",
        )
        result = ValidationResult()
        validate_domain_index_format(index, result)
        assert result.is_valid

    def test_rejects_title_in_index(self, tmp_path: Path) -> None:
        index = tmp_path / "skills-bad-index.md"
        index.write_text(
            "# Bad Index Title\n\n"
            "| Keywords | File |\n"
            "|----------|------|\n"
            "| kw1 | [name](bad/skill.md) |\n",
            encoding="utf-8",
        )
        result = ValidationResult()
        validate_domain_index_format(index, result)
        assert not result.is_valid
        assert "non-table content" in result.errors[0]

    def test_rejects_prose_in_index(self, tmp_path: Path) -> None:
        index = tmp_path / "skills-prose-index.md"
        index.write_text(
            "| Keywords | File |\n"
            "|----------|------|\n"
            "| kw1 | [name](skill.md) |\n"
            "\nThis is explanatory prose.\n",
            encoding="utf-8",
        )
        result = ValidationResult()
        validate_domain_index_format(index, result)
        assert not result.is_valid


class TestValidateMemoryTier:
    def test_missing_directory(self) -> None:
        result = validate_memory_tier(Path("/nonexistent"))
        assert not result.is_valid
        assert "not found" in result.errors[0]

    def test_missing_memory_index(self, tmp_path: Path) -> None:
        result = validate_memory_tier(tmp_path)
        assert not result.is_valid
        assert "memory-index.md not found" in result.errors[0]

    def test_valid_two_tier_structure(self, tmp_path: Path) -> None:
        # Create domain directory
        domain_dir = tmp_path / "testing"
        domain_dir.mkdir()

        # Create atomic file
        (domain_dir / "testing-skill-one.md").write_text("content", encoding="utf-8")

        # Create domain index
        (tmp_path / "skills-testing-index.md").write_text(
            "| Keywords | File |\n"
            "|----------|------|\n"
            "| kw1 kw2 | [testing-skill-one](testing/testing-skill-one.md) |\n",
            encoding="utf-8",
        )

        # Create memory-index referencing the domain index
        (tmp_path / "memory-index.md").write_text(
            "| Task Keywords | Essential Memories |\n"
            "|---------------|-------------------|\n"
            "| testing | [skills-testing-index](skills-testing-index.md) |\n",
            encoding="utf-8",
        )

        result = validate_memory_tier(tmp_path)
        assert result.is_valid

    def test_broken_reference_in_memory_index(self, tmp_path: Path) -> None:
        (tmp_path / "memory-index.md").write_text(
            "| Keywords | Memories |\n"
            "|----------|----------|\n"
            "| kw | [missing](missing-index.md) |\n",
            encoding="utf-8",
        )
        result = validate_memory_tier(tmp_path)
        assert not result.is_valid
        assert "broken reference" in result.errors[0]

    def test_broken_reference_in_domain_index(self, tmp_path: Path) -> None:
        (tmp_path / "memory-index.md").write_text(
            "| Keywords | Memories |\n"
            "|----------|----------|\n"
            "| kw | [idx](skills-test-index.md) |\n",
            encoding="utf-8",
        )
        (tmp_path / "skills-test-index.md").write_text(
            "| Keywords | File |\n"
            "|----------|------|\n"
            "| kw | [ghost](test/ghost.md) |\n",
            encoding="utf-8",
        )
        result = validate_memory_tier(tmp_path)
        assert not result.is_valid
        assert any("ghost.md" in e for e in result.errors)

    def test_deprecated_skill_prefix(self, tmp_path: Path) -> None:
        domain_dir = tmp_path / "test"
        domain_dir.mkdir()
        (domain_dir / "skill-old.md").write_text("old", encoding="utf-8")

        (tmp_path / "memory-index.md").write_text(
            "| Keywords | Memories |\n"
            "|----------|----------|\n"
            "| kw | [idx](skills-test-index.md) |\n",
            encoding="utf-8",
        )
        (tmp_path / "skills-test-index.md").write_text(
            "| Keywords | File |\n"
            "|----------|------|\n"
            "| kw | [old](test/skill-old.md) |\n",
            encoding="utf-8",
        )
        result = validate_memory_tier(tmp_path)
        assert not result.is_valid
        assert any("skill-" in e for e in result.errors)

    def test_orphan_domain_index_warning(self, tmp_path: Path) -> None:
        (tmp_path / "memory-index.md").write_text(
            "| Keywords | Memories |\n"
            "|----------|----------|\n"
            "| kw | [other](other-file.md) |\n",
            encoding="utf-8",
        )
        (tmp_path / "other-file.md").write_text("content", encoding="utf-8")
        (tmp_path / "skills-orphan-index.md").write_text(
            "| Keywords | File |\n"
            "|----------|------|\n"
            "| kw | [file](orphan/file.md) |\n",
            encoding="utf-8",
        )
        result = validate_memory_tier(tmp_path)
        assert any("not referenced in memory-index" in w for w in result.warnings)


class TestMain:
    def test_nonexistent_path_fails(self) -> None:
        assert main(["--path", "/nonexistent"]) == 1

    def test_valid_structure_passes(self, tmp_path: Path) -> None:
        domain_dir = tmp_path / "testing"
        domain_dir.mkdir()
        (domain_dir / "testing-one.md").write_text("content", encoding="utf-8")

        (tmp_path / "skills-testing-index.md").write_text(
            "| Keywords | File |\n"
            "|----------|------|\n"
            "| kw | [one](testing/testing-one.md) |\n",
            encoding="utf-8",
        )
        (tmp_path / "memory-index.md").write_text(
            "| Keywords | Memories |\n"
            "|----------|----------|\n"
            "| testing | [idx](skills-testing-index.md) |\n",
            encoding="utf-8",
        )
        assert main(["--path", str(tmp_path)]) == 0

    def test_ci_mode_promotes_warnings(self, tmp_path: Path) -> None:
        (tmp_path / "memory-index.md").write_text(
            "| Keywords | Memories |\n"
            "|----------|----------|\n",
            encoding="utf-8",
        )
        (tmp_path / "skills-orphan-index.md").write_text(
            "| Keywords | File |\n"
            "|----------|------|\n",
            encoding="utf-8",
        )
        # Without --ci, warnings only (pass)
        assert main(["--path", str(tmp_path)]) == 0
        # With --ci, warnings become errors (fail)
        assert main(["--path", str(tmp_path), "--ci"]) == 1
