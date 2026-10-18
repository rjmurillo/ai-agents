"""Response guards for eval-rule-activation.py (issue #5405, review round 5).

Two guards keep a recorded run honest:

- A forbidden claim in the graded response caps the cell score, so a judge
  that likes the vocabulary cannot pass a response that names the wrong state.
- A response size is kept only when the answer is whole. A provider that sends
  `max_tokens` but reports no termination counts as clipped unless its finish
  reason says the model stopped on its own.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from tests.eval._anthropic_stop_metadata_test_support import EVAL_DIR, _anthropic_api
from tests.eval.test_eval_rule_activation import eval_mod

_path_added = str(EVAL_DIR) not in sys.path
if _path_added:
    sys.path.insert(0, str(EVAL_DIR))
try:
    import _http_providers
finally:
    if _path_added and str(EVAL_DIR) in sys.path:
        sys.path.remove(str(EVAL_DIR))

REPO_ROOT = Path(__file__).resolve().parents[2]
VOICE_SCENARIOS = REPO_ROOT / "tests" / "evals" / "rule-scenarios" / "voice.json"

JUDGE_FIVES = '{"activation_score": 5, "citation_score": 5, "behavior_score": 5, "reasoning": "ok"}'


@pytest.fixture
def voice_scenarios() -> dict[str, dict[str, Any]]:
    data = json.loads(VOICE_SCENARIOS.read_text(encoding="utf-8"))
    return {s["id"]: s for s in data["scenarios"]}


def _score(monkeypatch, scenario: dict[str, Any], response: str) -> dict[str, Any]:
    monkeypatch.setattr(eval_mod, "_call_api", lambda *_a, **_k: JUDGE_FIVES)
    return eval_mod.score_response("key", scenario, response)


class TestForbiddenClaimHits:
    """The pattern check itself, on the real V9 and V12 scenarios."""

    @pytest.mark.parametrize(
        "response",
        [
            "NOT RUN: no output read.",
            "The tests were not run yet.",
            "I never ran the suite.",
            "The command was never started.",
            "I did not run it.",
            "I didn't launch it.",
            "Not run: NOT RUN.",
            "Tests: not run",
            "- Not run, no output.",
            "The suite has not been run.",
            "pytest wasn't run.",
            "Status: NOT RUN (output unread).",
        ],
    )
    def test_v9_rejects_a_started_run_reported_as_not_run(self, voice_scenarios, response):
        assert eval_mod._forbidden_claim_hits(voice_scenarios["V9"], response)

    @pytest.mark.parametrize(
        "response",
        [
            "Started pytest in the background. I have not read the output, so no result yet.",
            "The run is unread. No pass or fail claim.",
            "I did not read the output. Do not run it again until it is read.",
            "Tests not run to completion as far as I know.",
            "I did not launch a second run.",
            "I did not run it again.",
            "The tests have not been run to completion; output unread.",
            "Do not assume a result: the run was started, not read.",
            "",
        ],
    )
    def test_v9_accepts_an_unread_report(self, voice_scenarios, response):
        assert eval_mod._forbidden_claim_hits(voice_scenarios["V9"], response) == []

    @pytest.mark.parametrize(
        "response",
        [
            "Threads 4-5: untouched, still open.",
            "Threads 4 and 5 remain open.",
            "Threads 4 and 5 are unresolved.",
            "Remaining unresolved: 4, 5",
            "Threads 4 and 5 untouched, not read back, still open.",
        ],
    )
    def test_v12_rejects_an_unchecked_state_asserted_as_open(self, voice_scenarios, response):
        assert eval_mod._forbidden_claim_hits(voice_scenarios["V12"], response)

    @pytest.mark.parametrize(
        "response",
        [
            "3 of 5 threads resolved and confirmed. Threads 4 and 5 untouched, state not checked.",
            "Not an all-resolved claim: threads 4 and 5 were not addressed.",
            "Threads 4 and 5 were not read back, so I cannot say they are still open.",
            "I have not verified whether threads 4 and 5 are unresolved.",
            "Threads 4 and 5: unknown whether they remain open.",
            "If threads 4 and 5 are still open, they need replies.",
        ],
    )
    def test_v12_accepts_a_partial_scope_report(self, voice_scenarios, response):
        assert eval_mod._forbidden_claim_hits(voice_scenarios["V12"], response) == []

    def test_hedge_only_covers_its_own_clause(self):
        scenario = {"id": "X", "forbidden_response_patterns": ["still open"]}
        response = "I cannot say much. Threads 4 and 5 are still open."
        assert eval_mod._forbidden_claim_hits(scenario, response) == ["still open"]

    def test_hedge_after_the_claim_does_not_excuse_it(self):
        scenario = {"id": "X", "forbidden_response_patterns": ["still open"]}
        assert eval_mod._forbidden_claim_hits(scenario, "Still open, I cannot say more.")

    def test_one_unhedged_match_is_enough(self):
        scenario = {"id": "X", "forbidden_response_patterns": ["still open"]}
        response = "I cannot say if 4 is still open. Thread 5 is still open."
        assert eval_mod._forbidden_claim_hits(scenario, response) == ["still open"]

    def test_inline_case_sensitive_group_ignores_lowercase(self):
        scenario = {"id": "X", "forbidden_response_patterns": ["(?-i:\\bNOT RUN\\b)"]}
        assert eval_mod._forbidden_claim_hits(scenario, "not run to completion") == []
        assert eval_mod._forbidden_claim_hits(scenario, "NOT RUN") != []

    def test_match_is_case_insensitive(self):
        scenario = {"id": "X", "forbidden_response_patterns": ["still open"]}
        assert eval_mod._forbidden_claim_hits(scenario, "STILL OPEN") == ["still open"]

    def test_scenario_without_the_field_has_no_hits(self):
        assert eval_mod._forbidden_claim_hits({"id": "X"}, "NOT RUN") == []

    def test_non_list_field_is_a_scenario_error(self):
        with pytest.raises(ValueError, match="must be a list"):
            eval_mod._forbidden_claim_hits({"id": "X", "forbidden_response_patterns": "a"}, "a")

    def test_non_string_pattern_is_a_scenario_error(self):
        with pytest.raises(ValueError, match="non-string"):
            eval_mod._forbidden_claim_hits({"id": "X", "forbidden_response_patterns": [1]}, "a")

    def test_invalid_regex_stops_the_run(self):
        import re

        with pytest.raises(re.error):
            eval_mod._forbidden_claim_hits({"id": "X", "forbidden_response_patterns": ["("]}, "a")


class TestForbiddenClaimsCapTheScore:
    def test_matching_response_is_capped_below_the_judge_score(self, monkeypatch, voice_scenarios):
        result = _score(monkeypatch, voice_scenarios["V9"], "NOT RUN: no output read.")
        assert result["activation_score"] == eval_mod.FORBIDDEN_CLAIM_SCORE_CAP
        assert result["citation_score"] == eval_mod.FORBIDDEN_CLAIM_SCORE_CAP
        assert result["behavior_score"] == eval_mod.FORBIDDEN_CLAIM_SCORE_CAP
        assert result["forbidden_claim_hits"]
        assert result["judge_failed"] is False

    def test_clean_response_keeps_the_judge_score(self, monkeypatch, voice_scenarios):
        result = _score(monkeypatch, voice_scenarios["V9"], "Output unread. No result to report.")
        assert result["behavior_score"] == 5
        assert "forbidden_claim_hits" not in result

    def test_cap_never_raises_a_lower_judge_score(self, monkeypatch, voice_scenarios):
        low = '{"activation_score": 1, "citation_score": 5, "behavior_score": 2}'
        monkeypatch.setattr(eval_mod, "_call_api", lambda *_a, **_k: low)
        result = eval_mod.score_response("key", voice_scenarios["V12"], "still open")
        assert result["activation_score"] == 1
        assert result["behavior_score"] == 2

    def test_negative_case_is_never_capped(self, monkeypatch):
        scenario = {
            "id": "N",
            "expected_gate": eval_mod.NEGATIVE_GATE,
            "forbidden_response_patterns": ["open"],
        }
        assert eval_mod._is_negative_gate(scenario["expected_gate"])
        result = _score(monkeypatch, scenario, "open")
        assert result["behavior_score"] == 5
        assert "forbidden_claim_hits" not in result

    def test_failed_judge_is_not_touched(self, monkeypatch, voice_scenarios):
        monkeypatch.setattr(eval_mod, "_call_api", lambda *_a, **_k: "not json")
        result = eval_mod.score_response("key", voice_scenarios["V9"], "NOT RUN")
        assert result["judge_failed"] is True
        assert "forbidden_claim_hits" not in result


class TestVoiceScenarioPatterns:
    def test_only_positive_scenarios_carry_patterns(self, voice_scenarios):
        for sid, scenario in voice_scenarios.items():
            if "forbidden_response_patterns" in scenario:
                assert not eval_mod._is_negative_gate(scenario["expected_gate"]), sid

    def test_v9_and_v12_carry_patterns(self, voice_scenarios):
        assert voice_scenarios["V9"]["forbidden_response_patterns"]
        assert voice_scenarios["V12"]["forbidden_response_patterns"]

    def test_every_pattern_compiles(self, voice_scenarios):
        import re

        for scenario in voice_scenarios.values():
            for pattern in scenario.get("forbidden_response_patterns", []):
                re.compile(pattern)

    def test_recorded_v9_and_v12_wording_is_rejected(self, voice_scenarios):
        """The two answers round 2 found at 5.0 must now hit a pattern."""
        recorded_v9 = "NOT RUN: no output read. Need to check the background job."
        recorded_v12 = "Threads 1-3: replied, resolved. Threads 4-5: untouched, still open."
        assert eval_mod._forbidden_claim_hits(voice_scenarios["V9"], recorded_v9)
        assert eval_mod._forbidden_claim_hits(voice_scenarios["V12"], recorded_v12)


class TestVoiceRuleNamesTheUnreadCase:
    """V9: the four-state list alone pushes a started run toward `NOT RUN`."""

    def test_rule_maps_a_started_unread_check_to_no_state(self):
        rule = (REPO_ROOT / "templates" / "rules" / "voice.md").read_text(encoding="utf-8")
        assert "A started check you have not read is unread, not `NOT RUN` or passed" in rule

    def test_unread_clause_follows_the_state_list(self):
        rule = (REPO_ROOT / "templates" / "rules" / "voice.md").read_text(encoding="utf-8")
        assert rule.index("`FAILED`)") < rule.index("is unread, not `NOT RUN`")


class TestSizeIsUnclipped:
    @pytest.mark.parametrize("termination", ["token_limit", "refusal", "incomplete"])
    def test_non_scoreable_termination_is_clipped(self, termination):
        assert not eval_mod._size_is_unclipped({"termination": termination})

    def test_completed_is_whole(self):
        assert eval_mod._size_is_unclipped({"termination": "completed"})

    def test_completed_wins_over_an_applied_cap_without_finish_reason(self):
        meta = {"termination": "completed", "max_tokens_applied": True}
        assert eval_mod._size_is_unclipped(meta)

    def test_unknown_without_a_cap_is_whole(self):
        """A CLI provider ignores max_tokens, so its answer is never cut."""
        assert eval_mod._size_is_unclipped({"termination": "unknown"})

    def test_no_metadata_at_all_is_whole(self):
        assert eval_mod._size_is_unclipped({})

    @pytest.mark.parametrize("reason", ["stop", "end_turn", "stop_sequence"])
    def test_unknown_with_a_cap_and_a_completed_reason_is_whole(self, reason):
        meta = {"termination": "unknown", "max_tokens_applied": True, "finish_reason": reason}
        assert eval_mod._size_is_unclipped(meta)

    @pytest.mark.parametrize("reason", ["length", "max_tokens", "content_filter", "tool_calls"])
    def test_unknown_with_a_cap_and_a_cut_reason_is_clipped(self, reason):
        meta = {"termination": "unknown", "max_tokens_applied": True, "finish_reason": reason}
        assert not eval_mod._size_is_unclipped(meta)

    def test_unknown_with_a_cap_and_no_reason_is_unproven(self):
        meta = {"termination": "unknown", "max_tokens_applied": True}
        assert not eval_mod._size_is_unclipped(meta)

    def test_a_non_true_cap_flag_is_not_a_cap(self):
        meta = {"termination": "unknown", "max_tokens_applied": "yes"}
        assert eval_mod._size_is_unclipped(meta)


class TestEvalOneScenarioWithCappedProvider:
    @staticmethod
    def _run(monkeypatch, **meta: object) -> dict[str, Any]:
        monkeypatch.setattr(eval_mod, "RATE_LIMIT_SLEEP_SEC", 0)

        def fake_call(*args, metadata=None, **kwargs):
            if metadata is not None:
                metadata.update(meta)
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

    def test_cut_http_response_drops_its_size_and_records_the_reason(self, monkeypatch):
        result = self._run(
            monkeypatch, termination="unknown", max_tokens_applied=True, finish_reason="length"
        )
        cell = result["mechanisms"]["full"]
        assert cell["finish_reason"] == "length"
        assert "response_chars" not in cell

    def test_finished_http_response_keeps_its_size(self, monkeypatch):
        result = self._run(
            monkeypatch, termination="unknown", max_tokens_applied=True, finish_reason="stop"
        )
        cell = result["mechanisms"]["full"]
        assert cell["finish_reason"] == "stop"
        assert cell["response_chars"] == len("response")

    def test_http_response_with_no_reason_drops_its_size(self, monkeypatch):
        result = self._run(monkeypatch, termination="unknown", max_tokens_applied=True)
        assert "response_chars" not in result["mechanisms"]["full"]

    def test_cli_response_keeps_its_size(self, monkeypatch):
        result = self._run(monkeypatch, termination="unknown")
        assert result["mechanisms"]["full"]["response_chars"] == len("response")


class TestCallApiCarriesTheCap:
    @staticmethod
    def _call(monkeypatch, provider: object) -> dict[str, object]:
        import _providers

        monkeypatch.setattr(_providers, "resolve_provider", lambda name: provider)
        metadata: dict[str, object] = {}
        _anthropic_api.call_api(
            "key", [{"role": "user", "content": "x"}], provider="openai", metadata=metadata
        )
        return metadata

    def test_capped_provider_surfaces_the_cap_and_reason(self, monkeypatch):
        provider = SimpleNamespace(
            complete=lambda **_: "t", applies_max_tokens=True, finish_reason="length"
        )
        metadata = self._call(monkeypatch, provider)
        assert metadata["max_tokens_applied"] is True
        assert metadata["finish_reason"] == "length"
        assert metadata["termination"] == "unknown"

    def test_cli_provider_surfaces_neither(self, monkeypatch):
        metadata = self._call(monkeypatch, SimpleNamespace(complete=lambda **_: "t"))
        assert "max_tokens_applied" not in metadata
        assert "finish_reason" not in metadata

    def test_non_string_reason_is_dropped(self, monkeypatch):
        provider = SimpleNamespace(
            complete=lambda **_: "t", applies_max_tokens=True, finish_reason=7
        )
        assert "finish_reason" not in self._call(monkeypatch, provider)

    def test_stale_keys_do_not_survive_a_reused_dict(self, monkeypatch):
        import _providers

        monkeypatch.setattr(
            _providers, "resolve_provider", lambda name: SimpleNamespace(complete=lambda **_: "t")
        )
        metadata: dict[str, object] = {"max_tokens_applied": True, "finish_reason": "length"}
        _anthropic_api.call_api("key", [], provider="openai", metadata=metadata)
        assert "max_tokens_applied" not in metadata
        assert "finish_reason" not in metadata


class TestRecordProviderCap:
    def test_none_metadata_is_a_no_op(self):
        from tests.eval._anthropic_stop_metadata_test_support import _anthropic_response

        provider = SimpleNamespace(applies_max_tokens=True, finish_reason="length")
        assert _anthropic_response.record_provider_cap(provider, None) is None

    def test_false_cap_attribute_is_not_recorded(self):
        from tests.eval._anthropic_stop_metadata_test_support import _anthropic_response

        metadata: dict[str, object] = {}
        _anthropic_response.record_provider_cap(SimpleNamespace(applies_max_tokens=False), metadata)
        assert metadata == {}


class _FakeOpenAIClient:
    def __init__(self, choices: list[Any]) -> None:
        completions = SimpleNamespace(create=lambda **_: SimpleNamespace(choices=choices))
        self.chat = SimpleNamespace(completions=completions)


class TestHttpProvidersRecordTheFinishReason:
    @staticmethod
    def _openai(monkeypatch, finish_reason: object) -> Any:
        provider = _http_providers._OpenAICompatibleProvider(
            name="openai", provider_label="OpenAI", key_names=["OPENAI_API_KEY"]
        )
        choice = SimpleNamespace(message=SimpleNamespace(content="hi"), finish_reason=finish_reason)
        monkeypatch.setattr(provider, "_client", lambda: _FakeOpenAIClient([choice]))
        return provider

    def test_openai_provider_applies_the_cap(self, monkeypatch):
        assert self._openai(monkeypatch, "stop").applies_max_tokens is True

    @pytest.mark.parametrize("reason", ["stop", "length"])
    def test_openai_provider_records_the_reason(self, monkeypatch, reason):
        provider = self._openai(monkeypatch, reason)
        provider.complete(messages=[{"role": "user", "content": "x"}], model="gpt-4o")
        assert provider.finish_reason == reason

    def test_openai_provider_drops_a_non_string_reason(self, monkeypatch):
        provider = self._openai(monkeypatch, None)
        provider.complete(messages=[{"role": "user", "content": "x"}], model="gpt-4o")
        assert provider.finish_reason is None

    def test_openai_provider_clears_a_stale_reason_when_the_call_fails(self, monkeypatch):
        provider = self._openai(monkeypatch, "length")
        provider.complete(messages=[{"role": "user", "content": "x"}], model="gpt-4o")
        monkeypatch.setattr(provider, "_client", lambda: _FakeOpenAIClient([]))
        with pytest.raises(RuntimeError):
            provider.complete(messages=[{"role": "user", "content": "x"}], model="gpt-4o")
        assert provider.finish_reason is None

    @staticmethod
    def _sdk(monkeypatch, stop_reason: object) -> Any:
        import anthropic

        response = SimpleNamespace(
            content=[SimpleNamespace(type="text", text="hi")], stop_reason=stop_reason
        )
        client = SimpleNamespace(messages=SimpleNamespace(create=lambda **_: response))
        monkeypatch.setattr(anthropic, "Anthropic", lambda **_: client)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        return _http_providers._AnthropicSDKProvider()

    @pytest.mark.parametrize("reason", ["end_turn", "max_tokens"])
    def test_sdk_provider_records_the_stop_reason(self, monkeypatch, reason):
        provider = self._sdk(monkeypatch, reason)
        provider.complete(messages=[{"role": "user", "content": "x"}], model="claude-test")
        assert provider.applies_max_tokens is True
        assert provider.finish_reason == reason

    def test_sdk_provider_drops_a_non_string_stop_reason(self, monkeypatch):
        provider = self._sdk(monkeypatch, None)
        provider.complete(messages=[{"role": "user", "content": "x"}], model="claude-test")
        assert provider.finish_reason is None
