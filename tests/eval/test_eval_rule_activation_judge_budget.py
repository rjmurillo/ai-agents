"""Judge token budget and partial judge loss in eval-rule-activation.py (#7061).

The judge inherited the transport's 1024 output-token default, a verbose
reasoning string was cut mid-JSON, and the one truncated sample failed the
whole run as FAIL_JUDGE_ERRORS. These tests pin the explicit budget, the retry
on `token_limit`, and the verdict rule: a gating cell that still graded some
samples is a caveat, a gating cell that graded none fails closed. No model is
called.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.eval.test_eval_rule_activation import eval_mod

SCENARIO = {"input": "x", "expected_gate": "apply-rule"}
GOOD_JSON = '{"activation_score": 5, "citation_score": 5, "behavior_score": 5, "reasoning": "ok"}'
CUT_JSON = '{"activation_score": 5, "citation_score": 5, "behavior_score": 5, "reasoning": "cut'


def _fake_judge(monkeypatch: pytest.MonkeyPatch, replies: dict[int, tuple[str, str]]) -> list[int]:
    """Answer each judge call by its budget: {max_tokens: (text, termination)}."""
    budgets: list[int] = []

    def fake_call_api(*_args: object, **kwargs: Any) -> str:
        budget = kwargs["max_tokens"]
        budgets.append(budget)
        text, termination = replies[budget]
        kwargs["metadata"]["termination"] = termination
        return text

    monkeypatch.setattr(eval_mod, "_call_api", fake_call_api)
    monkeypatch.setattr(eval_mod, "RATE_LIMIT_SLEEP_SEC", 0)
    return budgets


def _sample(score: int | None) -> dict[str, Any]:
    if score is None:
        return {"judge_failed": True, "termination": "token_limit"}
    return {
        "activation_score": score,
        "citation_score": score,
        "behavior_score": score,
        "judge_failed": False,
    }


def _cell(*scores: int | None) -> dict[str, Any]:
    samples = [_sample(score) for score in scores]
    return {"scores": eval_mod._reduce_score_samples(samples, "median")}


def _run(description: dict[str, Any]) -> list[dict[str, Any]]:
    """A run that passes on its scores, with the positive description cell given."""
    return [
        {
            "negative_case": False,
            "mechanisms": {
                "baseline": _cell(1, 1, 1),
                "description": description,
                "full": _cell(5, 5, 5),
            },
        },
        {
            "negative_case": True,
            "mechanisms": {m: _cell(5, 5, 5) for m in eval_mod.MECHANISMS},
        },
    ]


class TestJudgeBudget:
    def test_judge_call_passes_an_explicit_budget_above_the_shared_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        budgets = _fake_judge(
            monkeypatch, {eval_mod.JUDGE_TOKEN_BUDGETS[0]: (GOOD_JSON, "completed")}
        )

        result = eval_mod.score_response("sk-test", SCENARIO, "response")

        assert budgets == [eval_mod.JUDGE_TOKEN_BUDGETS[0]]
        assert budgets[0] > 1024
        assert result["judge_failed"] is False

    def test_budgets_ascend_and_fit_the_evidence_limit(self) -> None:
        budgets = eval_mod.JUDGE_TOKEN_BUDGETS

        assert len(budgets) >= 2
        assert list(budgets) == sorted(set(budgets))
        assert budgets[-1] * 4 <= eval_mod.MAX_JUDGE_EVIDENCE_CHARS


class TestTruncationRetry:
    def test_token_limit_on_first_budget_is_replaced_by_the_retry(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        first, second = eval_mod.JUDGE_TOKEN_BUDGETS[:2]
        budgets = _fake_judge(
            monkeypatch, {first: (CUT_JSON, "token_limit"), second: (GOOD_JSON, "completed")}
        )

        sample = eval_mod._score_judge_sample("sk-test", SCENARIO, "response", "m", None, 0)

        assert budgets == [first, second]
        assert sample["judge_failed"] is False
        assert sample["activation_score"] == 5
        assert sample["judge_max_tokens"] == second
        assert [cut["judge_max_tokens"] for cut in sample["truncated_attempts"]] == [first]
        assert sample["truncated_attempts"][0]["termination"] == "token_limit"

    def test_token_limit_at_every_budget_fails_the_sample(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        budgets = _fake_judge(
            monkeypatch, {b: (CUT_JSON, "token_limit") for b in eval_mod.JUDGE_TOKEN_BUDGETS}
        )

        sample = eval_mod._score_judge_sample("sk-test", SCENARIO, "response", "m", None, 2)

        assert budgets == list(eval_mod.JUDGE_TOKEN_BUDGETS)
        assert sample["judge_failed"] is True
        assert sample["termination"] == "token_limit"
        assert sample["sample_index"] == 2
        assert len(sample["truncated_attempts"]) == len(eval_mod.JUDGE_TOKEN_BUDGETS) - 1
        assert all(cut is not sample for cut in sample["truncated_attempts"])

    @pytest.mark.parametrize(
        ("text", "termination"),
        [("I will not score this.", "refusal"), ("not json", "completed")],
    )
    def test_refusal_and_parse_failure_are_not_retried(
        self, monkeypatch: pytest.MonkeyPatch, text: str, termination: str
    ) -> None:
        budgets = _fake_judge(
            monkeypatch, {b: (text, termination) for b in eval_mod.JUDGE_TOKEN_BUDGETS}
        )

        sample = eval_mod._score_judge_sample("sk-test", SCENARIO, "response", "m", None, 0)

        assert budgets == [eval_mod.JUDGE_TOKEN_BUDGETS[0]]
        assert sample["judge_failed"] is True
        assert "truncated_attempts" not in sample

    def test_clean_first_answer_records_no_truncation(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _fake_judge(monkeypatch, {eval_mod.JUDGE_TOKEN_BUDGETS[0]: (GOOD_JSON, "completed")})

        sample = eval_mod._score_judge_sample("sk-test", SCENARIO, "response", "m", None, 0)

        assert sample["judge_failed"] is False
        assert "truncated_attempts" not in sample


class TestPartialJudgeLossVerdict:
    def test_control_run_passes_with_every_sample_graded(self) -> None:
        summary = eval_mod.aggregate(_run(_cell(5, 5, 5)))

        assert summary["verdict"] == "PASS"
        assert summary["partial_judge_failure_cells"] == 0

    def test_one_failed_sample_with_graded_samples_left_is_a_caveat(self) -> None:
        summary = eval_mod.aggregate(_run(_cell(5, None, 5)))

        assert summary["verdict"] == "PASS"
        assert summary["total_judge_failures"] == 1
        assert summary["gating_judge_failures"] == 0
        assert summary["partial_judge_failure_cells"] == 1
        caveats = eval_mod._render_caveats(summary)
        assert any(line.startswith("Incomplete measurement: 1 gating cell") for line in caveats)
        assert not any(line.startswith("Judge failures:") for line in caveats)

    def test_token_limit_exhausting_a_cell_fails_closed(self) -> None:
        summary = eval_mod.aggregate(_run(_cell(None, None, None)))

        assert summary["verdict"] == "FAIL_JUDGE_ERRORS"
        assert summary["gating_judge_failures"] == 1
        assert summary["partial_judge_failure_cells"] == 0

    def test_failed_cell_without_sample_counts_fails_closed(self) -> None:
        legacy = {
            "scores": {
                "activation_score": 5,
                "citation_score": 5,
                "behavior_score": 5,
                "judge_failed": True,
            }
        }

        summary = eval_mod.aggregate(_run(legacy))

        assert summary["verdict"] == "FAIL_JUDGE_ERRORS"

    @pytest.mark.parametrize("count", [0, True, "2", None])
    def test_graded_sample_count_must_be_a_positive_int(self, count: object) -> None:
        cell = _cell(5, None, 5)
        cell["scores"]["graded_sample_count"] = count

        assert eval_mod.aggregate(_run(cell))["verdict"] == "FAIL_JUDGE_ERRORS"


class TestSelectedRunPartialJudgeLoss:
    @staticmethod
    def _repeats(cell: dict[str, Any]) -> list[dict[str, Any]]:
        return [{"id": "S1", "negative_case": False, "mechanisms": {"description": cell}}]

    def test_partial_loss_is_measured(self) -> None:
        summary = eval_mod._selected_summary(self._repeats(_cell(5, None, 5)), ("description",))

        assert summary["verdict"] == "NOT_GATED"
        assert summary["per_arm"]["description"]["judge_failures"] == 1

    def test_cell_with_no_graded_sample_is_incomplete(self) -> None:
        summary = eval_mod._selected_summary(
            self._repeats(_cell(None, None, None)), ("description",)
        )

        assert summary["verdict"] == "NOT_GATED_INCOMPLETE"
