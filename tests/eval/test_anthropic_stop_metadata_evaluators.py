"""Tests for REQ-037: `eval-rule-activation.py` and `eval-prompt-change.py`
must not score a refusal, token_limit, or incomplete judge response.

Split out of `test_anthropic_stop_metadata.py` (taste-lints file-size gate);
see `_anthropic_stop_metadata_test_support.py` for the shared loader.
Module-level functions, not classes (CQA cohesion gate: a class adds a
`def`); same-shaped cases are tabled under one `@pytest.mark.parametrize`
function each; the one-off fakes below are lambdas or `itertools.cycle`,
not nested `def`s, since none needs more than one expression (CQA cohesion
gate: a nested `def` also counts).
"""

from __future__ import annotations

import itertools
import json
from typing import Any

import pytest

from tests.eval._anthropic_stop_metadata_test_support import (
    prompt_change_mod,
    rule_activation_mod,
)

_RULE_ACTIVATION_SCENARIO: dict[str, Any] = {
    "desc": "d",
    "rationale": "r",
    "expected_signals": ["signal"],
    "expected_gate": "",
}

_PROMPT_CHANGE_SCENARIO: dict[str, Any] = {
    "id": "S1",
    "desc": "d",
    "input": "i",
    "expected_verdict": "ROUTE",
    "verdict_options": ["ROUTE", "DELEGATE"],
}

_BLOCKING_TERMINATIONS = [
    pytest.param("refusal", id="refusal"),
    pytest.param("token_limit", id="token_limit"),
    pytest.param("incomplete", id="incomplete"),
]


def _fake_call_api(termination: str, text: str):
    """A `call_api`/`_call_api` double that writes `termination` into the
    caller's `metadata` kwarg and returns `text`. Both judges always pass
    `metadata` as a keyword, so `**kwargs` covers either call signature
    without a signature-specific fake per call site."""
    return lambda *_args, **kwargs: (kwargs["metadata"].update(termination=termination) or text)


# eval-rule-activation.py: refusal / token_limit / incomplete are not scored


@pytest.mark.parametrize("termination", _BLOCKING_TERMINATIONS)
def test_rule_activation_judge_not_scored_on_blocking_termination(
    monkeypatch: pytest.MonkeyPatch, termination: str
) -> None:
    monkeypatch.setattr(
        rule_activation_mod, "_call_api", _fake_call_api(termination, "irrelevant raw text")
    )

    result = rule_activation_mod.score_response("key", _RULE_ACTIVATION_SCENARIO, "response")

    assert result["judge_failed"] is True
    assert result["activation_score"] == 0
    assert result["termination"] == termination
    assert f"termination={termination}" in result["reasoning"]


def test_rule_activation_judge_scores_completed_normally(monkeypatch: pytest.MonkeyPatch) -> None:
    scores = json.dumps({"activation_score": 4, "citation_score": 3, "behavior_score": 5})
    monkeypatch.setattr(rule_activation_mod, "_call_api", _fake_call_api("completed", scores))

    result = rule_activation_mod.score_response("key", _RULE_ACTIVATION_SCENARIO, "response")

    assert result["judge_failed"] is False
    assert result["activation_score"] == 4
    assert result["termination"] == "completed"


# eval-prompt-change.py: refusal / token_limit / incomplete are not scored


@pytest.mark.parametrize("termination", _BLOCKING_TERMINATIONS)
def test_prompt_change_judge_not_scored_on_blocking_termination(
    monkeypatch: pytest.MonkeyPatch, termination: str
) -> None:
    monkeypatch.setattr(
        prompt_change_mod, "call_api", _fake_call_api(termination, "irrelevant raw text")
    )

    out = prompt_change_mod.judge_scenario("k", "sys", _PROMPT_CHANGE_SCENARIO, "claude")

    assert out["verdict"] == "NOT_SCORED"
    assert out["not_scored"] is True
    assert out["termination"] == termination
    assert f"termination={termination}" in out["reason"]
    # `not_scored` is the flag scoring reads; `check_scenario_pass` returns
    # False unconditionally on it (REQ-037 AC-9).
    assert prompt_change_mod.check_scenario_pass(out, _PROMPT_CHANGE_SCENARIO) is False


def test_prompt_change_judge_scores_completed_normally(monkeypatch: pytest.MonkeyPatch) -> None:
    verdict = '{"verdict": "ROUTE", "reason": "ok"}'
    monkeypatch.setattr(prompt_change_mod, "call_api", _fake_call_api("completed", verdict))

    out = prompt_change_mod.judge_scenario("k", "sys", _PROMPT_CHANGE_SCENARIO, "claude")

    assert out["verdict"] == "ROUTE"
    assert out["not_scored"] is False
    assert out["termination"] == "completed"
    assert prompt_change_mod.check_scenario_pass(out, _PROMPT_CHANGE_SCENARIO) is True


@pytest.mark.parametrize("sneaky_expected_verdict", ["ERROR", "NOT_SCORED"])
def test_a_scenario_naming_the_sentinel_as_expected_verdict_cannot_pass_on_refusal(
    monkeypatch: pytest.MonkeyPatch, sneaky_expected_verdict: str
) -> None:
    """A scenario whose `expected_verdict` happens to equal a sentinel
    display label must not pass just because the judge was refused."""
    monkeypatch.setattr(prompt_change_mod, "call_api", _fake_call_api("refusal", "irrelevant"))
    scenario = dict(_PROMPT_CHANGE_SCENARIO, expected_verdict=sneaky_expected_verdict)

    out = prompt_change_mod.judge_scenario("k", "sys", scenario, "claude")

    assert prompt_change_mod.check_scenario_pass(out, scenario) is False


# eval-prompt-change.py: run_scenario_multi excludes not_scored runs (REQ-037)

_NOT_SCORED_AGGREGATION_CASES = [
    pytest.param(
        [
            {"verdict": "ROUTE", "reason": "ok", "not_scored": False},
            {"verdict": "ROUTE", "reason": "ok", "not_scored": False},
            {"verdict": "NOT_SCORED", "reason": "termination=refusal", "not_scored": True},
        ],
        {"passed": True, "runs": 2, "requested_runs": 3, "not_scored_runs": 1, "passes": 2},
        id="one_refused_of_three_with_two_passes_still_passes",
    ),
    pytest.param(
        [{"verdict": "NOT_SCORED", "reason": "termination=refusal", "not_scored": True}] * 3,
        {"passed": False, "runs": 0, "not_scored_runs": 3, "pass_rate": 0.0},
        id="all_three_refused_cannot_pass",
    ),
]


@pytest.mark.parametrize("results, expected", _NOT_SCORED_AGGREGATION_CASES)
def test_run_scenario_multi_excludes_not_scored_runs(
    monkeypatch: pytest.MonkeyPatch, results: list[dict[str, Any]], expected: dict[str, Any]
) -> None:
    results_cycle = itertools.cycle(results)
    monkeypatch.setattr(
        prompt_change_mod, "judge_scenario", lambda *_a, **_kw: dict(next(results_cycle))
    )
    monkeypatch.setattr(prompt_change_mod.time, "sleep", lambda _s: None)

    out = prompt_change_mod.run_scenario_multi("k", "p", _PROMPT_CHANGE_SCENARIO, "m", 3)

    for key, value in expected.items():
        assert out[key] == value, key
