"""Tests for scripts.backlog_triage_result.

Covers the Phase 2 per-issue result recorder (issue #2260): label parsing,
structured result fields, env validation, findings truncation, and the CLI
entry point.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.backlog_triage_result import (
    MAX_FINDINGS_CHARS,
    TRUNCATION_SUFFIX,
    build_result,
    main,
    parse_labels,
    parse_structured_findings,
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


class TestParseStructuredFindings:
    def test_extracts_all_phase_two_fields_from_json(self):
        findings = json.dumps(
            {
                "complexity_classification": "senior",
                "area_routing": ["agent-architect", "agent-security"],
                "dependency_detection": {
                    "blocked_by": [2259, "2260", 0, "bad"],
                    "blocks": [2261],
                    "related": [1799],
                    "notes": "Needs Phase 1 state.",
                },
                "scope_assessment": {
                    "status": "too_broad",
                    "needs_decomposition": True,
                    "can_batch": False,
                    "notes": "Split by capability.",
                },
                "evidence_check": {
                    "has_repro_steps": False,
                    "has_acceptance_criteria": True,
                    "has_enough_context": True,
                    "missing": ["repro steps"],
                },
            }
        )

        result = parse_structured_findings(findings, ["agent-implementer"])

        assert result == {
            "complexity_classification": "senior",
            "area_routing": ["agent-architect", "agent-security"],
            "dependency_detection": {
                "blocked_by": [2259, 2260],
                "blocks": [2261],
                "related": [1799],
                "notes": "Needs Phase 1 state.",
            },
            "scope_assessment": {
                "status": "too_broad",
                "needs_decomposition": True,
                "can_batch": False,
                "notes": "Split by capability.",
            },
            "evidence_check": {
                "has_repro_steps": False,
                "has_acceptance_criteria": True,
                "has_enough_context": True,
                "missing": ["repro steps"],
            },
        }

    def test_parses_json_when_wrapped_by_verdict_text(self):
        findings = 'VERDICT: PASS\n{"complexity":"junior"}\nLABEL: agent-qa'
        result = parse_structured_findings(findings, ["agent-qa"])
        assert result["complexity_classification"] == "junior"
        assert result["area_routing"] == ["agent-qa"]

    def test_malformed_json_defaults_to_typed_unknowns(self):
        result = parse_structured_findings("not json", ["agent-qa", "area-workflows"])
        assert result["complexity_classification"] == "unknown"
        assert result["area_routing"] == ["agent-qa"]
        assert result["dependency_detection"] == {
            "blocked_by": [],
            "blocks": [],
            "related": [],
            "notes": "",
        }
        assert result["scope_assessment"] == {
            "status": "unknown",
            "needs_decomposition": False,
            "can_batch": False,
            "notes": "",
        }
        assert result["evidence_check"] == {
            "has_repro_steps": None,
            "has_acceptance_criteria": None,
            "has_enough_context": None,
            "missing": [],
        }


class TestBuildResult:
    def test_builds_full_result(self):
        result = build_result(
            {
                "ISSUE_NUMBER": "42",
                "ISSUE_TITLE": "Add backlog triage",
                "AI_VERDICT": "PASS",
                "AI_LABELS": '["area-workflows", "agent-implementer"]',
                "AI_FINDINGS": json.dumps(
                    {
                        "complexity_classification": "medior",
                        "area_routing": ["agent-implementer"],
                        "dependency_detection": {"blocked_by": [2259]},
                        "scope_assessment": {"status": "right_sized"},
                        "evidence_check": {"has_enough_context": True},
                    }
                ),
            }
        )
        assert result["number"] == 42
        assert result["title"] == "Add backlog triage"
        assert result["verdict"] == "PASS"
        assert result["labels"] == ["area-workflows", "agent-implementer"]
        assert result["complexity_classification"] == "medior"
        assert result["area_routing"] == ["agent-implementer"]
        assert result["dependency_detection"]["blocked_by"] == [2259]
        assert result["scope_assessment"]["status"] == "right_sized"
        assert result["evidence_check"]["has_enough_context"] is True

    def test_defaults_missing_optional_fields(self):
        result = build_result({"ISSUE_NUMBER": "7"})
        assert result["title"] == ""
        assert result["verdict"] == "UNKNOWN"
        assert result["labels"] == []
        assert result["findings"] == ""
        assert result["complexity_classification"] == "unknown"
        assert result["area_routing"] == []

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

    def test_truncates_long_findings_to_max_length(self):
        long_text = "x" * (MAX_FINDINGS_CHARS + 100)
        result = build_result({"ISSUE_NUMBER": "1", "AI_FINDINGS": long_text})
        assert result["findings"].endswith(TRUNCATION_SUFFIX)
        assert len(result["findings"]) == MAX_FINDINGS_CHARS


class TestMain:
    def test_writes_result_file(self, tmp_path: Path, monkeypatch, capsys):
        monkeypatch.setenv("ISSUE_NUMBER", "99")
        monkeypatch.setenv("ISSUE_TITLE", "t")
        monkeypatch.setenv("AI_VERDICT", "WARN")
        monkeypatch.setenv("AI_FINDINGS", '{"complexity_classification":"junior"}')
        out = tmp_path / "result.json"
        rc = main(["--output", str(out)])
        assert rc == 0
        payload = json.loads(out.read_text())
        assert payload["number"] == 99
        assert payload["verdict"] == "WARN"
        assert payload["complexity_classification"] == "junior"
        assert "issue #99" in capsys.readouterr().out

    def test_missing_number_returns_config_error(self, tmp_path: Path, monkeypatch, capsys):
        monkeypatch.delenv("ISSUE_NUMBER", raising=False)
        rc = main(["--output", str(tmp_path / "r.json")])
        assert rc == 2
        assert "required" in capsys.readouterr().err
