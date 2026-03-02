"""Tests for measure_memory_performance.py."""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

SCRIPT_DIR = Path(__file__).resolve().parents[3] / ".claude" / "skills" / "memory" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import measure_memory_performance


class TestMeasureSerenaSearch:
    """Tests for measure_serena_search function."""

    def test_returns_error_for_missing_path(self):
        result = measure_memory_performance.measure_serena_search(
            "test query", "/nonexistent/path", 1, 0
        )
        assert "Error" in result

    def test_measures_existing_path(self, tmp_path):
        (tmp_path / "test-memory.md").write_text("# Test content here")
        result = measure_memory_performance.measure_serena_search(
            "test", str(tmp_path), 2, 1
        )
        assert "Error" not in result
        assert result["TotalTimeMs"] >= 0
        assert result["TotalFiles"] >= 1

    def test_counts_matched_files(self, tmp_path):
        (tmp_path / "security-scan.md").write_text("# Security")
        (tmp_path / "other-topic.md").write_text("# Other")
        result = measure_memory_performance.measure_serena_search(
            "security", str(tmp_path), 2, 0
        )
        assert result["MatchedFiles"] >= 1


class TestTestForgetfulAvailable:
    """Tests for test_forgetful_available function."""

    def test_unavailable_endpoint(self):
        result = measure_memory_performance.test_forgetful_available(
            "http://localhost:99999/fake"
        )
        assert result is False


class TestMeasureForgetfulSearch:
    """Tests for measure_forgetful_search function."""

    def test_returns_error_when_unavailable(self):
        result = measure_memory_performance.measure_forgetful_search(
            "test", "http://localhost:99999/fake", 1, 0
        )
        assert "Error" in result


class TestFormatConsole:
    """Tests for format_console function."""

    def test_prints_serena_avg(self, capsys):
        benchmark = {
            "Summary": {
                "SerenaAvgMs": 5.0,
                "ForgetfulAvgMs": 0.0,
                "SpeedupFactor": 0.0,
                "Target": "96-164x",
            }
        }
        measure_memory_performance.format_console(benchmark)
        captured = capsys.readouterr()
        assert "5.0ms" in captured.out


class TestFormatMarkdown:
    """Tests for format_markdown function."""

    def test_generates_markdown(self):
        benchmark = {
            "Configuration": {
                "Queries": 3,
                "Iterations": 5,
                "WarmupIterations": 2,
            },
            "Summary": {
                "SerenaAvgMs": 5.0,
                "ForgetfulAvgMs": 0.0,
                "SpeedupFactor": 0.0,
                "Target": "96-164x",
            },
        }
        result = measure_memory_performance.format_markdown(benchmark)
        assert "# Memory Performance Benchmark Report" in result
        assert "Serena" in result
