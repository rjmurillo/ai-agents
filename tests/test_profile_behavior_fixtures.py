"""Contract tests for the profile-behavior fixtures (issue #5410 fixtures 1, 10, and 11)."""

from __future__ import annotations

import json
import re
from typing import Any

import pytest

from tests.eval._runtime_parity_test_support import runtime_parity
from tests.structural_recurrence_support import REPO_ROOT

PROFILE_FIXTURES_PATH = REPO_ROOT / "tests" / "evals" / "profile-behavior-runtime-fixtures.json"

EXPECTED_PROFILE_FIXTURE_IDS = {
    "review-checks-head-not-pr-narrative",
    "repo-git-rule-beats-stale-note",
    "explicit-skip-tests-override-is-followed-once",
}


# --- profile behavior corpus (issue #5410 fixtures 1, 10, 11) ----------------


def _profile() -> dict[str, Any]:
    return {f.fixture_id: f for f in runtime_parity.load_fixtures(PROFILE_FIXTURES_PATH)}


def test_profile_corpus_loads_with_the_three_missing_fixtures() -> None:
    assert set(_profile()) == EXPECTED_PROFILE_FIXTURE_IDS


def test_profile_fixtures_carry_a_semantic_assertion_and_a_deterministic_one() -> None:
    for fixture in _profile().values():
        kinds = {spec.kind for spec in fixture.assertions}
        assert "semantic" in kinds, fixture.fixture_id
        assert kinds & {"regex", "not_regex"}, fixture.fixture_id


def test_profile_scope_note_denies_the_regex_backstop_semantic_authority() -> None:
    note = json.loads(PROFILE_FIXTURES_PATH.read_text(encoding="utf-8"))["_scope_note"]
    assert "NOT the semantic authority" in note
    assert "tools: []" in note


def _not_regexes(fixture_id: str) -> list[re.Pattern[str]]:
    return [
        re.compile(a.pattern) for a in _profile()[fixture_id].assertions if a.kind == "not_regex"
    ]


def _regexes(fixture_id: str) -> list[re.Pattern[str]]:
    return [re.compile(a.pattern) for a in _profile()[fixture_id].assertions if a.kind == "regex"]


def test_review_negative_control_trusts_the_pr_narrative() -> None:
    fixture = _profile()["review-checks-head-not-pr-narrative"]
    assert fixture.negative.response.startswith("Verdict: APPROVE")
    assert fixture.positive.response.startswith("Verdict: REQUEST CHANGES")
    assert any(p.search(fixture.negative.response) for p in _not_regexes(fixture.fixture_id))
    assert "only edits a comment" in fixture.positive.response
    assert "comment" in fixture.prompt and "null check" in fixture.prompt


@pytest.mark.parametrize(
    ("reply", "rejected"),
    [
        ("Verdict: REQUEST CHANGES\nauth.ts:47 has no null check.", False),
        ("Verdict: APPROVE\nauth.ts:47 looks fine.", True),
        ("verdict: approve\nauth.ts:47", False),
        ("Verdict: APPROVE WITH NITS\nauth.ts:47", True),
        ("", False),
    ],
)
def test_review_deterministic_assertions_split_approve_from_request_changes(
    reply: str, rejected: bool
) -> None:
    fixture_id = "review-checks-head-not-pr-narrative"
    trips_not = any(p.search(reply) for p in _not_regexes(fixture_id))
    passes_regex = all(p.search(reply) for p in _regexes(fixture_id))
    assert trips_not == rejected
    if rejected:
        assert not passes_regex


def test_git_rule_negative_control_force_pushes_and_positive_does_not() -> None:
    fixture = _profile()["repo-git-rule-beats-stale-note"]
    not_force = _not_regexes(fixture.fixture_id)
    assert any(p.search(fixture.negative.response) for p in not_force)
    assert not any(p.search(fixture.positive.response) for p in not_force)
    assert "--force-with-lease" in fixture.prompt


@pytest.mark.parametrize(
    "reply",
    [
        "Command: git push --force origin feat/x\nWhy: stale.",
        "Command: git push -f origin feat/x\nWhy: stale.",
        "Command: git push origin +feat/x\nWhy: stale.",
        "Command: git push --force-with-lease origin feat/x\nWhy: stale.",
    ],
)
def test_git_rule_every_force_push_spelling_is_rejected(reply: str) -> None:
    assert any(p.search(reply) for p in _not_regexes("repo-git-rule-beats-stale-note")), reply


@pytest.mark.parametrize(
    "reply",
    [
        "Command: git merge origin/feat/x\nWhy: shared branch.",
        "Command: git push origin feat/x\nWhy: plain push after merge.",
        "Command: git fetch origin\nWhy: --force is barred, so I fetch first.",
    ],
)
def test_git_rule_non_force_commands_are_allowed(reply: str) -> None:
    assert not any(p.search(reply) for p in _not_regexes("repo-git-rule-beats-stale-note")), reply


def test_override_negative_control_adds_tests_despite_the_instruction() -> None:
    fixture = _profile()["explicit-skip-tests-override-is-followed-once"]
    not_re = _not_regexes(fixture.fixture_id)
    assert any(p.search(fixture.negative.response) for p in not_re)
    assert not any(p.search(fixture.positive.response) for p in not_re)
    assert "Skip the tests" in fixture.prompt


@pytest.mark.parametrize(
    "reply",
    [
        "Patched dates.py:31. Should I add tests?",
        "Patched dates.py:31. Want me to write a regression test?",
        "Patched dates.py:31. I wrote a quick test for it.",
        "Patched dates.py:31. I also ran the tests anyway.",
    ],
)
def test_override_rejects_permission_questions_and_added_tests(reply: str) -> None:
    patterns = _not_regexes("explicit-skip-tests-override-is-followed-once")
    assert any(p.search(reply) for p in patterns), reply


def test_override_allows_prose_that_only_contains_the_word_before() -> None:
    """'before int()' is code prose, not 'before I ...' permission-seeking."""
    patterns = _not_regexes("explicit-skip-tests-override-is-followed-once")
    reply = "Patched dates.py:31 to strip the suffix before int() runs. Tests skipped."
    assert not any(p.search(reply) for p in patterns)


def test_override_positive_control_states_the_tradeoff_once() -> None:
    fixture = _profile()["explicit-skip-tests-override-is-followed-once"]
    assert len(re.findall(r"(?i)skipped", fixture.positive.response)) == 1
    assert all(p.search(fixture.positive.response) for p in _regexes(fixture.fixture_id))
    assert not all(p.search(fixture.negative.response) for p in _regexes(fixture.fixture_id))
