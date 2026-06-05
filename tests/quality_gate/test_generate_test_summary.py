"""Tests for scripts/quality_gate/generate_test_summary.py.

Pins the behavior of the extracted ``Generate test summary`` workflow step.
"""

from __future__ import annotations

from pathlib import Path

from scripts.quality_gate.generate_test_summary import (
    build_summary,
    main,
    write_summary,
)


# ---------------------------------------------------------------------------
# build_summary
# ---------------------------------------------------------------------------


class TestBuildSummary:
    def test_includes_status_and_summary(self) -> None:
        out = build_summary("PASS", "12 passed in 1.2s")
        assert "## Pre-executed Test Results" in out
        assert "### pytest (Python)" in out
        assert "- **Status**: PASS" in out
        assert "- **Summary**: 12 passed in 1.2s" in out

    def test_trailing_newline_present(self) -> None:
        out = build_summary("FAIL", "1 failed")
        assert out.endswith("\n")

    def test_skipped_status_renders(self) -> None:
        out = build_summary("SKIPPED", "Python test environment not available")
        assert "- **Status**: SKIPPED" in out


# ---------------------------------------------------------------------------
# write_summary
# ---------------------------------------------------------------------------


class TestWriteSummary:
    def test_writes_heredoc_block(self, tmp_path: Path) -> None:
        output = tmp_path / "out"
        output.touch()
        write_summary(output, "BODY\n")
        text = output.read_text(encoding="utf-8")
        lines = text.splitlines()
        assert lines[0].startswith("test_summary<<EOF_SUMMARY_")
        delimiter = lines[0].split("<<", 1)[1]
        assert "BODY" in lines
        # Heredoc must be closed by the same delimiter token.
        assert lines[-1] == delimiter

    def test_appends_not_truncates(self, tmp_path: Path) -> None:
        output = tmp_path / "out"
        output.write_text("existing=1\n", encoding="utf-8")
        write_summary(output, "BODY\n")
        text = output.read_text(encoding="utf-8")
        assert text.startswith("existing=1\n")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


class TestMain:
    def test_writes_output_and_returns_zero(self, tmp_path, monkeypatch) -> None:
        output = tmp_path / "gh_output"
        output.touch()
        monkeypatch.setenv("GITHUB_OUTPUT", str(output))
        rc = main(["--pytest-status", "PASS", "--pytest-summary", "5 passed"])
        assert rc == 0
        text = output.read_text(encoding="utf-8")
        assert "test_summary<<EOF_SUMMARY_" in text
        assert "- **Status**: PASS" in text
        assert "- **Summary**: 5 passed" in text

    def test_defaults_from_env(self, tmp_path, monkeypatch) -> None:
        output = tmp_path / "gh_output"
        output.touch()
        monkeypatch.setenv("GITHUB_OUTPUT", str(output))
        monkeypatch.setenv("PYTEST_STATUS", "FAIL")
        monkeypatch.setenv("PYTEST_SUMMARY", "2 failed")
        rc = main([])
        assert rc == 0
        text = output.read_text(encoding="utf-8")
        assert "- **Status**: FAIL" in text
        assert "- **Summary**: 2 failed" in text

    def test_missing_github_output_returns_two(self, monkeypatch) -> None:
        monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
        rc = main(["--pytest-status", "PASS", "--pytest-summary", "ok"])
        assert rc == 2

    def test_default_status_is_skipped(self, tmp_path, monkeypatch) -> None:
        output = tmp_path / "gh_output"
        output.touch()
        monkeypatch.setenv("GITHUB_OUTPUT", str(output))
        monkeypatch.delenv("PYTEST_STATUS", raising=False)
        monkeypatch.delenv("PYTEST_SUMMARY", raising=False)
        rc = main([])
        assert rc == 0
        text = output.read_text(encoding="utf-8")
        assert "- **Status**: SKIPPED" in text
        assert "- **Summary**: Not executed" in text
