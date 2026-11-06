"""The recurrence ablation pair varies one thing: code-quality.md (issue #5410).

The earlier control ran the implementer agent, whose prompt asks for tests, so
both arms wrote tests and the pair could not separate. These tests pin what
keeps this pair able to fail.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
CORPUS = REPO_ROOT / "tests/evals/structural-recurrence-ablation-fixtures.json"
AGENT = "tests/evals/agents/neutral-editor.md"
RULE = ".claude/rules/code-quality.md"
VOICE = ".claude/rules/voice.md"


@pytest.fixture(scope="module")
def arms() -> dict[str, dict[str, Any]]:
    fixtures = json.loads(CORPUS.read_text(encoding="utf-8"))["fixtures"]
    return {fixture["id"]: fixture for fixture in fixtures}


def test_the_corpus_holds_exactly_the_two_arms(arms: dict[str, dict[str, Any]]) -> None:
    assert set(arms) == {"recurrence-ablation-with-rule", "recurrence-ablation-no-rule"}


def test_the_arms_differ_only_in_id_and_the_rule(arms: dict[str, dict[str, Any]]) -> None:
    with_rule = dict(arms["recurrence-ablation-with-rule"])
    no_rule = dict(arms["recurrence-ablation-no-rule"])

    assert sorted(with_rule.pop("instructions")) == sorted([RULE, VOICE])
    assert no_rule.pop("instructions") == [VOICE]
    with_rule.pop("id")
    no_rule.pop("id")
    assert with_rule == no_rule


@pytest.mark.parametrize("arm_id", ["recurrence-ablation-with-rule", "recurrence-ablation-no-rule"])
def test_each_arm_runs_the_neutral_agent(arms: dict[str, dict[str, Any]], arm_id: str) -> None:
    assert arms[arm_id]["agents"] == {"claude": AGENT, "copilot": AGENT}


def test_the_neutral_agent_carries_no_test_guidance() -> None:
    body = (REPO_ROOT / AGENT).read_text(encoding="utf-8")

    assert not re.search(r"(?i)\b(tests?|guard|validator|regression)\b", body)


def test_the_prompt_names_the_recurrence_but_not_the_test_convention(
    arms: dict[str, dict[str, Any]],
) -> None:
    prompt = arms["recurrence-ablation-no-rule"]["prompt"]

    assert "feeds.py:12" in prompt
    assert "ingest.py:88" in prompt
    assert not re.search(r"(?i)\btests?\b", prompt)


def test_no_assertion_pins_a_test_file_name(arms: dict[str, dict[str, Any]]) -> None:
    for fixture in arms.values():
        paths = [item.get("path") or "" for item in fixture["assertions"]]
        assert not [path for path in paths if "test" in path]
