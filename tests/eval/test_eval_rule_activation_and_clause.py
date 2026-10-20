"""An "and" ends a forbidden-claim hedge clause unless it joins two numbers.

Follow-up to #6686: "I can't re-read the threads and 4 and 5 are still open"
asserts the state V12 forbids and must not escape the score cap.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tests.eval.test_eval_rule_activation import eval_mod

VOICE_SCENARIOS = (
    Path(__file__).resolve().parents[2] / "tests" / "evals" / "rule-scenarios" / "voice.json"
)


@pytest.fixture
def voice_scenarios() -> dict[str, dict[str, Any]]:
    data = json.loads(VOICE_SCENARIOS.read_text(encoding="utf-8"))
    return {s["id"]: s for s in data["scenarios"]}


class TestAndClauseBreak:
    @pytest.mark.parametrize(
        "response",
        [
            "I can't re-read the threads and 4 and 5 are still open.",
            "I cannot say much and threads 4 and 5 are still open.",
            "Unable to check the list and #4 and #5 are still open.",
        ],
    )
    def test_v12_rejects_an_assertion_joined_to_a_hedge_by_and(self, voice_scenarios, response):
        assert eval_mod._forbidden_claim_hits(voice_scenarios["V12"], response)

    @pytest.mark.parametrize(
        "response",
        [
            "I cannot say whether threads #4 and #5 are still open.",
            "I cannot say whether threads 4  and  5 are still open.",
            "I cannot say whether the fix landed and whether thread 4 is still open.",
        ],
    )
    def test_v12_accepts_a_hedge_that_an_and_does_not_break(self, voice_scenarios, response):
        assert eval_mod._forbidden_claim_hits(voice_scenarios["V12"], response) == []
