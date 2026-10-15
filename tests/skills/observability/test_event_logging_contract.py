#!/usr/bin/env python3
"""Tests for the operational event-logging contract checker.

Covers the nine reference scenarios from issue #5413 (a compliant case and a
violating case each), a mutation control, per-function positive, negative, and
edge cases, CLI exit codes, and conformance of the checker to the contract
document it encodes.
"""

from __future__ import annotations

import importlib.util
import io
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SKILL_DIR = ROOT / ".claude" / "skills" / "observability"
SCRIPT_PATH = SKILL_DIR / "scripts" / "check_event_logging.py"
CONTRACT_PATH = SKILL_DIR / "references" / "event-logging-contract.md"


def _load_module():
    spec = importlib.util.spec_from_file_location("check_event_logging", SCRIPT_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


mod = _load_module()
classify_scenario = mod.classify_scenario
required_categories = mod.required_categories
missing_required = mod.missing_required
prohibited_findings = mod.prohibited_findings
main = mod.main

# 1. Stateful background job: start, end, count, duration, result.
JOB_OK = {
    "behavior": {"job_lifecycle": True},
    "emits": [
        {"event": "job_start", "fields": {"id": "j1"}},
        {
            "event": "job_completion",
            "fields": {"count": 42, "duration": 3.1, "result": "ok"},
        },
    ],
}
JOB_MISSING_END = {
    "behavior": {"job_lifecycle": True},
    "emits": [{"event": "job_start", "fields": {"id": "j1"}}],
}

# 2. External call succeeds: one outcome event, no per-layer duplication.
CALL_OK = {
    "behavior": {"external_call": True},
    "emits": [
        {"event": "external_call_outcome", "fields": {"operation": "GET /x", "status": 200}},
    ],
}
CALL_DUPLICATED = {
    "behavior": {"external_call": True},
    "emits": [
        {"event": "external_call_outcome", "fields": {"operation": "GET /x", "status": 200}},
        {"event": "external_call_outcome", "fields": {"operation": "GET /x", "status": 200}},
    ],
}

# 3. Retry path: failed attempts plus final exhaustion explain the outcome.
RETRY_OK = {
    "behavior": {"retry": True},
    "emits": [
        {"event": "retry_attempt", "fields": {"attempt": 1}},
        {"event": "retry_attempt", "fields": {"attempt": 2}},
        {"event": "retry_exhaustion", "fields": {"attempt": 3}},
    ],
}
RETRY_NO_EXHAUSTION = {
    "behavior": {"retry": True},
    "emits": [{"event": "retry_attempt", "fields": {"attempt": 1}}],
}

# 4. Skip path: the predicate's reason is observable.
SKIP_OK = {
    "behavior": {"skip_changes_behavior": True},
    "emits": [{"event": "skip", "fields": {"reason": "manifest missing"}}],
}
SKIP_NO_REASON = {
    "behavior": {"skip_changes_behavior": True},
    "emits": [{"event": "skip", "fields": {}}],
}

# 5. Error path: not swallowed, operation context, no secret.
ERROR_OK = {
    "behavior": {"error_not_swallowed": True},
    "emits": [{"event": "error", "fields": {"operation": "sync_manifest"}}],
}
ERROR_SWALLOWED = {"behavior": {"error_not_swallowed": True}, "emits": []}

# 6. Secret-bearing auth request: token and body are not logged.
AUTH_REDACTED = {
    "behavior": {"external_call": True},
    "emits": [
        {"event": "external_call_outcome", "fields": {"operation": "POST /token", "status": 200}},
    ],
}
AUTH_LEAKS_SECRET = {
    "behavior": {"external_call": True},
    "emits": [
        {
            "event": "external_call_outcome",
            "fields": {"operation": "POST /token", "status": 200},
            "contains_secret": True,
        },
    ],
}
AUTH_LOGS_BODY = {
    "behavior": {"external_call": True},
    "emits": [
        {
            "event": "external_call_outcome",
            "fields": {"operation": "POST /token", "status": 200},
            "full_body": True,
        },
    ],
}

# 7. Pure in-memory helper: no operational event required.
PURE_HELPER: dict = {"behavior": {}, "emits": []}
PURE_HELPER_OVERLOGS = {
    "behavior": {},
    "emits": [{"event": "trace", "per_function_entry_exit": True}],
}

# 8. Lower-layer telemetry already captures the signal: do not duplicate it.
DOWNSTREAM_SILENT: dict = {"behavior": {}, "emits": []}
DOWNSTREAM_DUPLICATED = {
    "behavior": {},
    "emits": [{"event": "state_transition", "duplicate_of_lower_layer": True}],
}

# 9. High-cardinality field with no diagnostic value: reject it.
CARDINALITY_OK = {
    "behavior": {"state_transition": True},
    "emits": [{"event": "state_transition", "fields": {"from": "a", "to": "b"}}],
}
CARDINALITY_REJECTED = {
    "behavior": {"state_transition": True},
    "emits": [
        {
            "event": "state_transition",
            "fields": {"from": "a", "to": "b"},
            "high_cardinality_no_value": True,
        },
    ],
}

COMPLIANT = [
    JOB_OK, CALL_OK, RETRY_OK, SKIP_OK, ERROR_OK, AUTH_REDACTED,
    PURE_HELPER, DOWNSTREAM_SILENT, CARDINALITY_OK,
]  # fmt: skip


class TestNineScenarios:
    """Each issue #5413 scenario: compliant passes, violating variant is caught."""

    @pytest.mark.parametrize("scenario", COMPLIANT)
    def test_compliant_scenarios_pass(self, scenario: dict) -> None:
        result = classify_scenario(scenario)
        assert result["compliant"], result["findings"]
        assert result["findings"] == []

    @pytest.mark.parametrize(
        ("scenario", "expected"),
        [
            (JOB_MISSING_END, "missing_required_event:job_completion"),
            (CALL_DUPLICATED, "duplicate_event:external_call_outcome"),
            (RETRY_NO_EXHAUSTION, "missing_required_event:retry_exhaustion"),
            (SKIP_NO_REASON, "missing_field:skip.reason"),
            (ERROR_SWALLOWED, "missing_required_event:error"),
            (AUTH_LEAKS_SECRET, "secret_in_telemetry:external_call_outcome"),
            (AUTH_LOGS_BODY, "full_body:external_call_outcome"),
            (PURE_HELPER_OVERLOGS, "function_entry_exit:trace"),
            (DOWNSTREAM_DUPLICATED, "duplicate_event:state_transition"),
            (CARDINALITY_REJECTED, "high_cardinality:state_transition"),
        ],
    )
    def test_violating_scenarios_are_detected(self, scenario: dict, expected: str) -> None:
        result = classify_scenario(scenario)
        assert not result["compliant"]
        assert expected in result["findings"]

    def test_multiple_retry_attempts_are_not_duplicates(self) -> None:
        assert "duplicate_event:retry_attempt" not in classify_scenario(RETRY_OK)["findings"]


class TestMutationControl:
    """Dropping a load-bearing event is caught. Harmless absence stays valid."""

    @pytest.mark.parametrize("scenario", [s for s in COMPLIANT if s["emits"]])
    def test_removing_any_event_category_is_detected(self, scenario: dict) -> None:
        for category in {event["event"] for event in scenario["emits"]}:
            mutant = {
                "behavior": scenario["behavior"],
                "emits": [e for e in scenario["emits"] if e["event"] != category],
            }
            assert not classify_scenario(mutant)["compliant"], (scenario, category)

    @pytest.mark.parametrize("scenario", [s for s in COMPLIANT if not s["behavior"]])
    def test_absent_logging_without_a_trigger_stays_valid(self, scenario: dict) -> None:
        assert classify_scenario({**scenario, "emits": []})["compliant"]


class TestRequiredCategories:
    def test_pos_single_trigger(self) -> None:
        assert required_categories({"skip_changes_behavior": True}) == ["skip"]

    def test_pos_job_expands_to_two(self) -> None:
        assert required_categories({"job_lifecycle": True}) == ["job_start", "job_completion"]

    def test_neg_no_triggers_requires_nothing(self) -> None:
        assert required_categories({}) == []

    def test_edge_false_flag_ignored(self) -> None:
        assert required_categories({"retry": False}) == []


class TestMissingRequired:
    def test_pos_all_present(self) -> None:
        assert missing_required(JOB_OK["behavior"], JOB_OK["emits"]) == []

    def test_neg_event_absent(self) -> None:
        findings = missing_required(ERROR_SWALLOWED["behavior"], ERROR_SWALLOWED["emits"])
        assert findings == ["missing_required_event:error"]

    def test_edge_present_but_missing_field(self) -> None:
        findings = missing_required(SKIP_NO_REASON["behavior"], SKIP_NO_REASON["emits"])
        assert findings == ["missing_field:skip.reason"]

    def test_edge_event_without_fields_key(self) -> None:
        findings = missing_required({"skip_changes_behavior": True}, [{"event": "skip"}])
        assert findings == ["missing_field:skip.reason"]

    def test_edge_every_attempt_needs_its_field(self) -> None:
        emits = [
            {"event": "retry_attempt", "fields": {"attempt": 1}},
            {"event": "retry_attempt", "fields": {}},
            {"event": "retry_exhaustion"},
        ]
        assert missing_required({"retry": True}, emits) == ["missing_field:retry_attempt.attempt"]


class TestProhibitedFindings:
    def test_pos_clean_emits(self) -> None:
        assert prohibited_findings(CALL_OK["emits"]) == []

    def test_neg_secret_flagged(self) -> None:
        assert prohibited_findings(AUTH_LEAKS_SECRET["emits"]) == [
            "secret_in_telemetry:external_call_outcome"
        ]

    def test_edge_empty_emits(self) -> None:
        assert prohibited_findings([]) == []

    def test_edge_same_event_with_different_fields_is_not_a_duplicate(self) -> None:
        emits = [
            {"event": "state_transition", "fields": {"from": "a", "to": "b"}},
            {"event": "state_transition", "fields": {"from": "b", "to": "c"}},
        ]
        assert prohibited_findings(emits) == []

    def test_edge_flag_and_identical_pair_report_one_duplicate(self) -> None:
        event = {"event": "x", "fields": {}, "duplicate_of_lower_layer": True}
        assert prohibited_findings([event, dict(event)]) == ["duplicate_event:x"]


class TestClassifyScenarioEdges:
    def test_empty_scenario_is_compliant(self) -> None:
        assert classify_scenario({})["compliant"] is True

    def test_bad_behavior_type_raises(self) -> None:
        with pytest.raises(ValueError, match="behavior"):
            classify_scenario({"behavior": [], "emits": []})

    def test_bad_emits_type_raises(self) -> None:
        with pytest.raises(ValueError, match="emits"):
            classify_scenario({"behavior": {}, "emits": {}})

    def test_non_object_event_raises(self) -> None:
        with pytest.raises(ValueError, match="object"):
            classify_scenario({"behavior": {}, "emits": ["skip"]})


class TestCli:
    def _run(self, args: list[str], stdin: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT_PATH), *args],
            input=stdin,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_exit_0_compliant_via_stdin(self) -> None:
        proc = self._run([], json.dumps(JOB_OK))
        assert proc.returncode == 0
        assert json.loads(proc.stdout)["compliant"] is True

    def test_exit_1_non_compliant(self) -> None:
        proc = self._run([], json.dumps(AUTH_LEAKS_SECRET))
        assert proc.returncode == 1
        assert "secret_in_telemetry:external_call_outcome" in proc.stdout

    def test_exit_2_malformed_json(self) -> None:
        proc = self._run([], "{not json")
        assert proc.returncode == 2
        assert "error:" in proc.stderr

    def test_exit_2_non_object_json(self) -> None:
        assert self._run([], "[]").returncode == 2

    def test_reads_file_argument(self, tmp_path: Path) -> None:
        scenario_file = tmp_path / "s.json"
        scenario_file.write_text(json.dumps(RETRY_NO_EXHAUSTION))
        proc = self._run([str(scenario_file)], "")
        assert proc.returncode == 1
        assert "missing_required_event:retry_exhaustion" in proc.stdout

    def test_main_returns_2_on_missing_file(self, tmp_path: Path) -> None:
        assert main([str(tmp_path / "absent.json")]) == 2

    def test_main_returns_0_from_file(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        scenario_file = tmp_path / "ok.json"
        scenario_file.write_text(json.dumps(JOB_OK))
        assert main([str(scenario_file)]) == 0
        assert json.loads(capsys.readouterr().out)["compliant"] is True

    def test_main_reads_stdin(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(PURE_HELPER)))
        assert main([]) == 0
        assert json.loads(capsys.readouterr().out)["compliant"] is True


def _table_rows(heading: str) -> list[str]:
    """Return the first-column row numbers of the table under `## <heading>`."""
    text = CONTRACT_PATH.read_text(encoding="utf-8")
    section = re.search(rf"^## {re.escape(heading)}\n(.*?)(?=^## )", text, re.S | re.M)
    assert section, f"heading {heading!r} missing from {CONTRACT_PATH}"
    return re.findall(r"^\| (\d+) \|", section.group(1), re.M)


class TestContractConformance:
    """The checker covers every mechanical row of the document it encodes."""

    # MUST Emit rows 1-7 and 9 map to a behavior flag. Row 8 is a judgment call.
    EMIT_ROW_TO_FLAG = {
        "1": "job_lifecycle",
        "2": "state_transition",
        "3": "external_call",
        "4": "retry",
        "5": "rate_limited",
        "6": "skip_changes_behavior",
        "7": "error_not_swallowed",
        "9": "cancellation_differs",
    }
    # MUST NOT rows 1-5 map to a prohibited flag. Row 6 (pillar choice) is a judgment call.
    NOT_ROW_TO_FLAG = {
        "1": "per_function_entry_exit",
        "2": "duplicate_of_lower_layer",
        "3": "contains_secret",
        "4": "full_body",
        "5": "high_cardinality_no_value",
    }

    def test_must_emit_rows_are_the_known_nine(self) -> None:
        assert _table_rows("MUST Emit") == [str(n) for n in range(1, 10)]

    def test_must_not_emit_rows_are_the_known_six(self) -> None:
        assert _table_rows("MUST NOT Emit") == [str(n) for n in range(1, 7)]

    def test_every_mechanical_emit_row_has_a_checker_flag(self) -> None:
        assert set(self.EMIT_ROW_TO_FLAG.values()) == set(mod.REQUIRED)

    def test_every_mechanical_prohibition_has_a_checker_flag(self) -> None:
        mapped = set(self.NOT_ROW_TO_FLAG.values())
        assert mapped == set(mod.PROHIBITED_FLAGS)

    def test_contract_names_the_governing_principle(self) -> None:
        text = CONTRACT_PATH.read_text(encoding="utf-8")
        assert "reconstruct externally meaningful state" in text
