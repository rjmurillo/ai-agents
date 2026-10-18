"""Output-token measurement for eval-rule-activation.py (issue #5405).

The concision invariant in the voice rule is load bearing only if a run with
the rule shows fewer output tokens than a run without it. These tests cover
the plumbing that makes that comparison possible: usage parsing is tested in
`test_anthropic_stop_metadata_parse.py`; here, `call_api` metadata, the
per-cell record, the per-mechanism mean, the full-vs-baseline delta, and the
table line.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tests.eval._anthropic_stop_metadata_test_support import _anthropic_api
from tests.eval.test_eval_rule_activation import _make_scenario, eval_mod

REPO_ROOT = Path(__file__).resolve().parents[2]
VOICE_SCENARIOS = REPO_ROOT / "tests" / "evals" / "rule-scenarios" / "voice.json"


def _with_tokens(
    scenario: dict[str, Any], baseline: Any = None, full: Any = None
) -> dict[str, Any]:
    for mech, tokens in (("baseline", baseline), ("full", full)):
        if tokens is not None:
            scenario["mechanisms"][mech]["output_tokens"] = tokens
    return scenario


class TestCallApiMetadata:
    def test_output_tokens_reach_the_metadata_dict(self, monkeypatch):
        response = _anthropic_api.MessageResponse(
            "text", "end_turn", "completed", (), None, None, 17
        )
        monkeypatch.setattr(_anthropic_api, "call_api_response", lambda *a, **k: response)
        metadata: dict[str, object] = {}
        _anthropic_api.call_api("key", [], metadata=metadata)
        assert metadata["output_tokens"] == 17

    def test_missing_usage_leaves_the_key_absent(self, monkeypatch):
        response = _anthropic_api.MessageResponse("text", "end_turn", "completed", ())
        monkeypatch.setattr(_anthropic_api, "call_api_response", lambda *a, **k: response)
        metadata: dict[str, object] = {}
        _anthropic_api.call_api("key", [], metadata=metadata)
        assert "output_tokens" not in metadata

    def test_zero_tokens_are_recorded_not_dropped(self, monkeypatch):
        response = _anthropic_api.MessageResponse("", "end_turn", "completed", (), None, None, 0)
        monkeypatch.setattr(_anthropic_api, "call_api_response", lambda *a, **k: response)
        metadata: dict[str, object] = {}
        _anthropic_api.call_api("key", [], metadata=metadata)
        assert metadata["output_tokens"] == 0


class TestEvalOneScenarioRecordsTokens:
    @staticmethod
    def _run(monkeypatch, usage: object) -> dict[str, Any]:
        monkeypatch.setattr(eval_mod, "RATE_LIMIT_SLEEP_SEC", 0)

        def fake_call(*args, metadata=None, **kwargs):
            if metadata is not None and usage is not None:
                metadata["output_tokens"] = usage
            return "response"

        monkeypatch.setattr(eval_mod, "_call_api", fake_call)
        monkeypatch.setattr(
            eval_mod,
            "score_response",
            lambda *a, **k: {
                "activation_score": 3,
                "citation_score": 3,
                "behavior_score": 3,
                "judge_failed": False,
            },
        )
        rule = {"name": "voice", "description": "d", "body": "rule body", "path": "p"}
        scenario = {"id": "V6", "input": "x", "expected_gate": "enforce-concise-reporting"}
        return eval_mod.eval_one_scenario(
            "key", rule, "voice", scenario, "model", dry_run=False, judge_repeats=1
        )

    def test_reported_tokens_land_on_the_cell(self, monkeypatch):
        result = self._run(monkeypatch, 55)
        assert result["mechanisms"]["full"]["output_tokens"] == 55
        assert result["mechanisms"]["baseline"]["output_tokens"] == 55

    def test_absent_usage_leaves_no_token_key(self, monkeypatch):
        result = self._run(monkeypatch, None)
        assert "output_tokens" not in result["mechanisms"]["full"]

    def test_bool_usage_is_not_recorded(self, monkeypatch):
        result = self._run(monkeypatch, True)
        assert "output_tokens" not in result["mechanisms"]["full"]


class TestMechanismMean:
    def test_mean_over_cells_that_reported(self):
        pool = [
            _with_tokens(_make_scenario(3, 3, 3), baseline=100),
            _with_tokens(_make_scenario(3, 3, 3), baseline=51),
        ]
        summary = eval_mod._mechanism_summary(pool, "baseline")
        assert summary["mean_output_tokens"] == 75.5
        assert summary["output_token_count"] == 2

    def test_none_when_no_cell_reported(self):
        summary = eval_mod._mechanism_summary([_make_scenario(3, 3, 3)], "baseline")
        assert summary["mean_output_tokens"] is None
        assert summary["output_token_count"] == 0

    @pytest.mark.parametrize("junk", [True, "40", 4.5, None])
    def test_non_integer_counts_are_ignored(self, junk):
        pool = [_with_tokens(_make_scenario(3, 3, 3), baseline=20)]
        pool[0]["mechanisms"]["baseline"]["output_tokens"] = 20
        pool.append(_make_scenario(3, 3, 3))
        pool[1]["mechanisms"]["baseline"]["output_tokens"] = junk
        summary = eval_mod._mechanism_summary(pool, "baseline")
        assert summary["mean_output_tokens"] == 20
        assert summary["output_token_count"] == 1


class TestResponseChars:
    def test_cell_records_the_response_length(self, monkeypatch):
        result = TestEvalOneScenarioRecordsTokens._run(monkeypatch, None)
        assert result["mechanisms"]["full"]["response_chars"] == len("response")

    def test_mean_over_cells_that_recorded_it(self):
        pool = [_make_scenario(3, 3, 3), _make_scenario(3, 3, 3)]
        pool[0]["mechanisms"]["full"]["response_chars"] = 100
        pool[1]["mechanisms"]["full"]["response_chars"] = 50
        summary = eval_mod._mechanism_summary(pool, "full")
        assert summary["mean_response_chars"] == 75.0
        assert summary["response_chars_count"] == 2

    def test_none_when_unrecorded(self):
        summary = eval_mod._mechanism_summary([_make_scenario(3, 3, 3)], "full")
        assert summary["mean_response_chars"] is None
        assert summary["response_chars_count"] == 0

    def test_render_table_prints_chars_for_cli_runs_without_usage(self):
        scenario = _make_scenario(2, 3, 4)
        scenario["mechanisms"]["baseline"]["response_chars"] = 300
        scenario["mechanisms"]["full"]["response_chars"] = 120
        text = eval_mod.render_table("voice", eval_mod.aggregate([scenario]))
        assert "Mean response chars: baseline 300.0, full 120.0" in text
        assert "Mean output tokens" not in text


class TestOutputTokenDelta:
    def test_negative_when_the_rule_shortens_responses(self):
        full = {"mean_output_tokens": 60.0}
        base = {"mean_output_tokens": 140.5}
        assert eval_mod._output_token_delta(full, base) == -80.5

    def test_positive_when_the_rule_lengthens_responses(self):
        assert (
            eval_mod._output_token_delta({"mean_output_tokens": 9}, {"mean_output_tokens": 4}) == 5
        )

    @pytest.mark.parametrize(
        "treated, base",
        [
            ({"mean_output_tokens": None}, {"mean_output_tokens": 10}),
            ({"mean_output_tokens": 10}, {"mean_output_tokens": None}),
            ({}, {"mean_output_tokens": 10}),
            ({"mean_output_tokens": 10}, {}),
        ],
    )
    def test_unmeasured_side_gives_none_not_zero(self, treated, base):
        assert eval_mod._output_token_delta(treated, base) is None

    def test_aggregate_publishes_the_delta(self):
        scenarios = [
            _with_tokens(_make_scenario(2, 3, 4), baseline=120, full=70),
            _with_tokens(_make_scenario(2, 3, 4), baseline=100, full=50),
        ]
        summary = eval_mod.aggregate(scenarios)
        assert summary["output_tokens_delta_full_vs_baseline"] == -50.0

    def test_aggregate_without_usage_publishes_none(self):
        summary = eval_mod.aggregate([_make_scenario(2, 3, 4)])
        assert summary["output_tokens_delta_full_vs_baseline"] is None

    def test_render_table_prints_the_line_only_when_measured(self):
        measured = eval_mod.aggregate([_with_tokens(_make_scenario(2, 3, 4), 120, 70)])
        unmeasured = eval_mod.aggregate([_make_scenario(2, 3, 4)])
        assert "Mean output tokens: baseline 120.0, full 70.0 (-50.0)" in eval_mod.render_table(
            "voice", measured
        )
        assert "Mean output tokens" not in eval_mod.render_table("voice", unmeasured)


class TestVoiceReportingFixtures:
    """Shape of the #5405 claim-grounding and concision scenarios in voice.json."""

    @pytest.fixture
    def scenarios(self) -> dict[str, dict[str, Any]]:
        data = json.loads(VOICE_SCENARIOS.read_text(encoding="utf-8"))
        return {s["id"]: s for s in data["scenarios"]}

    def test_every_evidence_state_has_a_scenario(self, scenarios):
        text = json.dumps([s["expected_signals"] for s in scenarios.values()])
        for state in ("NOT RUN", "FAILED", "UNAVAILABLE", "INFERRED"):
            assert state in text, state

    def test_partial_scope_and_unread_result_have_scenarios(self, scenarios):
        gates = {s["expected_gate"] for s in scenarios.values()}
        assert {"enforce-all-needs-full-scope", "enforce-unread-not-passed"} <= gates

    def test_semantic_equivalence_scenario_names_each_state_it_must_keep(self, scenarios):
        signals = " ".join(scenarios["V14"]["expected_signals"])
        assert "NOT RUN" in signals and "INFERRED" in signals

    def test_exemptions_are_negative_cases(self, scenarios):
        for sid in ("V15", "V16", "V17"):
            assert eval_mod._is_negative_gate(scenarios[sid]["expected_gate"]), sid

    def test_claim_scenarios_are_positive_cases(self, scenarios):
        for sid in ("V6", "V7", "V8", "V9", "V10", "V11", "V12", "V13", "V14"):
            assert not eval_mod._is_negative_gate(scenarios[sid]["expected_gate"]), sid

    def test_ids_are_unique_and_inputs_do_not_ask_for_file_changes(self, scenarios):
        data = json.loads(VOICE_SCENARIOS.read_text(encoding="utf-8"))
        ids = [s["id"] for s in data["scenarios"]]
        assert len(ids) == len(set(ids))
        assert all("Do not modify any files." in s["input"] for s in data["scenarios"])
