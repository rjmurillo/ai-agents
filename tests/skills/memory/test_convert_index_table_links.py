"""Tests for convert_index_table_links.py."""

import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parents[3] / ".claude" / "skills" / "memory" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import convert_index_table_links


class TestFindProjectRoot:
    """Tests for _find_project_root function."""

    def test_returns_path(self):
        # In a git repo, should return a valid Path
        result = convert_index_table_links._find_project_root()
        assert isinstance(result, Path)
        assert result.exists()


class TestValidatePathWithinProject:
    """Tests for _validate_path_within_project (CWE-22)."""

    def test_valid_subpath(self, tmp_path):
        child = tmp_path / "sub"
        child.mkdir()
        # Should return the resolved path without raising
        result = convert_index_table_links._validate_path_within_project(str(child), tmp_path)
        assert result == child.resolve()

    def test_rejects_sibling(self, tmp_path):
        sibling = tmp_path.parent / "sibling"
        with pytest.raises(SystemExit):
            convert_index_table_links._validate_path_within_project(str(sibling), tmp_path)


class TestBuildMemoryNames:
    """Tests for _build_memory_names function."""

    def test_returns_basenames(self, tmp_path):
        (tmp_path / "test-memory.md").write_text("# Test")
        (tmp_path / "another.md").write_text("# Another")
        names = convert_index_table_links._build_memory_names(tmp_path)
        assert "test-memory" in names
        assert "another" in names

    def test_empty_dir(self, tmp_path):
        names = convert_index_table_links._build_memory_names(tmp_path)
        assert len(names) == 0


class TestConvertSingleRefs:
    """Tests for _convert_single_refs function."""

    def test_converts_known_memory(self):
        content = "| keyword | test-memory |"
        names = {"test-memory": True}
        result = convert_index_table_links._convert_single_refs(content, names)
        assert "[test-memory](test-memory.md)" in result

    def test_skips_unknown(self):
        content = "| keyword | unknown-file |"
        names = {"test-memory": True}
        result = convert_index_table_links._convert_single_refs(content, names)
        assert "[unknown-file]" not in result

    def test_skips_existing_links(self):
        content = "| keyword | [test-memory](test-memory.md) |"
        names = {"test-memory": True}
        result = convert_index_table_links._convert_single_refs(content, names)
        assert result.count("[test-memory]") == 1

    def test_skips_separator_rows(self):
        content = "| --- | --- |"
        names = {"test": True}
        result = convert_index_table_links._convert_single_refs(content, names)
        assert "[" not in result


class TestConvertCommaRefs:
    """Tests for _convert_comma_refs function."""

    def test_converts_comma_list(self):
        content = "| file-a, file-b |"
        names = {"file-a": True, "file-b": True}
        result = convert_index_table_links._convert_comma_refs(content, names)
        assert "[file-a](file-a.md)" in result
        assert "[file-b](file-b.md)" in result

    def test_partial_conversion(self):
        content = "| file-a, unknown |"
        names = {"file-a": True}
        result = convert_index_table_links._convert_comma_refs(content, names)
        assert "[file-a](file-a.md)" in result
        assert "unknown" in result
        assert "[unknown]" not in result

    def test_skips_existing_links(self):
        content = "| [file-a](file-a.md), file-b |"
        names = {"file-a": True, "file-b": True}
        result = convert_index_table_links._convert_comma_refs(content, names)
        assert result == content


class TestCountMdLinks:
    """Tests for _count_md_links function."""

    def test_counts_links(self):
        content = "[a](a.md) and [b](b.md)"
        assert convert_index_table_links._count_md_links(content) == 2

    def test_zero_links(self):
        assert convert_index_table_links._count_md_links("no links here") == 0


class TestProcessFiles:
    """Integration test for process_files function."""

    def test_processes_index_files(self, tmp_path):
        (tmp_path / "test-memory.md").write_text("# Test Memory")
        index = tmp_path / "test-index.md"
        index.write_text("| keyword | test-memory |\n")

        stats = convert_index_table_links.process_files(tmp_path, None, True)
        assert stats["FilesProcessed"] >= 1

    def test_skips_non_index_files(self, tmp_path):
        (tmp_path / "regular.md").write_text("| keyword | test |")
        stats = convert_index_table_links.process_files(tmp_path, None, True)
        assert stats["FilesProcessed"] == 0

    def test_empty_directory(self, tmp_path):
        stats = convert_index_table_links.process_files(tmp_path, None, True)
        assert stats["FilesProcessed"] == 0
        assert stats["Errors"] == []


class TestDryRun:
    """--dry-run reports the conversions and writes nothing."""

    def _setup(self, tmp_path):
        (tmp_path / "test-memory.md").write_text("# Test Memory", encoding="utf-8")
        index = tmp_path / "test-index.md"
        index.write_text("| keyword | test-memory |\n", encoding="utf-8")
        return index

    def test_dry_run_counts_changes_but_leaves_the_index_untouched(self, tmp_path):
        index = self._setup(tmp_path)

        stats = convert_index_table_links.process_files(tmp_path, None, True, dry_run=True)

        assert stats["FilesModified"] == 1
        assert stats["LinksAdded"] >= 1
        assert index.read_text(encoding="utf-8") == "| keyword | test-memory |\n"

    def test_real_run_still_writes_the_link(self, tmp_path):
        index = self._setup(tmp_path)

        convert_index_table_links.process_files(tmp_path, None, True)

        assert "[test-memory](test-memory.md)" in index.read_text(encoding="utf-8")

    def test_dry_run_with_nothing_to_convert_modifies_zero_files(self, tmp_path):
        (tmp_path / "plain-index.md").write_text("no table here\n", encoding="utf-8")

        stats = convert_index_table_links.process_files(tmp_path, None, True, dry_run=True)

        assert stats["FilesModified"] == 0

    def test_cli_dry_run_prints_would_update_and_keeps_file(self, tmp_path, capsys):
        index = self._setup(tmp_path)

        rc = convert_index_table_links.main(
            ["--memories-path", str(tmp_path), "--skip-path-validation", "--dry-run"]
        )

        out = capsys.readouterr().out
        assert rc == 0
        assert "Would update: test-index.md" in out
        assert "Dry run complete. Would modify 1 files." in out
        assert index.read_text(encoding="utf-8") == "| keyword | test-memory |\n"


def test_json_dry_run_marks_the_stats_so_a_preview_is_not_a_write(tmp_path, capsys):
    (tmp_path / "test-memory.md").write_text("# T", encoding="utf-8")
    (tmp_path / "test-index.md").write_text("| keyword | test-memory |\n", encoding="utf-8")

    rc = convert_index_table_links.main(
        ["--memories-path", str(tmp_path), "--skip-path-validation", "--dry-run", "--output-json"]
    )

    import json

    stats = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert stats["DryRun"] is True
    assert stats["FilesModified"] == 1


def test_json_real_run_has_no_dry_run_key(tmp_path, capsys):
    (tmp_path / "test-memory.md").write_text("# T", encoding="utf-8")
    (tmp_path / "test-index.md").write_text("| keyword | test-memory |\n", encoding="utf-8")

    convert_index_table_links.main(
        ["--memories-path", str(tmp_path), "--skip-path-validation", "--output-json"]
    )

    import json

    assert "DryRun" not in json.loads(capsys.readouterr().out)
