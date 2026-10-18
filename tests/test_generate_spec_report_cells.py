"""Table-cell escaping in generate_spec_report (issue #6506).

The reference lists enter one markdown table row. A pipe, newline, or HTML tag
must not add a column, a row, or markup.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import patch

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parents[1] / ".github" / "scripts"


def _import_script(name: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS_DIR / f"{name}.py")
    assert spec is not None, f"Could not load spec for {name}"
    assert spec.loader is not None, f"Spec for {name} has no loader"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_mod = _import_script("generate_spec_report")
main = _mod.main
_cell = _mod._cell


def _setup_output(tmp_path: Path, monkeypatch) -> Path:
    output_file = tmp_path / "github-output.txt"
    output_file.write_text("")
    monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))
    return output_file


def _make_argv(spec_refs: str = "REQ-001", issue_refs: str = "#42") -> list[str]:
    return [
        "--has-specs",
        "true",
        "--trace-verdict",
        "PASS",
        "--completeness-verdict",
        "PASS",
        "--spec-refs",
        spec_refs,
        "--issue-refs",
        issue_refs,
        "--trace-findings",
        "All traced",
        "--completeness-findings",
        "All complete",
        "--github-repository",
        "owner/repo",
        "--server-url",
        "https://github.com",
        "--run-id",
        "12345",
        "--event-name",
        "pull_request",
        "--ref-name",
        "main",
    ]


class TestCell:
    """Reference lists enter a table row, so each value must stay one inert cell (#6506)."""

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("AB#123", "AB#123"),
            ("AB#1 AB#2", "AB#1 AB#2"),
            ("*None*", "*None*"),
            ("", ""),
            ("a | b", "a \\| b"),
            ("a|b|c", "a\\|b\\|c"),
            ("back\\slash", "back\\\\slash"),
            ("x \\| y", "x \\\\\\| y"),
            ("line1\nline2\r\nline3", "line1 line2 line3"),
            ("tab\tsep\x00nul\x1besc", "tab sep nul esc"),
            ("sep\u2028one\u2029two", "sep one two"),
            ("<b>bold</b>", "&lt;b&gt;bold&lt;/b&gt;"),
            ("<!-- c -->", "&lt;!-- c --&gt;"),
            ("  padded   spaces  ", "padded spaces"),
        ],
    )
    def test_cell_value(self, value, expected):
        assert _cell(value) == expected

    def test_pipe_cannot_add_a_column_to_the_row(self, tmp_path, monkeypatch):
        _setup_output(tmp_path, monkeypatch)
        report_dir = tmp_path / "ai-review-results"
        with patch.object(_mod, "initialize_ai_review", return_value=str(report_dir)):
            report_dir.mkdir(parents=True)
            rc = main([*_make_argv(), "--azure-refs", "AB#1 | injected | cells\n| forged | row |"])
        assert rc == 0
        report = (report_dir / "spec-validation-report.md").read_text()
        row = next(ln for ln in report.splitlines() if ln.startswith("| **Azure Boards**"))
        assert row == "| **Azure Boards** | AB#1 \\| injected \\| cells \\| forged \\| row \\| |"
        assert "\n| forged" not in report

    def test_all_three_reference_cells_are_escaped(self, tmp_path, monkeypatch):
        _setup_output(tmp_path, monkeypatch)
        report_dir = tmp_path / "ai-review-results"
        with patch.object(_mod, "initialize_ai_review", return_value=str(report_dir)):
            report_dir.mkdir(parents=True)
            rc = main(
                [
                    *_make_argv(spec_refs="a|b", issue_refs="<i>#1</i>"),
                    "--azure-refs",
                    "AB#2|x",
                ]
            )
        assert rc == 0
        report = (report_dir / "spec-validation-report.md").read_text()
        assert "| **Specs** | a\\|b |" in report
        assert "| **GitHub issues** | &lt;i&gt;#1&lt;/i&gt; |" in report
        assert "| **Azure Boards** | AB#2\\|x |" in report

    def test_empty_azure_refs_still_render_the_italic_placeholder(self, tmp_path, monkeypatch):
        _setup_output(tmp_path, monkeypatch)
        report_dir = tmp_path / "ai-review-results"
        with patch.object(_mod, "initialize_ai_review", return_value=str(report_dir)):
            report_dir.mkdir(parents=True)
            rc = main(_make_argv())
        assert rc == 0
        report = (report_dir / "spec-validation-report.md").read_text()
        assert "| **Azure Boards** | *None* |" in report
