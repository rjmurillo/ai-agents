#!/usr/bin/env python3
"""Tests for the operational event-logging contract checker.

Covers the nine reference scenarios from issue #5413, per-function positive,
negative, and edge cases, and CLI exit codes (0 compliant, 1 non-compliant,
2 malformed). The checker under test lives at
.claude/skills/observability/scripts/check_event_logging.py; the contract it
encodes is .claude/skills/observability/references/event-logging-contract.md.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)

from claude_skills_import import import_skill_script

SCRIPT_REL = ".claude/skills/observability/scripts/check_event_logging.py"
mod = import_skill_script(SCRIPT_REL)
classify_scenario = mod.classify_scenario
required_categories = mod.required_categories
missing_required = mod.missing_required
prohibited_findings = mod.prohibited_findings
main = mod.main

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = PROJECT_ROOT / SCRIPT_REL


# --- Nine reference scenarios (issue #5413): compliant + violating pair each ---

# 1. Stateful background job needs start/end/count/duration/result.
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

# 2. Successful external call: one outcome event, no per-layer duplication.
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

# 3. Retry path: failed attempt + exhaustion explain the outcome.
RETRY_OK = {
    "behavior": {"retry": True},
    "emits": [
        {"event": "retry_attempt", "fields": {"attempt": 1}},
        {"event": "retry_exhaustion", "fields": {"attempt": 3}},
    ],
}
RETRY_NO_EXHAUSTION = {
    "behavior": {"retry": True},
    "emits": [{"event": "retry_attempt", "fields": {"attempt": 1}}],
}

# 4. Intentional skip whose reason must be observable.
SKIP_OK = {
    "behavior": {"skip_changes_behavior": True},
    "emits": [{"event": "skip", "fields": {"reason": "manifest missing"}}],
}
SKIP_NO_REASON = {
    "behavior": {"skip_changes_behavior": True},
    "emits": [{"event": "skip", "fields": {}}],
}

# 5. Error path not swallowed, has operation context, no secret.
ERROR_OK = {
    "behavior": {"error_not_swallowed": True},
    "emits": [{"event": "error", "fields": {"operation": "sync_manifest"}}],
}
ERROR_SWALLOWED = {
    "behavior": {"error_not_swallowed": True},
    "emits": [],
}

# 6. Secret-bearing auth request: token/body must NOT be logged.
AUTH_REDACTED = {
    "behavior": {"external_call": True},
    "emits": [
        {
            "event": "external_call_outcome",
            "fields": {"operation": "POST /token", "status": 200},
            "contains_secret": False,
        },
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

# 7. Pure in-memory helper needs NO operational event (absence is valid).
PURE_HELPER = {"behavior": {}, "emits": []}
PURE_HELPER_OVERLOGS = {
    "behavior": {},
    "emits": [{"event": "trace", "per_function_entry_exit": True}],
}

# 8. Signal already captured by lower layer: do not duplicate.
DOWNSTREAM_SILENT = {"behavior": {}, "emits": []}
DOWNSTREAM_DUPLICATED = {
    "behavior": {},
    "emits": [{"event": "state_transition", "duplicate_of_lower_layer": True}],
}

# 9. High-cardinality field with no diagnostic value: reject.
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


class TestNineScenarios:
    """Each issue #5413 scenario: compliant passes, violating variant is caught."""

    @pytest.mark.parametrize(
        "scenario",
        [JOB_OK, CALL_OK, RETRY_OK, SKIP_OK, ERROR_OK, AUTH_REDACTED,
         PURE_HELPER, DOWNSTREAM_SILENT, CARDINALITY_OK],
    )
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
            (PURE_HELPER_OVERLOGS, "function_entry_exit:trace"),
            (DOWNSTREAM_DUPLICATED, "duplicate_event:state_transition"),
            (CARDINALITY_REJECTED, "high_cardinality:state_transition"),
        ],
    )
    def test_violating_scenarios_are_detected(self, scenario: dict, expected: str) -> None:
        result = classify_scenario(scenario)
        assert not result["compliant"]
        assert expected in result["findings"]

    def test_pure_helper_absence_is_valid_not_a_gap(self) -> None:
        # The load-bearing negative control: no logging is the correct state.
        assert classify_scenario(PURE_HELPER)["findings"] == []


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
        scenario = {"behavior": {"skip_changes_behavior": True}, "emits": [{"event": "skip"}]}
        findings = missing_required(scenario["behavior"], scenario["emits"])
        assert findings == ["missing_field:skip.reason"]


class TestProhibitedFindings:
    def test_pos_clean_emits(self) -> None:
        assert prohibited_findings(CALL_OK["emits"]) == []

    def test_neg_secret_flagged(self) -> None:
        assert prohibited_findings(AUTH_LEAKS_SECRET["emits"]) == [
            "secret_in_telemetry:external_call_outcome"
        ]

    def test_edge_empty_emits(self) -> None:
        assert prohibited_findings([]) == []

    def test_duplicate_detected_without_lower_layer_flag(self) -> None:
        assert "duplicate_event:external_call_outcome" in prohibited_findings(
            CALL_DUPLICATED["emits"]
        )


class TestClassifyScenarioEdges:
    def test_empty_scenario_is_compliant(self) -> None:
        assert classify_scenario({})["compliant"] is True

    def test_bad_behavior_type_raises(self) -> None:
        with pytest.raises(ValueError):
            classify_scenario({"behavior": [], "emits": []})

    def test_bad_emits_type_raises(self) -> None:
        with pytest.raises(ValueError):
            classify_scenario({"behavior": {}, "emits": {}})


class TestCli:
    def _run(self, args: list[str], stdin: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT_PATH), *args],
            input=stdin,
            capture_output=True,
            text=True,
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
        proc = self._run([], "[]")
        assert proc.returncode == 2

    def test_reads_file_argument(self, tmp_path: Path) -> None:
        scenario_file = tmp_path / "s.json"
        scenario_file.write_text(json.dumps(RETRY_NO_EXHAUSTION))
        proc = self._run([str(scenario_file)], "")
        assert proc.returncode == 1
        assert "missing_required_event:retry_exhaustion" in proc.stdout

    def test_main_returns_2_on_missing_file(self) -> None:
        assert main(["does-not-exist.json"]) == 2

    def test_main_returns_0_from_file(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        scenario_file = tmp_path / "ok.json"
        scenario_file.write_text(json.dumps(JOB_OK))
        assert main([str(scenario_file)]) == 0
        assert json.loads(capsys.readouterr().out)["compliant"] is True

    def test_main_returns_1_from_file(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        scenario_file = tmp_path / "bad.json"
        scenario_file.write_text(json.dumps(AUTH_LEAKS_SECRET))
        assert main([str(scenario_file)]) == 1
        assert "secret_in_telemetry" in capsys.readouterr().out

    def test_main_reads_stdin(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        import io

        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(PURE_HELPER)))
        assert main([]) == 0
        assert json.loads(capsys.readouterr().out)["compliant"] is True
