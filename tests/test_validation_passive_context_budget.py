"""Tests for scripts.validation.passive_context_budget module.

Validates file measurement, budget checking, output formatting, CLI, and
CWE-22 path traversal protection.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from scripts.validation.passive_context_budget import (
    DEFAULT_BUDGETS,
    FileResult,
    _resolve_safe,
    build_parser,
    format_json,
    format_table,
    main,
    measure_file,
    parse_budget_override,
    validate_passive_context,
)

# ---------------------------------------------------------------------------
# FileResult
# ---------------------------------------------------------------------------


class TestFileResult:
    """Tests for FileResult dataclass properties."""

    def test_usage_percent_normal(self) -> None:
        r = FileResult(path="a.md", exists=True, size_bytes=100, estimated_tokens=500, budget=1000)
        assert r.usage_percent == 50.0

    def test_usage_percent_zero_budget(self) -> None:
        r = FileResult(path="a.md", exists=True, size_bytes=100, estimated_tokens=500, budget=0)
        assert r.usage_percent == 0.0

    def test_over_budget_false(self) -> None:
        r = FileResult(path="a.md", exists=True, size_bytes=100, estimated_tokens=500, budget=1000)
        assert r.over_budget is False

    def test_over_budget_true(self) -> None:
        r = FileResult(path="a.md", exists=True, size_bytes=100, estimated_tokens=1500, budget=1000)
        assert r.over_budget is True

    def test_over_budget_exact(self) -> None:
        r = FileResult(path="a.md", exists=True, size_bytes=100, estimated_tokens=1000, budget=1000)
        assert r.over_budget is False

    def test_frozen(self) -> None:
        r = FileResult(path="a.md", exists=True, size_bytes=100, estimated_tokens=500, budget=1000)
        with pytest.raises(AttributeError):
            r.path = "b.md"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# _resolve_safe (CWE-22)
# ---------------------------------------------------------------------------


class TestResolveSafe:
    """Tests for CWE-22 path traversal protection."""

    def test_normal_relative_path(self, tmp_path: Path) -> None:
        (tmp_path / "AGENTS.md").touch()
        result = _resolve_safe(tmp_path, "AGENTS.md")
        assert result is not None
        assert result == (tmp_path / "AGENTS.md").resolve()

    def test_nested_path(self, tmp_path: Path) -> None:
        nested = tmp_path / ".claude"
        nested.mkdir()
        (nested / "CLAUDE.md").touch()
        result = _resolve_safe(tmp_path, ".claude/CLAUDE.md")
        assert result is not None

    def test_traversal_blocked(self, tmp_path: Path) -> None:
        result = _resolve_safe(tmp_path, "../../../etc/passwd")
        assert result is None

    def test_dot_dot_in_middle_blocked(self, tmp_path: Path) -> None:
        result = _resolve_safe(tmp_path, "subdir/../../etc/passwd")
        assert result is None

    def test_root_path_itself(self, tmp_path: Path) -> None:
        result = _resolve_safe(tmp_path, ".")
        assert result is not None


# ---------------------------------------------------------------------------
# measure_file
# ---------------------------------------------------------------------------


class TestMeasureFile:
    """Tests for single file measurement."""

    def test_existing_file(self, tmp_path: Path) -> None:
        content = "Hello world. " * 100
        (tmp_path / "test.md").write_text(content, encoding="utf-8")
        result = measure_file(tmp_path, "test.md", 2000)
        assert result.exists is True
        assert result.size_bytes > 0
        assert result.estimated_tokens > 0
        assert result.budget == 2000

    def test_missing_file(self, tmp_path: Path) -> None:
        result = measure_file(tmp_path, "missing.md", 2000)
        assert result.exists is False
        assert result.size_bytes == 0
        assert result.estimated_tokens == 0

    def test_traversal_path(self, tmp_path: Path) -> None:
        result = measure_file(tmp_path, "../../../etc/passwd", 2000)
        assert result.exists is False

    def test_empty_file(self, tmp_path: Path) -> None:
        (tmp_path / "empty.md").write_text("", encoding="utf-8")
        result = measure_file(tmp_path, "empty.md", 2000)
        assert result.exists is True
        assert result.estimated_tokens == 0

    def test_large_file_over_budget(self, tmp_path: Path) -> None:
        content = "x" * 40000
        (tmp_path / "big.md").write_text(content, encoding="utf-8")
        result = measure_file(tmp_path, "big.md", 100)
        assert result.over_budget is True


# ---------------------------------------------------------------------------
# validate_passive_context
# ---------------------------------------------------------------------------


class TestValidatePassiveContext:
    """Tests for multi-file validation."""

    def test_all_files_present(self, tmp_path: Path) -> None:
        (tmp_path / "AGENTS.md").write_text("# Agents\nSmall content.", encoding="utf-8")
        (tmp_path / "CLAUDE.md").write_text("# Claude\nSmall content.", encoding="utf-8")
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        (claude_dir / "CLAUDE.md").write_text("# Project\nSmall.", encoding="utf-8")

        results = validate_passive_context(tmp_path, DEFAULT_BUDGETS)
        assert len(results) == 3
        assert all(r.exists for r in results)
        assert all(not r.over_budget for r in results)

    def test_missing_files_skipped(self, tmp_path: Path) -> None:
        results = validate_passive_context(tmp_path, {"missing.md": 1000})
        assert len(results) == 1
        assert results[0].exists is False

    def test_sorted_by_path(self, tmp_path: Path) -> None:
        budgets = {"z.md": 100, "a.md": 100, "m.md": 100}
        results = validate_passive_context(tmp_path, budgets)
        paths = [r.path for r in results]
        assert paths == sorted(paths)

    def test_custom_budgets(self, tmp_path: Path) -> None:
        (tmp_path / "test.md").write_text("content", encoding="utf-8")
        results = validate_passive_context(tmp_path, {"test.md": 5000})
        assert results[0].budget == 5000


# ---------------------------------------------------------------------------
# format_table
# ---------------------------------------------------------------------------


class TestFormatTable:
    """Tests for table output formatting."""

    def test_contains_header(self) -> None:
        results = [FileResult("a.md", True, 1024, 500, 1000)]
        output = format_table(results)
        assert "File" in output
        assert "Tokens" in output
        assert "Budget" in output

    def test_pass_status(self) -> None:
        results = [FileResult("a.md", True, 1024, 500, 1000)]
        output = format_table(results)
        assert "PASS" in output

    def test_fail_status(self) -> None:
        results = [FileResult("a.md", True, 1024, 1500, 1000)]
        output = format_table(results)
        assert "FAIL" in output

    def test_skip_for_missing(self) -> None:
        results = [FileResult("missing.md", False, 0, 0, 1000)]
        output = format_table(results)
        assert "SKIP" in output

    def test_multiple_files(self) -> None:
        results = [
            FileResult("a.md", True, 1024, 500, 1000),
            FileResult("b.md", True, 2048, 1500, 1000),
        ]
        output = format_table(results)
        assert "a.md" in output
        assert "b.md" in output


# ---------------------------------------------------------------------------
# format_json
# ---------------------------------------------------------------------------


class TestFormatJson:
    """Tests for JSON output formatting."""

    def test_valid_json(self) -> None:
        results = [FileResult("a.md", True, 1024, 500, 1000)]
        output = format_json(results)
        data = json.loads(output)
        assert isinstance(data, list)
        assert len(data) == 1

    def test_json_fields(self) -> None:
        results = [FileResult("a.md", True, 1024, 500, 1000)]
        data = json.loads(format_json(results))
        entry = data[0]
        assert entry["path"] == "a.md"
        assert entry["exists"] is True
        assert entry["estimated_tokens"] == 500
        assert entry["budget"] == 1000
        assert entry["usage_percent"] == 50.0
        assert entry["over_budget"] is False

    def test_empty_results(self) -> None:
        data = json.loads(format_json([]))
        assert data == []


# ---------------------------------------------------------------------------
# parse_budget_override
# ---------------------------------------------------------------------------


class TestParseBudgetOverride:
    """Tests for budget override parsing."""

    def test_valid_override(self) -> None:
        path, tokens = parse_budget_override("AGENTS.md:3000")
        assert path == "AGENTS.md"
        assert tokens == 3000

    def test_nested_path(self) -> None:
        path, tokens = parse_budget_override(".claude/CLAUDE.md:5000")
        assert path == ".claude/CLAUDE.md"
        assert tokens == 5000

    def test_invalid_format(self) -> None:
        with pytest.raises(argparse.ArgumentTypeError):
            parse_budget_override("no-colon")

    def test_non_integer_tokens(self) -> None:
        with pytest.raises(argparse.ArgumentTypeError):
            parse_budget_override("file.md:abc")

    def test_zero_tokens(self) -> None:
        with pytest.raises(argparse.ArgumentTypeError):
            parse_budget_override("file.md:0")

    def test_negative_tokens(self) -> None:
        with pytest.raises(argparse.ArgumentTypeError):
            parse_budget_override("file.md:-100")


# ---------------------------------------------------------------------------
# build_parser
# ---------------------------------------------------------------------------


class TestBuildParser:
    """Tests for CLI argument parsing."""

    def test_defaults(self) -> None:
        parser = build_parser()
        args = parser.parse_args([])
        assert args.output_format == "table"
        assert args.budget == []

    def test_ci_flag(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--ci"])
        assert args.ci is True

    def test_json_format(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--format", "json"])
        assert args.output_format == "json"

    def test_budget_overrides(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--budget", "a.md:1000", "--budget", "b.md:2000"])
        assert len(args.budget) == 2

    def test_custom_path(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--path", "/tmp/test"])
        assert args.path == "/tmp/test"


# ---------------------------------------------------------------------------
# main (integration)
# ---------------------------------------------------------------------------


class TestMain:
    """Integration tests for main entry point."""

    def test_pass_within_budget(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        (tmp_path / "AGENTS.md").write_text("# Small file", encoding="utf-8")
        exit_code = main(["--path", str(tmp_path), "--budget", "AGENTS.md:2000"])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "PASS" in captured.out

    def test_fail_ci_mode(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        content = "x" * 40000
        (tmp_path / "AGENTS.md").write_text(content, encoding="utf-8")
        exit_code = main(["--path", str(tmp_path), "--ci", "--budget", "AGENTS.md:100"])
        assert exit_code == 1
        captured = capsys.readouterr()
        assert "FAIL" in captured.out

    def test_fail_non_ci_returns_zero(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("CI", raising=False)
        content = "x" * 40000
        (tmp_path / "AGENTS.md").write_text(content, encoding="utf-8")
        exit_code = main(["--path", str(tmp_path), "--budget", "AGENTS.md:100"])
        assert exit_code == 0

    def test_invalid_path(self, tmp_path: Path) -> None:
        exit_code = main(["--path", str(tmp_path / "nonexistent")])
        assert exit_code == 2

    def test_json_output(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        (tmp_path / "AGENTS.md").write_text("# Test", encoding="utf-8")
        exit_code = main([
            "--path", str(tmp_path),
            "--format", "json",
            "--budget", "AGENTS.md:2000",
        ])
        assert exit_code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert isinstance(data, list)

    def test_default_budgets_used(self, tmp_path: Path) -> None:
        exit_code = main(["--path", str(tmp_path)])
        assert exit_code == 0

    def test_budget_override_applied(self, tmp_path: Path) -> None:
        (tmp_path / "custom.md").write_text("content", encoding="utf-8")
        exit_code = main([
            "--path", str(tmp_path),
            "--budget", "custom.md:5000",
        ])
        assert exit_code == 0
