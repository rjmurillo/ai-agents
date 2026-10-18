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
import re
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

    def test_reused_dict_does_not_keep_a_stale_count(self, monkeypatch):
        response = _anthropic_api.MessageResponse("text", "end_turn", "completed", ())
        monkeypatch.setattr(_anthropic_api, "call_api_response", lambda *a, **k: response)
        metadata: dict[str, object] = {"output_tokens": 99}
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
    def _run(monkeypatch, usage: object, termination: str | None = None) -> dict[str, Any]:
        monkeypatch.setattr(eval_mod, "RATE_LIMIT_SLEEP_SEC", 0)

        def fake_call(*args, metadata=None, **kwargs):
            if metadata is not None and usage is not None:
                metadata["output_tokens"] = usage
            if metadata is not None and termination is not None:
                metadata["termination"] = termination
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

    @pytest.mark.parametrize("termination", ["token_limit", "refusal", "incomplete"])
    def test_cut_or_refused_response_records_why_and_no_size(self, monkeypatch, termination):
        result = self._run(monkeypatch, 600, termination=termination)
        for mech in ("baseline", "full"):
            cell = result["mechanisms"][mech]
            assert cell["termination"] == termination
            assert "output_tokens" not in cell
            assert "response_chars" not in cell

    @pytest.mark.parametrize("termination", ["completed", "unknown"])
    def test_finished_or_unreported_response_keeps_its_size(self, monkeypatch, termination):
        result = self._run(monkeypatch, 55, termination=termination)
        cell = result["mechanisms"]["full"]
        assert cell["termination"] == termination
        assert cell["output_tokens"] == 55
        assert cell["response_chars"] == len("response")

    def test_provider_without_termination_metadata_keeps_its_size(self, monkeypatch):
        result = self._run(monkeypatch, 55)
        cell = result["mechanisms"]["full"]
        assert "termination" not in cell
        assert cell["response_chars"] == len("response")


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
        assert "Mean response chars: baseline 300.0 (n=1), full 120.0 (n=1)" in text
        assert "Mean output tokens" not in text

    def test_render_table_omits_chars_when_arms_cover_different_cells(self):
        first = _make_scenario(2, 3, 4)
        second = _make_scenario(2, 3, 4)
        first["mechanisms"]["baseline"]["response_chars"] = 500
        second["mechanisms"]["baseline"]["response_chars"] = 50
        first["mechanisms"]["full"]["response_chars"] = 50
        text = eval_mod.render_table("voice", eval_mod.aggregate([first, second]))
        assert "Mean response chars" not in text


def _cell(mean: Any = None, count: Any = None, scenarios: int = 2) -> dict[str, Any]:
    return {"mean_output_tokens": mean, "output_token_count": count, "scenario_count": scenarios}


class TestOutputTokenDelta:
    def test_negative_when_the_rule_shortens_responses(self):
        assert eval_mod._output_token_delta(_cell(60.0, 2), _cell(140.5, 2)) == -80.5

    def test_positive_when_the_rule_lengthens_responses(self):
        assert eval_mod._output_token_delta(_cell(9, 2), _cell(4, 2)) == 5

    @pytest.mark.parametrize(
        "treated, base",
        [
            (_cell(None, 0), _cell(10, 2)),
            (_cell(10, 2), _cell(None, 0)),
            ({}, _cell(10, 2)),
            (_cell(10, 2), {}),
            ({"mean_output_tokens": 10}, {"mean_output_tokens": 4}),
        ],
    )
    def test_unmeasured_side_gives_none_not_zero(self, treated, base):
        assert eval_mod._output_token_delta(treated, base) is None

    @pytest.mark.parametrize(
        "treated, base",
        [
            (_cell(50.0, 1), _cell(275.0, 2)),
            (_cell(50.0, 2), _cell(275.0, 1)),
            (_cell(50.0, 1), _cell(500.0, 1)),
        ],
    )
    def test_unequal_coverage_gives_none_not_a_mixed_delta(self, treated, base):
        """Baseline 500 and 50 against full 50 and none published -225.0 over unlike cells."""
        assert eval_mod._output_token_delta(treated, base) is None

    @pytest.mark.parametrize("count", [True, 2.0, "2", 0])
    def test_non_integer_or_zero_counts_are_not_coverage(self, count):
        assert eval_mod._output_token_delta(_cell(5, count), _cell(9, 2)) is None

    def test_aggregate_with_partial_coverage_publishes_none(self):
        scenarios = [
            _with_tokens(_make_scenario(2, 3, 4), baseline=500, full=50),
            _with_tokens(_make_scenario(2, 3, 4), baseline=50),
        ]
        summary = eval_mod.aggregate(scenarios)
        assert summary["output_tokens_delta_full_vs_baseline"] is None
        assert "Mean output tokens" not in eval_mod.render_table("voice", summary)

    def test_aggregate_publishes_the_delta(self):
        scenarios = [
            _with_tokens(_make_scenario(2, 3, 4), baseline=120, full=70),
            _with_tokens(_make_scenario(2, 3, 4), baseline=100, full=50),
        ]
        summary = eval_mod.aggregate(scenarios)
        assert summary["output_tokens_delta_full_vs_baseline"] == -50.0

    def test_aggregate_with_a_clipped_cell_publishes_none(self):
        """A cell cut at the token cap carries no size, so the pool is not covered."""
        clipped = _with_tokens(_make_scenario(2, 3, 4), baseline=600)
        clipped["mechanisms"]["full"]["termination"] = "token_limit"
        scenarios = [
            _with_tokens(_make_scenario(2, 3, 4), baseline=120, full=70),
            clipped,
        ]
        summary = eval_mod.aggregate(scenarios)
        assert summary["output_tokens_delta_full_vs_baseline"] is None
        assert "Mean output tokens" not in eval_mod.render_table("voice", summary)

    def test_delta_is_taken_from_exact_means_not_rounded_ones(self):
        """Means 10.667 and 10.333 publish as 10.7 and 10.3; their gap is 0.3, not 0.4."""
        baseline = [11, 11, 10]
        full = [10, 10, 11]
        scenarios = [
            _with_tokens(_make_scenario(2, 3, 4), baseline=b, full=f)
            for b, f in zip(baseline, full, strict=True)
        ]
        summary = eval_mod.aggregate(scenarios)
        per_mech = summary["per_mechanism"]
        assert per_mech["baseline"]["mean_output_tokens"] == 10.7
        assert per_mech["full"]["mean_output_tokens"] == 10.3
        assert summary["output_tokens_delta_full_vs_baseline"] == -0.3

    def test_aggregate_without_usage_publishes_none(self):
        summary = eval_mod.aggregate([_make_scenario(2, 3, 4)])
        assert summary["output_tokens_delta_full_vs_baseline"] is None

    def test_render_table_prints_the_line_only_when_measured(self):
        measured = eval_mod.aggregate([_with_tokens(_make_scenario(2, 3, 4), 120, 70)])
        unmeasured = eval_mod.aggregate([_make_scenario(2, 3, 4)])
        assert (
            "Mean output tokens: baseline 120.0 (n=1), full 70.0 (n=1) (-50.0)"
            in eval_mod.render_table("voice", measured)
        )
        assert "Mean output tokens" not in eval_mod.render_table("voice", unmeasured)


def _with_chars(
    scenario: dict[str, Any], baseline: int | None = None, full: int | None = None
) -> dict[str, Any]:
    for mech, chars in (("baseline", baseline), ("full", full)):
        if chars is not None:
            scenario["mechanisms"][mech]["response_chars"] = chars
    return scenario


class TestNegativePoolSize:
    """Issue #5405: a shrink on exempt cases must reach the table, not only the positive pool."""

    def test_negative_shrink_is_published_beside_the_positive_delta(self):
        scenarios = [
            _with_chars(_make_scenario(2, 3, 4), baseline=600, full=100),
            _with_chars(_make_scenario(2, 3, 4, negative=True), baseline=5027, full=2926),
            _with_chars(_make_scenario(2, 3, 4, negative=True), baseline=1249, full=1594),
        ]
        summary = eval_mod.aggregate(scenarios)
        assert summary["response_chars_delta_full_vs_baseline"] == -500.0
        assert summary["negative_response_chars_delta_full_vs_baseline"] == -878.0
        text = eval_mod.render_table("voice", summary)
        assert "Mean response chars: baseline 600.0 (n=1), full 100.0 (n=1) (-500.0)" in text
        assert (
            "Negative-pool mean response chars: baseline 3138.0 (n=2), "
            "full 2260.0 (n=2) (-878.0)" in text
        )

    def test_negative_tokens_are_published_when_both_arms_report(self):
        scenarios = [
            _with_tokens(_make_scenario(2, 3, 4), baseline=120, full=70),
            _with_tokens(_make_scenario(2, 3, 4, negative=True), baseline=900, full=400),
        ]
        summary = eval_mod.aggregate(scenarios)
        assert summary["negative_output_tokens_delta_full_vs_baseline"] == -500.0
        assert (
            "Negative-pool mean output tokens: baseline 900.0 (n=1), full 400.0 (n=1) (-500.0)"
            in eval_mod.render_table("voice", summary)
        )

    def test_no_negative_size_line_without_negative_measurements(self):
        scenarios = [
            _with_chars(_make_scenario(2, 3, 4), baseline=600, full=100),
            _make_scenario(2, 3, 4, negative=True),
        ]
        summary = eval_mod.aggregate(scenarios)
        assert summary["negative_response_chars_delta_full_vs_baseline"] is None
        assert summary["negative_output_tokens_delta_full_vs_baseline"] is None
        assert "Negative-pool" not in eval_mod.render_table("voice", summary)

    def test_partial_negative_coverage_publishes_none_not_a_mixed_delta(self):
        scenarios = [
            _with_chars(_make_scenario(2, 3, 4, negative=True), baseline=5000, full=100),
            _with_chars(_make_scenario(2, 3, 4, negative=True), baseline=50),
        ]
        summary = eval_mod.aggregate(scenarios)
        assert summary["negative_response_chars_delta_full_vs_baseline"] is None
        assert "Negative-pool" not in eval_mod.render_table("voice", summary)

    def test_negative_growth_prints_a_plus_sign(self):
        scenarios = [
            _with_chars(_make_scenario(2, 3, 4), baseline=600, full=100),
            _with_chars(_make_scenario(2, 3, 4, negative=True), baseline=1249, full=1594),
        ]
        text = eval_mod.render_table("voice", eval_mod.aggregate(scenarios))
        assert "full 1594.0 (n=1) (+345.0)" in text


RULE_VOCABULARY = re.compile(r"\b(FAILED|UNAVAILABLE|NOT RUN|INFERRED)\b")

LENGTH_CUE = re.compile(
    r"\b(words?|lines?|one-line|terse|concise|brief|short|sentences?|bullets?)\b",
    re.IGNORECASE,
)


class TestVoiceReportingFixtures:
    """Shape of the #5405 claim-grounding and concision scenarios in voice.json."""

    @pytest.fixture
    def scenarios(self) -> dict[str, dict[str, Any]]:
        data = json.loads(VOICE_SCENARIOS.read_text(encoding="utf-8"))
        return {s["id"]: s for s in data["scenarios"]}

    def test_every_evidence_state_has_a_scenario(self, scenarios):
        """Each state is pinned by its gate, not by the rule's own vocabulary."""
        gates = {s["expected_gate"] for s in scenarios.values()}
        state_gates = {
            "failed": {"enforce-failure-report", "enforce-failed-not-updated"},
            "not run": {"enforce-not-run"},
            "unavailable": {"enforce-unavailable-state"},
            "inferred": {"enforce-inference-label"},
        }
        for state, wanted in state_gates.items():
            assert wanted <= gates, state

    def test_claim_signals_describe_behavior_not_the_rule_vocabulary(self, scenarios):
        """The baseline arm never sees the rule, so a signal must not need its tokens.

        A literal 'FAILED' or 'NOT RUN' rewards vocabulary the baseline cannot know,
        which inflates the full-vs-baseline gain. Issue #5405 asks for the semantic
        distinction.
        """
        for sid in ("V6", "V7", "V8", "V9", "V10", "V11", "V12", "V13", "V14"):
            for signal in scenarios[sid]["expected_signals"]:
                match = RULE_VOCABULARY.search(signal)
                assert match is None, (sid, signal)

    @pytest.mark.parametrize(
        "text", ["FAILED", "Tests: NOT RUN", "UNAVAILABLE", "INFERRED safe to merge"]
    )
    def test_rule_vocabulary_pattern_matches_the_state_tokens(self, text):
        assert RULE_VOCABULARY.search(text)

    @pytest.mark.parametrize(
        "text",
        ["reports the push as failed, not completed", "tests reported as not run", "unavailable"],
    )
    def test_rule_vocabulary_pattern_ignores_plain_behavior_wording(self, text):
        assert RULE_VOCABULARY.search(text) is None

    def test_partial_scope_signal_does_not_assert_an_unobserved_state(self, scenarios):
        """V12 never read threads 4 and 5 back, so 'open' would be an ungrounded claim."""
        signals = " ".join(scenarios["V12"]["expected_signals"])
        assert "open" not in signals
        assert "state not checked" in signals

    def test_partial_scope_and_unread_result_have_scenarios(self, scenarios):
        gates = {s["expected_gate"] for s in scenarios.values()}
        assert {"enforce-all-needs-full-scope", "enforce-unread-not-passed"} <= gates

    def test_semantic_equivalence_scenario_names_each_state_it_must_keep(self, scenarios):
        signals = " ".join(scenarios["V14"]["expected_signals"])
        assert "not run" in signals and "inference" in signals and "confirmed" in signals

    def test_exemptions_are_negative_cases(self, scenarios):
        for sid in ("V15", "V16", "V17"):
            assert eval_mod._is_negative_gate(scenarios[sid]["expected_gate"]), sid

    def test_claim_scenarios_are_positive_cases(self, scenarios):
        for sid in ("V6", "V7", "V8", "V9", "V10", "V11", "V12", "V13", "V14"):
            assert not eval_mod._is_negative_gate(scenarios[sid]["expected_gate"]), sid

    def test_size_comparison_inputs_carry_no_length_or_format_cues(self, scenarios):
        """V6 to V13 feed the response-size mean, so only the rule may supply terseness.

        V14 is outside this set: its task is a terse rewrite, so the cue is the task.
        V10 keeps a 'Tests:' line because it measures the NOT RUN state, not length.
        """
        for n in range(6, 14):
            text = scenarios[f"V{n}"]["input"].replace("a 'Tests:' line", "")
            match = LENGTH_CUE.search(text)
            assert match is None, (f"V{n}", match and match.group(0))

    @pytest.mark.parametrize(
        "text",
        ["in one or two lines", "under 60 words", "keep it concise", "a one-line answer"],
    )
    def test_length_cue_pattern_matches_known_cues(self, text):
        assert LENGTH_CUE.search(text)

    def test_length_cue_pattern_ignores_plain_task_text(self):
        assert LENGTH_CUE.search("Write the completion report for the user.") is None

    def test_inference_scenario_signals_describe_behavior_not_vocabulary(self, scenarios):
        signals = scenarios["V13"]["expected_signals"]
        assert "likely" not in signals
        assert any("inference" in sig for sig in signals)
        assert any("body" in sig for sig in signals)

    def test_ids_are_unique_and_inputs_do_not_ask_for_file_changes(self, scenarios):
        data = json.loads(VOICE_SCENARIOS.read_text(encoding="utf-8"))
        ids = [s["id"] for s in data["scenarios"]]
        assert len(ids) == len(set(ids))
        assert all("Do not modify any files." in s["input"] for s in data["scenarios"])
