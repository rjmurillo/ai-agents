"""Tests for detect_test_coverage_gaps.py PowerShell test coverage detection."""

from __future__ import annotations

from pathlib import Path

from scripts.detect_test_coverage_gaps import (
    find_test_file,
    load_ignore_patterns,
    should_ignore,
)


class TestShouldIgnore:
    def test_ignores_test_files(self) -> None:
        patterns = [r"\.Tests\.ps1$"]
        assert should_ignore("scripts/Foo.Tests.ps1", patterns) is True

    def test_does_not_ignore_regular_files(self) -> None:
        patterns = [r"\.Tests\.ps1$"]
        assert should_ignore("scripts/Foo.ps1", patterns) is False

    def test_ignores_build_directory(self) -> None:
        patterns = [r"build[/\\]"]
        assert should_ignore("build/output.ps1", patterns) is True

    def test_empty_patterns_ignores_nothing(self) -> None:
        assert should_ignore("any/file.ps1", []) is False


class TestLoadIgnorePatterns:
    def test_loads_patterns_from_file(self, tmp_path: Path) -> None:
        ignore = tmp_path / "ignore.txt"
        ignore.write_text("pattern1\n# comment\npattern2\n\n", encoding="utf-8")
        patterns = load_ignore_patterns(str(ignore))
        assert patterns == ["pattern1", "pattern2"]

    def test_returns_empty_for_missing_file(self) -> None:
        assert load_ignore_patterns("/nonexistent/file") == []


class TestFindTestFile:
    def test_finds_test_in_same_directory(self, tmp_path: Path) -> None:
        (tmp_path / "Foo.ps1").write_text("", encoding="utf-8")
        (tmp_path / "Foo.Tests.ps1").write_text("", encoding="utf-8")
        assert find_test_file("Foo.ps1", tmp_path) is True

    def test_finds_test_in_tests_subdirectory(self, tmp_path: Path) -> None:
        (tmp_path / "tests").mkdir()
        (tmp_path / "Foo.ps1").write_text("", encoding="utf-8")
        (tmp_path / "tests" / "Foo.Tests.ps1").write_text("", encoding="utf-8")
        assert find_test_file("Foo.ps1", tmp_path) is True

    def test_returns_false_when_no_test(self, tmp_path: Path) -> None:
        (tmp_path / "Foo.ps1").write_text("", encoding="utf-8")
        assert find_test_file("Foo.ps1", tmp_path) is False
