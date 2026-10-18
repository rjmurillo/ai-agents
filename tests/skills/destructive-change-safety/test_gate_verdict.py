"""Fail-closed verdicts over destructive-change evidence."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import gate_verdict
import pytest


def good_evidence() -> dict[str, Any]:
    return {
        "sinks": [{"location": "store.py:10", "trace": ["main", "purge"]}],
        "preflight": {"command": "preview-sql ...", "exit_code": 0, "measured": 3},
        "expected": 3,
        "rollback": {"kind": "snapshot", "ref": "snap-2026-10-11"},
        "checks": [{"command": "pytest -q", "exit_code": 0}],
    }


# A scan that found no sink beyond the ones the evidence declares. Most tests probe one
# evidence rule and need a scan report to reach it, because every verdict requires one.
ACTIVE_SCAN: dict[str, Any] = {"decision": "activate", "sinks": []}
NO_SCAN = object()


def verdict(evidence: dict[str, Any], scan: Any = ACTIVE_SCAN) -> dict[str, Any]:
    return gate_verdict.evaluate(evidence, None if scan is NO_SCAN else scan)


def reasons(evidence: dict[str, Any], scan: Any = ACTIVE_SCAN) -> str:
    return " | ".join(verdict(evidence, scan)["reasons"])


def test_complete_evidence_passes() -> None:
    assert verdict(good_evidence()) == {"verdict": "PASS", "reasons": []}


def test_read_only_change_skips() -> None:
    assert verdict({}, {"decision": "skip", "sinks": []})["verdict"] == "SKIP"


def test_missing_scan_report_cannot_skip() -> None:
    """Issue #6506: no sinks declared and no scan is an unproven claim, not a skip."""
    result = verdict({}, NO_SCAN)
    assert result["verdict"] == "BLOCK"
    assert "no scan report" in result["reasons"][0]


@pytest.mark.parametrize(
    "scan",
    [
        {},
        {"sinks": []},
        {"decision": None},
        {"decision": ""},
        {"decision": "SKIP"},
        {"decision": 0},
    ],
)
def test_scan_report_without_a_known_decision_blocks(scan: dict[str, Any]) -> None:
    result = verdict({}, scan)
    assert result["verdict"] == "BLOCK"
    assert "no known `decision`" in result["reasons"][0]


def test_scan_report_without_a_decision_blocks_even_with_complete_evidence() -> None:
    assert verdict(good_evidence(), {"sinks": []})["verdict"] == "BLOCK"


def test_declared_sinks_with_no_scan_report_block() -> None:
    """Issue #6506 review: an agent could declare one sink and omit the rest the scan finds."""
    result = verdict(good_evidence(), NO_SCAN)
    assert result["verdict"] == "BLOCK"
    assert "no scan report" in result["reasons"][0]


def test_complete_evidence_with_a_matching_scan_passes() -> None:
    scan = {"decision": "activate", "sinks": [{"location": "store.py:10"}]}
    assert verdict(good_evidence(), scan) == {"verdict": "PASS", "reasons": []}


@pytest.mark.parametrize("sinks", [[], None])
def test_activate_scan_with_no_sinks_cannot_back_a_skip(sinks: object) -> None:
    """An `activate` report that lists no sink is inconsistent, so it never skips."""
    scan: dict[str, Any] = {"decision": "activate"}
    if sinks is not None:
        scan["sinks"] = sinks
    result = verdict({}, scan)
    assert result["verdict"] == "BLOCK"
    assert "lists no sink" in result["reasons"][0]


def test_skip_scan_with_declared_sinks_still_evaluates_the_rules() -> None:
    assert verdict(good_evidence(), {"decision": "skip", "sinks": []})["verdict"] == "PASS"


@pytest.mark.parametrize("exit_code", [False, True, None, "0", 0.0, 1, -1])
def test_preflight_exit_code_must_be_the_integer_zero(exit_code: object) -> None:
    evidence = good_evidence()
    evidence["preflight"]["exit_code"] = exit_code
    result = verdict(evidence)
    assert result["verdict"] == "BLOCK"
    assert "preflight did not exit 0" in reasons(evidence)


@pytest.mark.parametrize("exit_code", [False, True, None, "0", 0.0, 2])
def test_check_exit_code_must_be_the_integer_zero(exit_code: object) -> None:
    evidence = good_evidence()
    evidence["checks"] = [{"command": "pytest -q", "exit_code": exit_code}]
    result = verdict(evidence)
    assert result["verdict"] == "BLOCK"
    assert "check failed: pytest -q" in reasons(evidence)


def test_negative_measured_count_blocks() -> None:
    evidence = good_evidence()
    evidence["preflight"]["measured"] = -1
    evidence["expected"] = {"max": 10}
    result = verdict(evidence)
    assert result["verdict"] == "BLOCK"
    assert "preflight measured no count" in reasons(evidence)


def test_zero_measured_count_within_max_passes() -> None:
    evidence = good_evidence()
    evidence["preflight"]["measured"] = 0
    evidence["expected"] = {"max": 10}
    assert verdict(evidence)["verdict"] == "PASS"


def test_scan_sinks_the_evidence_omits_block() -> None:
    scan = {"decision": "activate", "sinks": [{"location": "other.py:4"}]}
    result = verdict(good_evidence(), scan)
    assert result["verdict"] == "BLOCK"
    assert "scanned sink other.py:4 is missing" in reasons(good_evidence(), scan)


def test_empty_evidence_cannot_skip_past_a_scanned_sink() -> None:
    scan = {"decision": "activate", "sinks": [{"location": "other.py:4"}]}
    assert verdict({}, scan)["verdict"] == "BLOCK"


def test_scan_of_matching_sinks_passes() -> None:
    scan = {"decision": "activate", "sinks": [{"location": "store.py:10"}]}
    assert verdict(good_evidence(), scan)["verdict"] == "PASS"


def test_unparsed_or_unscanned_scan_blocks() -> None:
    result = verdict(good_evidence(), {"decision": "unknown", "sinks": []})
    assert result["verdict"] == "BLOCK"
    assert "could not parse" in result["reasons"][0]


def test_sink_without_trace_blocks() -> None:
    evidence = good_evidence()
    evidence["sinks"][0]["trace"] = []
    assert "no traced path" in reasons(evidence)


def test_missing_preflight_is_unknown_scope() -> None:
    evidence = good_evidence()
    del evidence["preflight"]
    assert "scope is unknown" in reasons(evidence)


@pytest.mark.parametrize(
    "preflight",
    [
        {"exit_code": 1, "measured": 3},
        {"exit_code": 0},
        {"exit_code": 0, "measured": None},
        {"exit_code": 0, "measured": True},
        {"exit_code": 0, "measured": "3"},
    ],
)
def test_preflight_that_failed_or_measured_nothing_blocks(preflight: dict[str, Any]) -> None:
    evidence = good_evidence()
    evidence["preflight"] = preflight
    assert verdict(evidence)["verdict"] == "BLOCK"


def test_unexpected_exact_cardinality_blocks() -> None:
    evidence = good_evidence()
    evidence["preflight"]["measured"] = 4000
    assert "measured 4000, expected 3" in reasons(evidence)


def test_max_bound_allows_under_and_blocks_over() -> None:
    evidence = good_evidence()
    evidence["expected"] = {"max": 5}
    assert verdict(evidence)["verdict"] == "PASS"
    evidence["preflight"]["measured"] = 6
    assert "max 5" in reasons(evidence)


@pytest.mark.parametrize("expected", [None, "3", {}, {"max": "5"}])
def test_missing_or_malformed_expectation_blocks(expected: object) -> None:
    evidence = good_evidence()
    evidence["expected"] = expected
    assert "cardinality cannot be checked" in reasons(evidence)


@pytest.mark.parametrize("rollback", [None, {}, {"kind": "hope"}, {"kind": "none"}])
def test_missing_rollback_contract_blocks(rollback: object) -> None:
    evidence = good_evidence()
    evidence["rollback"] = rollback
    assert "no rollback contract" in reasons(evidence)


def test_referenced_rollback_kinds_need_a_ref() -> None:
    evidence = good_evidence()
    evidence["rollback"] = {"kind": "backup"}
    assert "names no ref" in reasons(evidence)


def test_irreversible_without_approval_blocks_and_never_invents_a_rollback() -> None:
    evidence = good_evidence()
    evidence["rollback"] = {"kind": "irreversible"}
    assert "needs human approval" in reasons(evidence)


def test_irreversible_with_human_approval_passes() -> None:
    evidence = good_evidence()
    evidence["rollback"] = {"kind": "irreversible"}
    evidence["approval"] = {"human": "owner sign-off in PR 1"}
    assert verdict(evidence)["verdict"] == "PASS"


def backup_evidence(tmp_path: Path, backup_text: str) -> dict[str, Any]:
    source = tmp_path / "state.json"
    backup = tmp_path / "state.json.bak"
    source.write_text("canonical", encoding="utf-8")
    backup.write_text(backup_text, encoding="utf-8")
    evidence = good_evidence()
    evidence["rollback"] = {
        "kind": "backup",
        "ref": "state.json.bak",
        "backup_path": str(backup),
        "source_path": str(source),
    }
    return evidence


def test_overwrite_with_matching_backup_passes(tmp_path: Path) -> None:
    assert verdict(backup_evidence(tmp_path, "canonical"))["verdict"] == "PASS"


def test_backup_that_differs_from_the_source_blocks(tmp_path: Path) -> None:
    assert "does not match" in reasons(backup_evidence(tmp_path, "stale"))


def test_missing_backup_file_blocks(tmp_path: Path) -> None:
    evidence = backup_evidence(tmp_path, "canonical")
    Path(evidence["rollback"]["backup_path"]).unlink()
    assert "does not exist" in reasons(evidence)


def test_no_checks_or_failed_checks_block() -> None:
    evidence = good_evidence()
    evidence["checks"] = []
    assert "no verification checks" in reasons(evidence)
    evidence["checks"] = [{"command": "pytest -q", "exit_code": 1}]
    assert "check failed: pytest -q" in reasons(evidence)


def test_non_dict_sections_are_treated_as_missing() -> None:
    evidence = good_evidence()
    evidence["sinks"] = "store.py:10"
    assert "`sinks` must be a list" in reasons(evidence)
    evidence["sinks"] = [["not", "a", "dict"]]
    evidence["preflight"] = ["x"]
    assert verdict(evidence)["verdict"] == "BLOCK"


def test_mutation_control_cardinality_check_is_load_bearing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evidence = good_evidence()
    evidence["preflight"]["measured"] = 4000
    assert verdict(evidence)["verdict"] == "BLOCK"
    monkeypatch.setattr(
        gate_verdict,
        "RULES",
        tuple(r for r in gate_verdict.RULES if r is not gate_verdict.rule_cardinality),
    )
    assert verdict(copy.deepcopy(evidence))["verdict"] == "PASS"


def test_mutation_control_path_trace_check_is_load_bearing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evidence = good_evidence()
    evidence["sinks"][0]["trace"] = []
    assert verdict(evidence)["verdict"] == "BLOCK"
    monkeypatch.setattr(
        gate_verdict,
        "RULES",
        tuple(r for r in gate_verdict.RULES if r is not gate_verdict.rule_sinks_traced),
    )
    assert verdict(copy.deepcopy(evidence))["verdict"] == "PASS"
