"""Scenario S2 is graded by the judge alone, with no forbidden patterns.

S2 asks for an analyzer rule page outline on a plain Markdown repository. Two
review cycles showed that a forbidden-claim pattern either caps a correct
rejection ("Don't import X from '@astrojs/starlight/components'") or misses a
hedged real import. The grader excuses a match only when a hedge such as "if"
or "cannot" opens its clause, or when "not" or "never" sits right before it;
"Don't" triggers neither. The owner chose judge-only grading for S2. This test
keeps a pattern from returning without that decision being revisited.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tests.eval.test_eval_rule_activation import eval_mod

SCENARIOS = (
    Path(__file__).resolve().parents[2]
    / "tests"
    / "evals"
    / "skill-scenarios"
    / "technical-writing.json"
)


@pytest.fixture
def s2() -> dict[str, Any]:
    data = json.loads(SCENARIOS.read_text(encoding="utf-8"))
    return next(s for s in data["scenarios"] if s["id"] == "S2")


def test_s2_sets_no_forbidden_patterns(s2: dict[str, Any]) -> None:
    assert "forbidden_response_patterns" not in s2


@pytest.mark.parametrize(
    "response",
    [
        "Don't import { Aside } from '@astrojs/starlight/components'.",
        "import { Aside } from '@astrojs/starlight/components';",
    ],
)
def test_s2_caps_nothing_so_the_judge_decides(s2: dict[str, Any], response: str) -> None:
    assert eval_mod._forbidden_claim_hits(s2, response) == []
