#!/usr/bin/env python3
"""
Regression tests for skillforge domain classification (issue #6647).

classify_domain must not scan the whole SKILL.md body. A meta-skill that
mentions testing in an example is not a testing skill.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[3] / ".claude" / "skills" / "skillforge" / "scripts"
_SAVED_SYS_PATH = list(sys.path)
sys.path.insert(0, str(SCRIPTS_DIR))
import discover_skills

sys.path[:] = _SAVED_SYS_PATH


def test_name_hit_assigns_domain() -> None:
    domains = discover_skills.classify_domain("webapp-testing", "Toolkit for web apps.", [])

    assert "testing" in domains


def test_description_needs_two_distinct_terms() -> None:
    one = discover_skills.classify_domain("alpha", "Runs a test against a service.", [])
    two = discover_skills.classify_domain("alpha", "Runs a test with pytest and jest.", [])

    assert "testing" not in one
    assert "testing" in two


def test_meta_skill_is_not_indexed_under_domains_it_only_mentions() -> None:
    description = (
        "Create new skills, modify and improve existing skills, and measure skill "
        "performance. Use when users want to run evals to test a skill."
    )

    domains = discover_skills.classify_domain("skill-creator", description, ["skill-creator"])

    assert "testing" not in domains
    assert "deployment" not in domains
    assert "database" not in domains


def test_terms_inside_other_words_do_not_count() -> None:
    domains = discover_skills.classify_domain(
        "social-planner", "Plan social media posts for a campaign.", ["social", "media"]
    )

    assert "devops" not in domains
    assert domains == ["general"]


def test_keywords_contribute_to_the_score() -> None:
    domains = discover_skills.classify_domain("alpha", "Does a thing.", ["pytest", "jest"])

    assert "testing" in domains


def test_no_signal_falls_back_to_general() -> None:
    assert discover_skills.classify_domain("alpha", "", []) == ["general"]


@pytest.mark.parametrize("name", ["", "-", "_"])
def test_degenerate_names_do_not_crash(name: str) -> None:
    assert discover_skills.classify_domain(name, "", []) == ["general"]


def test_doubled_consonant_form_in_a_name_assigns_domain() -> None:
    domains = discover_skills.classify_domain("ai-agents-debugging-playbook", "x", [])

    assert "debugging" in domains


@pytest.mark.parametrize(
    ("text", "term", "expected"),
    [
        ("debugging a crash", "debug", True),
        ("debugged it", "debug", True),
        ("debugs", "debug", True),
        ("shipping the release", "ship", True),
        ("shipped", "ship", True),
        ("tests and testing", "test", True),
        # Negative: other words that merely start with the term.
        ("debugger", "debug", False),
        ("attest the claim", "test", False),
        ("shippers", "ship", False),
        # Negative: a vowel never doubles, a different letter never doubles.
        ("deployying", "deploy", False),
        ("debugking", "debug", False),
        # Edge: empty term and empty text.
        ("anything", "", False),
        ("", "debug", False),
        # Edge: multi-word term takes the inflection on its last word.
        ("reading a stack traces", "stack trace", True),
    ],
)
def test_has_term_allows_inflection_and_doubled_consonant(
    text: str, term: str, expected: bool
) -> None:
    assert discover_skills._has_term(text, term) is expected
