"""Tests for validate_path_normalization module.

Validates that the path normalization scanner correctly detects absolute paths
in documentation files while respecting code blocks, inline code, file
extensions, and exclusion paths.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Add build/scripts to path for imports
_BUILD_SCRIPTS = Path(__file__).resolve().parent.parent / "build" / "scripts"
sys.path.insert(0, str(_BUILD_SCRIPTS))

from validate_path_normalization import (  # noqa: E402
    FORBIDDEN_PATTERNS,
    ScanResult,
    Violation,
    collect_files,
    main,
    scan_directory,
    scan_file,
)


class TestForbiddenPatterns:
    """Verify the built-in patterns detect expected paths."""

    @pytest.mark.parametrize(
        "text",
        [
            r"See C:\Users\username\file.md",
            r"Path D:\projects\repo",
        ],
    )
    def test_windows_pattern_matches(self, text: str) -> None:
        pat = FORBIDDEN_PATTERNS[0]
        assert pat.pattern.search(text)

    @pytest.mark.parametrize(
        "text",
        [
            "/Users/developer/projects/file.md",
            "Reference: /Users/abc/test",
        ],
    )
    def test_macos_pattern_matches(self, text: str) -> None:
        pat = FORBIDDEN_PATTERNS[1]
        assert pat.pattern.search(text)

    @pytest.mark.parametrize(
        "text",
        [
            "/home/runner/config.md",
            "Path: /home/user/repo",
        ],
    )
    def test_linux_pattern_matches(self, text: str) -> None:
        pat = FORBIDDEN_PATTERNS[2]
        assert pat.pattern.search(text)

    def test_relative_paths_not_matched(self) -> None:
        relative_texts = [
            "docs/guide.md",
            "../architecture/design.md",
            ".agents/planning/PRD-feature.md",
        ]
        for text in relative_texts:
            for pat in FORBIDDEN_PATTERNS:
                assert not pat.pattern.search(text), f"{pat.name} matched '{text}'"


class TestCollectFiles:
    """Tests for file collection with extension and exclusion filtering."""

    def test_collects_md_files(self, tmp_path: Path) -> None:
        (tmp_path / "doc.md").write_text("# Hello")
        (tmp_path / "readme.txt").write_text("text")
        files = collect_files(tmp_path, [".md"], [])
        assert len(files) == 1
        assert files[0].name == "doc.md"

    def test_collects_custom_extensions(self, tmp_path: Path) -> None:
        (tmp_path / "file.txt").write_text("content")
        (tmp_path / "file.md").write_text("content")
        files = collect_files(tmp_path, [".txt"], [])
        assert len(files) == 1
        assert files[0].suffix == ".txt"

    def test_excludes_paths(self, tmp_path: Path) -> None:
        (tmp_path / "good.md").write_text("ok")
        excluded = tmp_path / "node_modules"
        excluded.mkdir()
        (excluded / "bad.md").write_text("bad")
        files = collect_files(tmp_path, [".md"], ["node_modules"])
        assert len(files) == 1
        assert files[0].name == "good.md"

    def test_returns_empty_when_no_match(self, tmp_path: Path) -> None:
        (tmp_path / "file.py").write_text("code")
        files = collect_files(tmp_path, [".md"], [])
        assert files == []

    def test_excludes_multiple_paths(self, tmp_path: Path) -> None:
        (tmp_path / "root.md").write_text("ok")
        for d in [".git", "bin", "obj"]:
            sub = tmp_path / d
            sub.mkdir()
            (sub / "file.md").write_text("content")
        files = collect_files(tmp_path, [".md"], [".git", "bin", "obj"])
        assert len(files) == 1


class TestScanFile:
    """Tests for individual file scanning logic."""

    def test_detects_windows_path(self, tmp_path: Path) -> None:
        f = tmp_path / "doc.md"
        f.write_text("See C:\\Users\\test\\file.md\n")
        violations = scan_file(f, FORBIDDEN_PATTERNS)
        assert len(violations) == 1
        assert violations[0].pattern_name == "Windows Absolute Path"

    def test_detects_macos_path(self, tmp_path: Path) -> None:
        f = tmp_path / "doc.md"
        f.write_text("Reference: /Users/developer/file.md\n")
        violations = scan_file(f, FORBIDDEN_PATTERNS)
        assert len(violations) == 1
        assert violations[0].pattern_name == "macOS User Path"

    def test_detects_linux_path(self, tmp_path: Path) -> None:
        f = tmp_path / "doc.md"
        f.write_text("Config at /home/runner/config.md\n")
        violations = scan_file(f, FORBIDDEN_PATTERNS)
        assert len(violations) == 1
        assert violations[0].pattern_name == "Linux Home Path"

    def test_detects_multiple_violations(self, tmp_path: Path) -> None:
        f = tmp_path / "doc.md"
        f.write_text(
            "Windows: C:\\path\\to\\file.md\n"
            "macOS: /Users/dev/file.md\n"
            "Linux: /home/user/file.md\n"
        )
        violations = scan_file(f, FORBIDDEN_PATTERNS)
        assert len(violations) == 3

    def test_skips_fenced_code_blocks_backtick(self, tmp_path: Path) -> None:
        f = tmp_path / "doc.md"
        f.write_text(
            "# Doc\n"
            "```\n"
            "C:\\example\\path\n"
            "```\n"
        )
        violations = scan_file(f, FORBIDDEN_PATTERNS)
        assert violations == []

    def test_skips_fenced_code_blocks_tilde(self, tmp_path: Path) -> None:
        f = tmp_path / "doc.md"
        f.write_text(
            "# Doc\n"
            "~~~\n"
            "/home/user/example\n"
            "~~~\n"
        )
        violations = scan_file(f, FORBIDDEN_PATTERNS)
        assert violations == []

    def test_skips_inline_code(self, tmp_path: Path) -> None:
        f = tmp_path / "doc.md"
        f.write_text("Use `C:\\Users\\test` for the path\n")
        violations = scan_file(f, FORBIDDEN_PATTERNS)
        assert violations == []

    def test_detects_path_outside_inline_code(self, tmp_path: Path) -> None:
        f = tmp_path / "doc.md"
        f.write_text("Use `some code` and C:\\Users\\test for the path\n")
        violations = scan_file(f, FORBIDDEN_PATTERNS)
        assert len(violations) == 1

    def test_empty_file_no_violations(self, tmp_path: Path) -> None:
        f = tmp_path / "doc.md"
        f.write_text("")
        violations = scan_file(f, FORBIDDEN_PATTERNS)
        assert violations == []

    def test_whitespace_only_file(self, tmp_path: Path) -> None:
        f = tmp_path / "doc.md"
        f.write_text("   \n   \n   ")
        violations = scan_file(f, FORBIDDEN_PATTERNS)
        assert violations == []

    def test_reports_correct_line_number(self, tmp_path: Path) -> None:
        f = tmp_path / "doc.md"
        f.write_text(
            "Line 1: Normal text\n"
            "Line 2: C:\\violation\\here.md\n"
            "Line 3: Normal text\n"
        )
        violations = scan_file(f, FORBIDDEN_PATTERNS)
        assert len(violations) == 1
        assert violations[0].line == 2

    def test_no_violations_for_relative_paths(self, tmp_path: Path) -> None:
        f = tmp_path / "doc.md"
        f.write_text(
            "See: docs/guide.md\n"
            "See: ../architecture/design.md\n"
            "See: .agents/planning/PRD-feature.md\n"
        )
        violations = scan_file(f, FORBIDDEN_PATTERNS)
        assert violations == []

    def test_code_block_tracking_across_content(self, tmp_path: Path) -> None:
        """Paths after a closed code block are still detected."""
        f = tmp_path / "doc.md"
        f.write_text(
            "```\n"
            "C:\\inside\\block\n"
            "```\n"
            "C:\\outside\\block\n"
        )
        violations = scan_file(f, FORBIDDEN_PATTERNS)
        assert len(violations) == 1
        assert violations[0].line == 4


class TestScanDirectory:
    """Tests for directory-level scanning."""

    def test_scans_all_matching_files(self, tmp_path: Path) -> None:
        (tmp_path / "a.md").write_text("ok\n")
        (tmp_path / "b.md").write_text("C:\\bad\\path\n")
        result = scan_directory(tmp_path, [".md"], [], FORBIDDEN_PATTERNS)
        assert result.files_scanned == 2
        assert len(result.violations) == 1

    def test_files_with_violations_count(self, tmp_path: Path) -> None:
        (tmp_path / "a.md").write_text("C:\\a\n")
        (tmp_path / "b.md").write_text("C:\\b\n")
        (tmp_path / "c.md").write_text("ok\n")
        result = scan_directory(tmp_path, [".md"], [], FORBIDDEN_PATTERNS)
        assert result.files_with_violations == 2


class TestScanResult:
    """Tests for ScanResult dataclass."""

    def test_files_with_violations_property(self) -> None:
        result = ScanResult(
            files_scanned=3,
            violations=[
                Violation(Path("a.md"), 1, "x", "p", "d"),
                Violation(Path("a.md"), 2, "y", "p", "d"),
                Violation(Path("b.md"), 1, "z", "p", "d"),
            ],
        )
        assert result.files_with_violations == 2


class TestMain:
    """Tests for the main entry point."""

    def test_returns_0_no_violations(self, tmp_path: Path) -> None:
        (tmp_path / "clean.md").write_text("# Clean doc\n\nRelative: docs/file.md\n")
        result = main(["--path", str(tmp_path)])
        assert result == 0

    def test_returns_0_violations_without_fail_flag(self, tmp_path: Path) -> None:
        (tmp_path / "bad.md").write_text("Path: C:\\bad\\file.md\n")
        result = main(["--path", str(tmp_path)])
        assert result == 0

    def test_returns_1_violations_with_fail_flag(self, tmp_path: Path) -> None:
        (tmp_path / "bad.md").write_text("Path: C:\\bad\\file.md\n")
        result = main(["--path", str(tmp_path), "--fail-on-violation"])
        assert result == 1

    def test_returns_0_no_files(self, tmp_path: Path) -> None:
        result = main(["--path", str(tmp_path)])
        assert result == 0

    def test_custom_extensions(self, tmp_path: Path) -> None:
        (tmp_path / "file.txt").write_text("C:\\violation\n")
        (tmp_path / "file.md").write_text("clean\n")
        result = main(["--path", str(tmp_path), "--extensions", ".txt"])
        assert result == 0  # no --fail-on-violation, so 0

    def test_custom_extensions_with_fail(self, tmp_path: Path) -> None:
        (tmp_path / "file.txt").write_text("C:\\violation\n")
        result = main([
            "--path", str(tmp_path),
            "--extensions", ".txt",
            "--fail-on-violation",
        ])
        assert result == 1

    def test_exclude_paths(self, tmp_path: Path) -> None:
        excluded = tmp_path / "vendor"
        excluded.mkdir()
        (excluded / "lib.md").write_text("C:\\vendored\n")
        (tmp_path / "root.md").write_text("clean\n")
        result = main([
            "--path", str(tmp_path),
            "--exclude-paths", "vendor",
            "--fail-on-violation",
        ])
        assert result == 0

    def test_help_flag(self) -> None:
        with pytest.raises(SystemExit) as exc_info:
            main(["--help"])
        assert exc_info.value.code == 0

    def test_output_contains_file_count(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        (tmp_path / "a.md").write_text("ok\n")
        (tmp_path / "b.md").write_text("ok\n")
        main(["--path", str(tmp_path)])
        captured = capsys.readouterr()
        assert "Files to scan: 2" in captured.out

    def test_output_shows_remediation_on_violation(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        (tmp_path / "bad.md").write_text("C:\\test\\file.md\n")
        main(["--path", str(tmp_path)])
        captured = capsys.readouterr()
        assert "Remediation Steps" in captured.out
        assert "relative path" in captured.out.lower()

    def test_output_shows_success_message(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        (tmp_path / "ok.md").write_text("All good\n")
        main(["--path", str(tmp_path)])
        captured = capsys.readouterr()
        assert "SUCCESS" in captured.out

    def test_output_shows_violation_details(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        (tmp_path / "bad.md").write_text("Line1\nC:\\violation\\here.md\nLine3\n")
        main(["--path", str(tmp_path)])
        captured = capsys.readouterr()
        assert "Line 2" in captured.out
        assert "Windows Absolute Path" in captured.out
