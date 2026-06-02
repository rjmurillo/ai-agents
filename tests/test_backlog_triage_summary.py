"""Tests for scripts.backlog_triage_summary.

Covers the Phase 2 aggregator (issue #1799): mapping untrusted JSON to a typed
result, loading per-issue result files, skipping malformed input, rendering the
human-review markdown, table-cell sanitization, and the CLI entry point
including the missing-dir edge case.
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.backlog_triage_summary import (
    TriageResult,
    load_results,
    main,
    render_summary,
)


def _write_result(directory: Path, name: str, payload: dict | list | str) -> Path:
    path = directory / name
    if isinstance(payload, str):
        path.write_text(payload, encoding="utf-8")
    else:
        path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _result(
    *,
    number: int = 1,
    title: str = "t",
    verdict: str = "PASS",
    labels: tuple[str, ...] = (),
) -> TriageResult:
    return TriageResult(number=number, title=title, verdict=verdict, labels=labels)


class TestTriageResultFromRaw:
    def test_maps_full_payload(self):
        result = TriageResult.from_raw(
            {"number": 9, "title": "x", "verdict": "WARN", "labels": ["area-x"]}
        )
        assert result == TriageResult(
            number=9, title="x", verdict="WARN", labels=("area-x",)
        )

    def test_non_dict_returns_none(self):
        assert TriageResult.from_raw(["not", "a", "dict"]) is None

    def test_missing_number_returns_none(self):
        assert TriageResult.from_raw({"title": "no number"}) is None

    def test_non_integer_number_returns_none(self):
        assert TriageResult.from_raw({"number": "abc"}) is None

    def test_missing_optional_fields_default(self):
        result = TriageResult.from_raw({"number": 1})
        assert result is not None
        assert result.title == ""
        assert result.verdict == "UNKNOWN"
        assert result.labels == ()

    def test_non_list_labels_default_empty(self):
        result = TriageResult.from_raw({"number": 1, "labels": "oops"})
        assert result is not None
        assert result.labels == ()


class TestLoadResults:
    def test_loads_and_sorts_by_number(self, tmp_path: Path):
        _write_result(tmp_path, "b.json", {"number": 5, "title": "five"})
        _write_result(tmp_path, "a.json", {"number": 2, "title": "two"})
        results = load_results(tmp_path)
        assert [r.number for r in results] == [2, 5]

    def test_skips_unreadable_file(self, tmp_path: Path, capsys):
        _write_result(tmp_path, "bad.json", "{not json")
        _write_result(tmp_path, "ok.json", {"number": 1, "title": "t"})
        results = load_results(tmp_path)
        assert [r.number for r in results] == [1]
        assert "skipping unreadable" in capsys.readouterr().err

    def test_skips_result_without_number(self, tmp_path: Path, capsys):
        _write_result(tmp_path, "nonum.json", {"title": "no number"})
        results = load_results(tmp_path)
        assert results == []
        assert "skipping malformed" in capsys.readouterr().err

    def test_empty_dir_yields_no_results(self, tmp_path: Path):
        assert load_results(tmp_path) == []


class TestRenderSummary:
    def test_empty_state_message(self):
        text = render_summary([])
        assert "No issues were triaged" in text
        assert "Backlog Triage Summary" in text

    def test_renders_table_row(self):
        text = render_summary(
            [_result(number=42, title="Add it", verdict="PASS", labels=("area-x",))]
        )
        assert "Issues triaged: 1" in text
        assert "| #42 | Add it | PASS | area-x |" in text

    def test_missing_labels_renders_dash(self):
        text = render_summary([_result(number=1, title="t", verdict="WARN")])
        assert "| #1 | t | WARN | - |" in text

    def test_pipe_in_title_is_escaped(self):
        text = render_summary([_result(number=1, title="a | b")])
        assert "a \\| b" in text

    def test_newline_in_title_is_collapsed(self):
        text = render_summary([_result(number=1, title="line1\nline2")])
        assert "line1 line2" in text
        assert "line1\nline2" not in text


class TestMain:
    def test_writes_summary_from_results(self, tmp_path: Path, capsys):
        results_dir = tmp_path / "results"
        results_dir.mkdir()
        _write_result(results_dir, "r.json", {"number": 1, "title": "t", "verdict": "PASS"})
        out = tmp_path / "summary.md"
        rc = main(["--results-dir", str(results_dir), "--output", str(out)])
        assert rc == 0
        body = out.read_text()
        assert "| #1 | t | PASS |" in body
        assert "summary" in capsys.readouterr().out

    def test_missing_dir_writes_empty_state(self, tmp_path: Path):
        out = tmp_path / "summary.md"
        rc = main(["--results-dir", str(tmp_path / "absent"), "--output", str(out)])
        assert rc == 0
        assert "No issues were triaged" in out.read_text()
