"""Structural contract for the build gate failure disposition (issue #6992).

The build template must resolve the conflict between fixing unrelated drift
and recording out-of-scope findings by consuming the work-order contract and
the finding-disposition contract, and it must never let prose turn a failed
gate into a pass.
"""

from __future__ import annotations

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
TEMPLATE = PROJECT_ROOT / "templates" / "skills" / "build.SKILL.md.tmpl"
SCENARIOS = PROJECT_ROOT / "tests" / "evals" / "skill-scenarios" / "build.json"


def _section() -> str:
    text = TEMPLATE.read_text(encoding="utf-8")
    start = text.index("### Gate failure disposition")
    return text[start : text.index("## Verification", start)]


def test_no_unconditional_fix_unrelated_drift_directive() -> None:
    text = TEMPLATE.read_text(encoding="utf-8")
    assert "fix it in the same PR" not in text
    assert "it can fail on drift this build did not cause" in text


def test_positive_in_scope_regression_is_repaired_and_rerun() -> None:
    section = _section()
    assert "In scope. Repair it this cycle, rerun the gate." in section


def test_out_of_scope_makes_no_edit_and_names_owner() -> None:
    section = _section()
    assert "No edit to those files." in section
    assert "Stop this branch, report the gate FAILED, name the owner" in section
    assert "ESCALATE TO" in section


def test_failed_gate_never_becomes_pass_and_no_bypass() -> None:
    section = _section()
    assert "never turns it into PASS" in section
    assert "skip hooks" in section
    assert "Never weaken the gate" in section


def test_authorized_repair_is_separately_bounded() -> None:
    assert "Separate bounded repair" in _section()


def test_changed_evidence_requires_freshness_check() -> None:
    section = _section()
    assert "freshness check" in section
    assert "head SHA" in section
    assert "discard the record" in section


def test_handoff_uses_existing_fields_only() -> None:
    section = _section()
    assert "existing handoff fields only" in section
    for field in ("CONTEXT", "ESCALATE TO", "STOP CONDITIONS"):
        assert field in section


def test_scenarios_cover_positive_out_of_scope_and_changed_evidence() -> None:
    scenarios = {s["id"]: s for s in json.loads(SCENARIOS.read_text())["scenarios"]}
    assert {"S8", "S9", "S10"} <= scenarios.keys()
    assert "in scope" in scenarios["S8"]["expected_signals"]
    assert "FAILED" in scenarios["S9"]["expected_signals"]
    assert "freshness" in scenarios["S10"]["expected_signals"]
