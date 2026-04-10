"""Tests for scripts.validation.passive_context_budget module.

Validates passive context file measurement, budget checking, and CLI behavior.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.validation.passive_context_budget import (
    FileResult,
    build_parser,
    main,
    measure_file,
    print_json,
    print_report,
    validate_passive_context,
)

# ---------------------------------------------------------------------------
# FileResult
# ---------------------------------------------------------------------------


class TestFileResult:
    """Tests for FileResult dataclass properties."""

    def test_within_budget_when_under(self) -> None:
        r = FileResult(
            path="test.md",
            label="Test",
            exists=True,
            size_bytes=100,
            char_count=100,
            estimated_tokens=500,
            max_tokens=1000,
        )
        assert r.within_budget is True

    def test_within_budget_when_over(self) -> None:
        r = FileResult(
            path="test.md",
            label="Test",
            exists=True,
            size_bytes=100,
            char_count=100,
            estimated_tokens=1500,
            max_tokens=1000,
        )
        assert r.within_budget is False

    def test_within_budget_when_equal(self) -> None:
        r = FileResult(
            path="test.md",
            label="Test",
            exists=True,
            size_bytes=100,
            char_count=100,
            estimated_tokens=1000,
            max_tokens=1000,
        )
        assert r.within_budget is True

    def test_within_budget_missing_file(self) -> None:
        r = FileResult(
            path="missing.md",
            label="Missing",
            exists=False,
            size_bytes=0,
            char_count=0,
            estimated_tokens=0,
            max_tokens=1000,
        )
        assert r.within_budget is True

    def test_usage_percent(self) -> None:
        r = FileResult(
            path="test.md",
            label="Test",
            exists=True,
            size_bytes=100,
            char_count=100,
            estimated_tokens=750,
            max_tokens=1000,
        )
        assert r.usage_percent == 75.0

    def test_usage_percent_zero_budget(self) -> None:
        r = FileResult(
            path="test.md",
            label="Test",
            exists=True,
            size_bytes=100,
            char_count=100,
            estimated_tokens=100,
            max_tokens=0,
        )
        assert r.usage_percent == 0.0

    def test_size_kb(self) -> None:
        r = FileResult(
            path="test.md",
            label="Test",
            exists=True,
            size_bytes=2048,
            char_count=2048,
            estimated_tokens=500,
            max_tokens=1000,
        )
        assert r.size_kb == 2.0


# ---------------------------------------------------------------------------
# measure_file
# ---------------------------------------------------------------------------


class TestMeasureFile:
    """Tests for measuring individual files."""

    def test_missing_file_returns_zero_tokens(self, tmp_path: Path) -> None:
        target = {"path": "nonexistent.md", "max_tokens": 1000, "label": "Test"}
        result = measure_file(tmp_path, target)
        assert result.exists is False
        assert result.estimated_tokens == 0
        assert result.within_budget is True

    def test_existing_file_measures_tokens(self, tmp_path: Path) -> None:
        test_file = tmp_path / "test.md"
        test_file.write_text("Hello world, this is test content.", encoding="utf-8")
        target = {"path": "test.md", "max_tokens": 5000, "label": "Test"}
        result = measure_file(tmp_path, target)
        assert result.exists is True
        assert result.estimated_tokens > 0
        assert result.size_bytes > 0
        assert result.char_count > 0
        assert result.within_budget is True

    def test_large_file_exceeds_budget(self, tmp_path: Path) -> None:
        test_file = tmp_path / "big.md"
        test_file.write_text("x" * 10000, encoding="utf-8")
        target = {"path": "big.md", "max_tokens": 10, "label": "Big"}
        result = measure_file(tmp_path, target)
        assert result.exists is True
        assert result.within_budget is False

    def test_default_label_uses_path(self, tmp_path: Path) -> None:
        test_file = tmp_path / "agents.md"
        test_file.write_text("content", encoding="utf-8")
        target = {"path": "agents.md", "max_tokens": 5000}
        result = measure_file(tmp_path, target)
        assert result.label == "agents.md"

    def test_nested_path(self, tmp_path: Path) -> None:
        nested = tmp_path / "sub" / "dir"
        nested.mkdir(parents=True)
        test_file = nested / "index.md"
        test_file.write_text("nested content", encoding="utf-8")
        target = {"path": "sub/dir/index.md", "max_tokens": 5000, "label": "Nested"}
        result = measure_file(tmp_path, target)
        assert result.exists is True
        assert result.estimated_tokens > 0


# ---------------------------------------------------------------------------
# validate_passive_context
# ---------------------------------------------------------------------------


class TestValidatePassiveContext:
    """Tests for the main validation logic."""

    def test_all_within_budget_returns_zero(self, tmp_path: Path) -> None:
        f1 = tmp_path / "a.md"
        f1.write_text("small content", encoding="utf-8")
        targets = [{"path": "a.md", "max_tokens": 5000, "label": "A"}]
        results, code = validate_passive_context(tmp_path, targets, ci=True)
        assert code == 0
        assert all(r.within_budget for r in results)

    def test_over_budget_ci_returns_one(self, tmp_path: Path) -> None:
        f1 = tmp_path / "a.md"
        f1.write_text("x" * 10000, encoding="utf-8")
        targets = [{"path": "a.md", "max_tokens": 10, "label": "A"}]
        results, code = validate_passive_context(tmp_path, targets, ci=True)
        assert code == 1

    def test_over_budget_non_ci_returns_zero(self, tmp_path: Path) -> None:
        f1 = tmp_path / "a.md"
        f1.write_text("x" * 10000, encoding="utf-8")
        targets = [{"path": "a.md", "max_tokens": 10, "label": "A"}]
        results, code = validate_passive_context(tmp_path, targets, ci=False)
        assert code == 0

    def test_missing_files_pass(self, tmp_path: Path) -> None:
        targets = [{"path": "missing.md", "max_tokens": 1000, "label": "Missing"}]
        results, code = validate_passive_context(tmp_path, targets, ci=True)
        assert code == 0

    def test_multiple_files_one_fails(self, tmp_path: Path) -> None:
        good = tmp_path / "good.md"
        good.write_text("ok", encoding="utf-8")
        bad = tmp_path / "bad.md"
        bad.write_text("x" * 10000, encoding="utf-8")
        targets = [
            {"path": "good.md", "max_tokens": 5000, "label": "Good"},
            {"path": "bad.md", "max_tokens": 10, "label": "Bad"},
        ]
        results, code = validate_passive_context(tmp_path, targets, ci=True)
        assert code == 1
        assert results[0].within_budget is True
        assert results[1].within_budget is False


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------


class TestPrintReport:
    """Tests for human-readable report output."""

    def test_prints_pass(self, capsys: pytest.CaptureFixture[str]) -> None:
        results = [
            FileResult(
                path="test.md",
                label="Test",
                exists=True,
                size_bytes=100,
                char_count=100,
                estimated_tokens=500,
                max_tokens=1000,
            ),
        ]
        print_report(results)
        captured = capsys.readouterr()
        assert "PASS" in captured.out
        assert "test.md" in captured.out

    def test_prints_fail(self, capsys: pytest.CaptureFixture[str]) -> None:
        results = [
            FileResult(
                path="big.md",
                label="Big",
                exists=True,
                size_bytes=10000,
                char_count=10000,
                estimated_tokens=5000,
                max_tokens=1000,
            ),
        ]
        print_report(results)
        captured = capsys.readouterr()
        assert "FAIL" in captured.out
        assert "Over budget by" in captured.out

    def test_prints_skip_for_missing(
        self, capsys: pytest.CaptureFixture[str],
    ) -> None:
        results = [
            FileResult(
                path="missing.md",
                label="Missing",
                exists=False,
                size_bytes=0,
                char_count=0,
                estimated_tokens=0,
                max_tokens=1000,
            ),
        ]
        print_report(results)
        captured = capsys.readouterr()
        assert "SKIP" in captured.out


class TestPrintJson:
    """Tests for JSON output."""

    def test_outputs_valid_json(self, capsys: pytest.CaptureFixture[str]) -> None:
        results = [
            FileResult(
                path="test.md",
                label="Test",
                exists=True,
                size_bytes=100,
                char_count=100,
                estimated_tokens=500,
                max_tokens=1000,
            ),
        ]
        print_json(results)
        captured = capsys.readouterr()
        import json

        data = json.loads(captured.out)
        assert data["all_pass"] is True
        assert len(data["files"]) == 1
        assert data["files"][0]["path"] == "test.md"
        assert data["files"][0]["within_budget"] is True


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


class TestBuildParser:
    """Tests for CLI argument parsing."""

    def test_default_path(self) -> None:
        parser = build_parser()
        args = parser.parse_args([])
        assert args.path == "."

    def test_custom_path(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--path", "/tmp/repo"])
        assert args.path == "/tmp/repo"

    def test_ci_flag(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--ci"])
        assert args.ci is True

    def test_json_flag(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--json"])
        assert args.json is True


class TestMain:
    """Integration tests for main entry point."""

    def test_invalid_path_returns_two(self) -> None:
        result = main(["--path", "/nonexistent/path/that/does/not/exist"])
        assert result == 2

    def test_valid_repo_with_no_files(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("CI", raising=False)
        result = main(["--path", str(tmp_path)])
        assert result == 0

    def test_json_output(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.delenv("CI", raising=False)
        result = main(["--path", str(tmp_path), "--json"])
        assert result == 0
        captured = capsys.readouterr()
        import json

        data = json.loads(captured.out)
        assert "files" in data
        assert "all_pass" in data
