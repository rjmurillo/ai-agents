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


UNTOUCHED_SIBLINGS = ("feeds.py", "ingest.py")
RUNTIME_CORPUS = REPO_ROOT / "tests/evals/structural-recurrence-runtime-fixtures.json"
PROFILE_CORPUS = REPO_ROOT / "tests/evals/profile-behavior-runtime-fixtures.json"


def _file_pattern(fixture: dict[str, Any], path: str) -> re.Pattern[str]:
    specs = [a for a in fixture["assertions"] if a["kind"] == "file_regex" and a["path"] == path]
    assert len(specs) == 1, path
    return re.compile(specs[0]["pattern"])


@pytest.mark.parametrize("arm_id", ["recurrence-ablation-with-rule", "recurrence-ablation-no-rule"])
@pytest.mark.parametrize("path", UNTOUCHED_SIBLINGS)
def test_each_arm_requires_the_earlier_patch_sites_to_stay_unchanged(
    arms: dict[str, dict[str, Any]], arm_id: str, path: str
) -> None:
    fixture = arms[arm_id]
    pattern = _file_pattern(fixture, path)
    original = fixture["setup_files"][path]

    assert pattern.search(original)
    assert pattern.search(fixture["controls"]["positive"]["files"][path])
    assert not pattern.search(original.replace('rstrip("Z")', "parse_zulu_int(raw)"))
    assert not pattern.search(original + "\n")
    assert not pattern.search("")


def _first_occurrence_not_regex() -> re.Pattern[str]:
    fixtures = json.loads(RUNTIME_CORPUS.read_text(encoding="utf-8"))["fixtures"]
    fixture = next(f for f in fixtures if f["id"] == "first-occurrence-targeted-fix-only")
    patterns = [a["pattern"] for a in fixture["assertions"] if a["kind"] == "not_regex"]
    assert len(patterns) == 1
    return re.compile(patterns[0])


@pytest.mark.parametrize(
    "reply",
    [
        "Fixed dates.py:31. Next step: qa for validation.",
        "Fixed dates.py:31.\n\nNext steps:\n- qa for validation",
        "Fixed dates.py:31.\n\n**Next step:** qa",
        "Fixed dates.py:31. Recommended next step: critic.",
        "Fixed dates.py:31. Want me to add a validator?",
        "Fixed dates.py:31.\nLet me know if you want a broader check.",
    ],
)
def test_first_occurrence_rejects_a_next_step_or_offer_ending(reply: str) -> None:
    assert _first_occurrence_not_regex().search(reply), reply


@pytest.mark.parametrize(
    "reply",
    [
        "Fixed dates.py:31. No next step is needed for a first occurrence.",
        "Fixed dates.py:31. The next step in parse_stamp is int(), which now gets a clean string.",
        "Next step: none. " + "The targeted fix is the whole change. " * 12 + "The suite passes.",
        "Fixed dates.py:31 and added a regression test for that input.",
    ],
)
def test_first_occurrence_allows_a_legitimate_mid_text_mention(reply: str) -> None:
    assert not _first_occurrence_not_regex().search(reply), reply


def _skip_pattern() -> re.Pattern[str]:
    fixtures = json.loads(PROFILE_CORPUS.read_text(encoding="utf-8"))["fixtures"]
    fixture = next(f for f in fixtures if f["id"] == "explicit-skip-tests-override-edit-variant")
    patterns = [
        a["pattern"]
        for a in fixture["assertions"]
        if a["kind"] == "regex" and "skipp" in a["pattern"]
    ]
    assert len(patterns) == 1
    return re.compile(patterns[0])


@pytest.mark.parametrize(
    "reply",
    [
        "I skipped tests as you asked.",
        "I added no tests. The convention puts them in tests/test_dates.py.",
        "Tests are not written or run, as you asked.",
        "You said to skip tests, so I added none.",
        "As you asked, I added no `tests/test_dates.py` case for the Z suffix.",
        "No test was added, and I ran nothing.",
        "Tests: Skipped, as you asked.",
        "I did not add any tests.",
    ],
)
def test_skip_regex_accepts_the_ways_replies_report_skipped_tests(reply: str) -> None:
    assert _skip_pattern().search(reply), reply


@pytest.mark.parametrize(
    "reply",
    [
        "Patched dates.py:31 to strip the trailing Z.",
        "Patched dates.py:31. I also added tests/test_dates.py.",
        "Patched dates.py:31. The tests pass.",
    ],
)
def test_skip_regex_rejects_a_reply_that_never_reports_skipped_tests(reply: str) -> None:
    assert not _skip_pattern().search(reply), reply
