"""Tests for scripts.backlog_triage_result.

Covers the Phase 2 per-issue result recorder (issue #1799): label parsing,
result building, env validation, findings truncation, and the CLI entry point.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.backlog_triage_result import (
    MAX_FINDINGS_CHARS,
    build_result,
    main,
    parse_labels,
)


class TestParseLabels:
    def test_parses_json_array(self):
        assert parse_labels('["area-x", "agent-implementer"]') == [
            "area-x",
            "agent-implementer",
        ]

    def test_empty_string_yields_empty_list(self):
        assert parse_labels("") == []

    def test_malformed_json_yields_empty_list(self):
        assert parse_labels("{not json") == []

    def test_non_array_json_yields_empty_list(self):
        assert parse_labels('{"a": 1}') == []

    def test_coerces_items_to_str(self):
        assert parse_labels("[1, 2]") == ["1", "2"]


class TestBuildResult:
    def test_builds_full_result(self):
        result = build_result(
            {
                "ISSUE_NUMBER": "42",
                "ISSUE_TITLE": "Add backlog triage",
                "AI_VERDICT": "PASS",
                "AI_LABELS": '["area-workflows"]',
                "AI_FINDINGS": "complexity: medium",
            }
        )
        assert result == {
            "number": 42,
            "title": "Add backlog triage",
            "verdict": "PASS",
            "labels": ["area-workflows"],
            "findings": "complexity: medium",
        }

    def test_defaults_missing_optional_fields(self):
        result = build_result({"ISSUE_NUMBER": "7"})
        assert result["title"] == ""
        assert result["verdict"] == "UNKNOWN"
        assert result["labels"] == []
        assert result["findings"] == ""

    def test_blank_verdict_defaults_unknown(self):
        result = build_result({"ISSUE_NUMBER": "7", "AI_VERDICT": "   "})
        assert result["verdict"] == "UNKNOWN"

    def test_rejects_missing_number(self):
        with pytest.raises(ValueError, match="required"):
            build_result({})

    def test_rejects_blank_number(self):
        with pytest.raises(ValueError, match="required"):
            build_result({"ISSUE_NUMBER": "   "})

    def test_rejects_non_integer_number(self):
        with pytest.raises(ValueError, match="must be an integer"):
            build_result({"ISSUE_NUMBER": "abc"})

    def test_rejects_non_positive_number(self):
        with pytest.raises(ValueError, match="must be positive"):
            build_result({"ISSUE_NUMBER": "0"})

    def test_truncates_long_findings(self):
        long_text = "x" * (MAX_FINDINGS_CHARS + 100)
        result = build_result({"ISSUE_NUMBER": "1", "AI_FINDINGS": long_text})
        assert result["findings"].endswith("... (truncated)")
        assert len(result["findings"]) == MAX_FINDINGS_CHARS + len("... (truncated)")


class TestMain:
    def test_writes_result_file(self, tmp_path: Path, monkeypatch, capsys):
        monkeypatch.setenv("ISSUE_NUMBER", "99")
        monkeypatch.setenv("ISSUE_TITLE", "t")
        monkeypatch.setenv("AI_VERDICT", "WARN")
        out = tmp_path / "result.json"
        rc = main(["--output", str(out)])
        assert rc == 0
        payload = json.loads(out.read_text())
        assert payload["number"] == 99
        assert payload["verdict"] == "WARN"
        assert "issue #99" in capsys.readouterr().out

    def test_missing_number_returns_config_error(self, tmp_path: Path, monkeypatch, capsys):
        monkeypatch.delenv("ISSUE_NUMBER", raising=False)
        rc = main(["--output", str(tmp_path / "r.json")])
        assert rc == 2
        assert "required" in capsys.readouterr().err
