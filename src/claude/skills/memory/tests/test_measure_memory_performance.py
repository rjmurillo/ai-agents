#!/usr/bin/env python3
"""Tests for measure_memory_performance.py."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ..scripts.measure_memory_performance import (
    format_console,
    format_markdown,
    main,
    measure_serena_search,
)


class TestMeasureSerenaSearch:
    """Tests for Serena search benchmarking."""

    def test_missing_path(self, tmp_path: Path) -> None:
        result = measure_serena_search(
            "test", tmp_path / "missing", iterations=1, warmup_iterations=0,
        )
        assert "Error" in result

    def test_empty_directory(self, tmp_path: Path) -> None:
        result = measure_serena_search(
            "test query", tmp_path, iterations=1, warmup_iterations=0,
        )
        assert result["TotalFiles"] == 0
        assert result["MatchedFiles"] == 0
        assert result["TotalTimeMs"] >= 0

    def test_matching_files(self, tmp_path: Path) -> None:
        (tmp_path / "git-hooks.md").write_text("# Git Hooks")
        (tmp_path / "unrelated.md").write_text("# Other")

        result = measure_serena_search(
            "git hooks", tmp_path, iterations=2, warmup_iterations=1,
        )
        assert result["TotalFiles"] == 2
        assert result["MatchedFiles"] >= 1
        assert result["TotalTimeMs"] > 0
        assert len(result["IterationTimes"]) == 2

    def test_no_matches(self, tmp_path: Path) -> None:
        (tmp_path / "unrelated.md").write_text("# No match here")

        result = measure_serena_search(
            "xyznonexistent", tmp_path, iterations=1, warmup_iterations=0,
        )
        assert result["MatchedFiles"] == 0


class TestFormatConsole:
    """Tests for console format output."""

    def test_reports_serena_average(self) -> None:
        benchmark = {"Summary": {"SerenaAvgMs": 1.5}}
        output = format_console(benchmark)
        assert output == "Serena Average: 1.5ms"

    def test_reports_no_comparison_ratio(self) -> None:
        """Negative control: a one-backend benchmark reports no speedup.

        The summary used to carry `SpeedupFactor` and a claude-flow target.
        Both were ratios between two systems, so with one system they could
        only ever be zero. Reporting a zero ratio reads as a measured result.
        """
        output = format_console({"Summary": {"SerenaAvgMs": 1.5}})
        assert "Speedup" not in output
        assert "Target" not in output


class TestFormatMarkdown:
    """Tests for markdown format output."""

    def test_contains_header(self) -> None:
        benchmark = {
            "Configuration": {
                "Queries": 8,
                "Iterations": 5,
                "WarmupIterations": 2,
            },
            "Summary": {"SerenaAvgMs": 2.0},
        }
        output = format_markdown(benchmark)
        assert "# Memory Performance Benchmark Report" in output
        assert "| Queries | 8 |" in output


class TestMainFunction:
    """Tests for the main CLI entry point."""

    def test_serena_only_json(
        self, tmp_path: Path, capsys: pytest.CaptureFixture,
    ) -> None:
        serena = tmp_path / "memories"
        serena.mkdir()
        (serena / "git-hooks.md").write_text("# Git Hooks\nContent")

        result = main([
            "--format", "json",
            "--iterations", "1",
            "--warmup", "0",
            "--serena-path", str(serena),
        ])
        assert result == 0

        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert "SerenaResults" in output
        assert "Summary" in output

    def test_console_output(
        self, tmp_path: Path, capsys: pytest.CaptureFixture,
    ) -> None:
        serena = tmp_path / "memories"
        serena.mkdir()

        result = main([
            "--format", "console",
            "--iterations", "1",
            "--warmup", "0",
            "--serena-path", str(serena),
        ])
        assert result == 0

        captured = capsys.readouterr()
        assert "Memory Performance Benchmark" in captured.out

    def test_markdown_output(
        self, tmp_path: Path, capsys: pytest.CaptureFixture,
    ) -> None:
        serena = tmp_path / "memories"
        serena.mkdir()

        result = main([
            "--format", "markdown",
            "--iterations", "1",
            "--warmup", "0",
            "--serena-path", str(serena),
        ])
        assert result == 0

        captured = capsys.readouterr()
        assert "# Memory Performance Benchmark Report" in captured.out

    def test_custom_queries(
        self, tmp_path: Path, capsys: pytest.CaptureFixture,
    ) -> None:
        serena = tmp_path / "memories"
        serena.mkdir()

        result = main([
            "--format", "json",
            "--iterations", "1",
            "--warmup", "0",
            "--serena-path", str(serena),
            "--queries", "test query one", "test query two",
        ])
        assert result == 0

        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output["Configuration"]["Queries"] == 2
