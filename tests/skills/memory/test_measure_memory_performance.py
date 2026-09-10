"""Tests for measure_memory_performance.py."""

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[3] / ".claude" / "skills" / "memory" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import measure_memory_performance


class TestMeasureSerenaSearch:
    """Tests for measure_serena_search function."""

    def test_returns_error_for_missing_path(self, tmp_path):
        result = measure_memory_performance.measure_serena_search(
            "test query", tmp_path / "nonexistent", 1, 0
        )
        assert "Error" in result

    def test_measures_existing_path(self, tmp_path):
        (tmp_path / "test-memory.md").write_text("# Test content here")
        result = measure_memory_performance.measure_serena_search(
            "test", tmp_path, 2, 1
        )
        assert "Error" not in result
        assert result["TotalTimeMs"] >= 0
        assert result["TotalFiles"] >= 1

    def test_counts_matched_files(self, tmp_path):
        (tmp_path / "security-scan.md").write_text("# Security")
        (tmp_path / "other-topic.md").write_text("# Other")
        result = measure_memory_performance.measure_serena_search(
            "security", tmp_path, 2, 0
        )
        assert result["MatchedFiles"] >= 1


class TestRetiredBackendBenchmark:
    """Negative control: the second backend's benchmark path is gone."""

    def test_module_makes_no_network_call(self):
        """The benchmark must stay offline.

        It POSTed to an MCP endpoint over HTTP, which is why the module
        imported `validate_http_url` for scheme validation. With the request
        gone the validator has nothing to guard, so this asserts the absence
        of the machinery instead: the import is not a substitute for the
        request never being made.
        """
        measured = [
            name
            for name in dir(measure_memory_performance)
            if name.startswith("measure_")
        ]
        assert measured == ["measure_serena_search"]
        endpoints = [
            name
            for name in dir(measure_memory_performance)
            if name.endswith("_ENDPOINT")
        ]
        assert endpoints == []
        source = Path(measure_memory_performance.__file__).read_text(
            encoding="utf-8"
        )
        for forbidden in ("urllib", "socket", "http://"):
            assert forbidden not in source


class TestFormatConsole:
    """Tests for format_console function."""

    def test_returns_serena_avg(self):
        benchmark = {
            "Summary": {"SerenaAvgMs": 5.0}
        }
        # format_console returns a string, does not print
        result = measure_memory_performance.format_console(benchmark)
        assert "5.0ms" in result


class TestFormatMarkdown:
    """Tests for format_markdown function."""

    def test_generates_markdown(self):
        benchmark = {
            "Configuration": {
                "Queries": 3,
                "Iterations": 5,
                "WarmupIterations": 2,
            },
            "Summary": {"SerenaAvgMs": 5.0},
        }
        result = measure_memory_performance.format_markdown(benchmark)
        assert "# Memory Performance Benchmark Report" in result
        assert "Serena" in result
