"""Tests for REQ-037: `eval-rule-activation.py` and `eval-prompt-change.py`
must not score a refusal, token_limit, or incomplete judge response.

Split out of `test_anthropic_stop_metadata.py` (taste-lints file-size gate);
see `_anthropic_stop_metadata_test_support.py` for the shared loader.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from tests.eval._anthropic_stop_metadata_test_support import (
    prompt_change_mod,
    rule_activation_mod,
)

# ---------------------------------------------------------------------------
# eval-rule-activation.py: refusal / token_limit / incomplete are not scored
# ---------------------------------------------------------------------------


class TestRuleActivationJudgeTermination:
    SCENARIO: dict[str, Any] = {
        "desc": "d",
        "rationale": "r",
        "expected_signals": ["signal"],
        "expected_gate": "",
    }

    def _patch_call_api(self, monkeypatch: pytest.MonkeyPatch, termination: str) -> None:
        def fake(api_key, messages, model=None, seed=None, metadata=None):
            if metadata is not None:
                metadata["termination"] = termination
            return "irrelevant raw text"

        monkeypatch.setattr(rule_activation_mod, "_call_api", fake)

    def test_refusal_is_not_scored(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._patch_call_api(monkeypatch, "refusal")

        result = rule_activation_mod.score_response("key", self.SCENARIO, "response")

        assert result["judge_failed"] is True
        assert result["activation_score"] == 0
        assert result["termination"] == "refusal"
        assert "termination=refusal" in result["reasoning"]

    def test_token_limit_is_not_scored(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._patch_call_api(monkeypatch, "token_limit")

        result = rule_activation_mod.score_response("key", self.SCENARIO, "response")

        assert result["judge_failed"] is True
        assert result["activation_score"] == 0
        assert result["termination"] == "token_limit"

    def test_incomplete_is_not_scored(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._patch_call_api(monkeypatch, "incomplete")

        result = rule_activation_mod.score_response("key", self.SCENARIO, "response")

        assert result["judge_failed"] is True
        assert result["activation_score"] == 0
        assert result["termination"] == "incomplete"

    def test_completed_is_scored_normally(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def fake(api_key, messages, model=None, seed=None, metadata=None):
            if metadata is not None:
                metadata["termination"] = "completed"
            return json.dumps({"activation_score": 4, "citation_score": 3, "behavior_score": 5})

        monkeypatch.setattr(rule_activation_mod, "_call_api", fake)

        result = rule_activation_mod.score_response("key", self.SCENARIO, "response")

        assert result["judge_failed"] is False
        assert result["activation_score"] == 4
        assert result["termination"] == "completed"


# ---------------------------------------------------------------------------
# eval-prompt-change.py: refusal / token_limit / incomplete are not scored
# ---------------------------------------------------------------------------


class TestPromptChangeJudgeTermination:
    SCENARIO: dict[str, Any] = {
        "id": "S1",
        "desc": "d",
        "input": "i",
        "expected_verdict": "ROUTE",
        "verdict_options": ["ROUTE", "DELEGATE"],
    }

    def _patch_call_api(self, monkeypatch: pytest.MonkeyPatch, termination: str) -> None:
        def fake(api_key, messages, system, model, max_tokens, metadata=None):
            if metadata is not None:
                metadata["termination"] = termination
            return "irrelevant raw text"

        monkeypatch.setattr(prompt_change_mod, "call_api", fake)

    def test_refusal_is_flagged_not_scored_not_an_answer(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._patch_call_api(monkeypatch, "refusal")

        out = prompt_change_mod.judge_scenario("k", "sys", self.SCENARIO, "claude")

        assert out["verdict"] == "NOT_SCORED"
        assert out["not_scored"] is True
        assert out["termination"] == "refusal"
        assert "termination=refusal" in out["reason"]
        # `not_scored` is the flag scoring reads; `check_scenario_pass`
        # returns False unconditionally on it (REQ-037 AC-9).
        assert prompt_change_mod.check_scenario_pass(out, self.SCENARIO) is False

    def test_token_limit_is_flagged_not_scored_not_an_answer(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._patch_call_api(monkeypatch, "token_limit")

        out = prompt_change_mod.judge_scenario("k", "sys", self.SCENARIO, "claude")

        assert out["verdict"] == "NOT_SCORED"
        assert out["not_scored"] is True
        assert out["termination"] == "token_limit"
        assert prompt_change_mod.check_scenario_pass(out, self.SCENARIO) is False

    def test_incomplete_is_flagged_not_scored_not_an_answer(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._patch_call_api(monkeypatch, "incomplete")

        out = prompt_change_mod.judge_scenario("k", "sys", self.SCENARIO, "claude")

        assert out["verdict"] == "NOT_SCORED"
        assert out["not_scored"] is True
        assert out["termination"] == "incomplete"
        assert prompt_change_mod.check_scenario_pass(out, self.SCENARIO) is False

    def test_completed_is_scored_normally(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def fake(api_key, messages, system, model, max_tokens, metadata=None):
            if metadata is not None:
                metadata["termination"] = "completed"
            return '{"verdict": "ROUTE", "reason": "ok"}'

        monkeypatch.setattr(prompt_change_mod, "call_api", fake)

        out = prompt_change_mod.judge_scenario("k", "sys", self.SCENARIO, "claude")

        assert out["verdict"] == "ROUTE"
        assert out["not_scored"] is False
        assert out["termination"] == "completed"
        assert prompt_change_mod.check_scenario_pass(out, self.SCENARIO) is True

    @pytest.mark.parametrize("sneaky_expected_verdict", ["ERROR", "NOT_SCORED"])
    def test_a_scenario_naming_the_sentinel_as_expected_verdict_cannot_pass_on_refusal(
        self, monkeypatch: pytest.MonkeyPatch, sneaky_expected_verdict: str
    ) -> None:
        """A scenario whose `expected_verdict` happens to equal a sentinel
        display label must not pass just because the judge was refused."""
        self._patch_call_api(monkeypatch, "refusal")
        scenario = dict(self.SCENARIO, expected_verdict=sneaky_expected_verdict)

        out = prompt_change_mod.judge_scenario("k", "sys", scenario, "claude")

        assert prompt_change_mod.check_scenario_pass(out, scenario) is False


# ---------------------------------------------------------------------------
# eval-prompt-change.py: run_scenario_multi excludes not_scored runs (REQ-037)
# ---------------------------------------------------------------------------


class TestPromptChangeNotScoredAggregation:
    SCENARIO: dict[str, Any] = {
        "id": "S1",
        "desc": "d",
        "input": "i",
        "expected_verdict": "ROUTE",
        "verdict_options": ["ROUTE", "DELEGATE"],
    }

    def _stub_judge(self, monkeypatch: pytest.MonkeyPatch, results: list[dict[str, Any]]) -> None:
        idx = {"i": 0}

        def fake(api_key, prompt, scenario, model):
            result = results[idx["i"] % len(results)]
            idx["i"] += 1
            return dict(result)

        monkeypatch.setattr(prompt_change_mod, "judge_scenario", fake)
        monkeypatch.setattr(prompt_change_mod.time, "sleep", lambda _s: None)

    def test_one_refused_of_three_with_two_passes_still_passes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._stub_judge(
            monkeypatch,
            [
                {"verdict": "ROUTE", "reason": "ok", "not_scored": False},
                {"verdict": "ROUTE", "reason": "ok", "not_scored": False},
                {"verdict": "NOT_SCORED", "reason": "termination=refusal", "not_scored": True},
            ],
        )

        out = prompt_change_mod.run_scenario_multi("k", "p", self.SCENARIO, "m", 3)

        assert out["passed"] is True
        assert out["runs"] == 2
        assert out["requested_runs"] == 3
        assert out["not_scored_runs"] == 1
        assert out["passes"] == 2

    def test_all_three_refused_cannot_pass(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._stub_judge(
            monkeypatch,
            [{"verdict": "NOT_SCORED", "reason": "termination=refusal", "not_scored": True}] * 3,
        )

        out = prompt_change_mod.run_scenario_multi("k", "p", self.SCENARIO, "m", 3)

        assert out["passed"] is False
        assert out["runs"] == 0
        assert out["not_scored_runs"] == 3
        assert out["pass_rate"] == 0.0
