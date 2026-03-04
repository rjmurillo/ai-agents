"""Tests for write_output and write_github_output GitHub Actions helpers.

Validates that multiline values use heredoc delimiter format to prevent
GitHub Actions from misinterpreting subsequent lines (issue #1386).
"""

from __future__ import annotations

from pathlib import Path

from scripts.ai_review_common import write_github_output, write_output


def _read_outputs(output_file: Path) -> dict[str, str]:
    """Parse GitHub Actions output file supporting both formats."""
    lines = output_file.read_text().splitlines()
    result: dict[str, str] = {}
    i = 0
    while i < len(lines):
        line = lines[i]
        if "<<" in line:
            key, delimiter = line.split("<<", 1)
            value_lines: list[str] = []
            i += 1
            while i < len(lines) and lines[i] != delimiter:
                value_lines.append(lines[i])
                i += 1
            result[key] = "\n".join(value_lines)
            i += 1
        elif "=" in line:
            k, v = line.split("=", 1)
            result[k] = v
            i += 1
        else:
            i += 1
    return result


class TestWriteOutput:
    def test_single_line_uses_simple_format(self, tmp_path, monkeypatch):
        output_file = tmp_path / "output"
        output_file.touch()
        monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))

        write_output("count", "42")

        raw = output_file.read_text()
        assert raw == "count=42\n"

    def test_multiline_uses_heredoc_format(self, tmp_path, monkeypatch):
        output_file = tmp_path / "output"
        output_file.touch()
        monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))

        write_output("details", "  - file1.py\n  - file2.py")

        raw = output_file.read_text()
        assert "details=" not in raw.split("\n")[0] or "<<" in raw.split("\n")[0]
        assert "details<<ghadelimiter_details" in raw
        assert "ghadelimiter_details" in raw

        outputs = _read_outputs(output_file)
        assert outputs["details"] == "  - file1.py\n  - file2.py"

    def test_empty_value_uses_simple_format(self, tmp_path, monkeypatch):
        output_file = tmp_path / "output"
        output_file.touch()
        monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))

        write_output("result", "")

        raw = output_file.read_text()
        assert raw == "result=\n"

    def test_no_output_file_is_noop(self, monkeypatch):
        monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
        # Should not raise
        write_output("key", "value\nwith\nnewlines")


class TestWriteGithubOutput:
    def test_multiline_uses_heredoc(self, tmp_path, monkeypatch):
        output_file = tmp_path / "output"
        output_file.touch()
        monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))

        write_github_output({
            "simple": "value",
            "multi": "line1\nline2",
        })

        outputs = _read_outputs(output_file)
        assert outputs["simple"] == "value"
        assert outputs["multi"] == "line1\nline2"

        raw = output_file.read_text()
        assert "simple=value" in raw
        assert "multi<<ghadelimiter_multi" in raw
