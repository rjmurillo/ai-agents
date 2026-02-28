"""Tests for validate_quality_gate_output.py schema validation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.validate_quality_gate_output import validate_output


def _valid_output(**overrides: object) -> dict:
    """Return a minimal valid quality gate output dict."""
    base = {
        "verdict": "PASS",
        "message": "No issues found",
        "agent": "security",
        "timestamp": "2026-02-21T19:00:00Z",
        "findings": [],
    }
    base.update(overrides)
    return base


class TestValidOutput:
    def test_minimal_valid(self) -> None:
        errors = validate_output(_valid_output())
        assert errors == []

    def test_valid_with_findings(self) -> None:
        findings = [
            {
                "severity": "high",
                "category": "injection",
                "description": "Unsanitized input in shell command",
                "location": "scripts/deploy.py:42",
                "cwe": "CWE-78",
                "recommendation": "Use shlex.quote()",
            }
        ]
        errors = validate_output(_valid_output(findings=findings))
        assert errors == []

    def test_all_agents_accepted(self) -> None:
        for agent in ("security", "qa", "analyst", "architect", "devops", "roadmap"):
            errors = validate_output(_valid_output(agent=agent))
            assert errors == [], f"Agent '{agent}' rejected"

    def test_all_verdicts_accepted(self) -> None:
        for verdict in ("PASS", "WARN", "CRITICAL_FAIL"):
            errors = validate_output(_valid_output(verdict=verdict))
            assert errors == [], f"Verdict '{verdict}' rejected"


class TestInvalidOutput:
    def test_missing_required_fields(self) -> None:
        errors = validate_output({})
        assert len(errors) == 1
        assert "Missing required fields" in errors[0]

    def test_invalid_verdict(self) -> None:
        errors = validate_output(_valid_output(verdict="REJECT"))
        assert any("Invalid verdict" in e for e in errors)

    def test_invalid_agent(self) -> None:
        errors = validate_output(_valid_output(agent="unknown"))
        assert any("Invalid agent" in e for e in errors)

    def test_empty_message(self) -> None:
        errors = validate_output(_valid_output(message=""))
        assert any("'message' must be a non-empty string" in e for e in errors)

    def test_findings_not_array(self) -> None:
        errors = validate_output(_valid_output(findings="not an array"))
        assert any("'findings' must be an array" in e for e in errors)

    def test_finding_missing_fields(self) -> None:
        errors = validate_output(_valid_output(findings=[{}]))
        assert any("missing required fields" in e for e in errors)

    def test_finding_invalid_severity(self) -> None:
        finding = {
            "severity": "extreme",
            "category": "test",
            "description": "something",
        }
        errors = validate_output(_valid_output(findings=[finding]))
        assert any("invalid severity" in e for e in errors)

    def test_finding_invalid_cwe(self) -> None:
        finding = {
            "severity": "high",
            "category": "test",
            "description": "something",
            "cwe": "CVE-2024-1234",
        }
        errors = validate_output(_valid_output(findings=[finding]))
        assert any("cwe" in e.lower() for e in errors)

    def test_finding_cwe_missing_digits(self) -> None:
        finding = {
            "severity": "high",
            "category": "test",
            "description": "something",
            "cwe": "CWE-",
        }
        errors = validate_output(_valid_output(findings=[finding]))
        assert any("cwe" in e.lower() for e in errors)

    def test_finding_cwe_non_numeric_suffix(self) -> None:
        finding = {
            "severity": "high",
            "category": "test",
            "description": "something",
            "cwe": "CWE-XXX",
        }
        errors = validate_output(_valid_output(findings=[finding]))
        assert any("cwe" in e.lower() for e in errors)

    def test_not_a_dict(self) -> None:
        errors = validate_output("not a dict")  # type: ignore[arg-type]
        assert errors == ["Root element must be a JSON object"]


class TestSchemaFile:
    def test_schema_is_valid_json(self) -> None:
        schema_path = (
            Path(__file__).resolve().parent.parent
            / ".agents"
            / "schemas"
            / "pr-quality-gate-output.schema.json"
        )
        assert schema_path.exists(), f"Schema file missing: {schema_path}"
        data = json.loads(schema_path.read_text(encoding="utf-8"))
        assert data["title"] == "PR Quality Gate Output"
        assert "verdict" in data["properties"]
        assert "findings" in data["properties"]
