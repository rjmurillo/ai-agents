"""Unreachable executable instructions, found with existing routing evidence.

Issue #5397 maps "dead code" to a skill no one can activate. The routing-role
gate already computes `inbound_zero` (no skill or agent text names the skill)
and declares who may select each skill (`role`, `invoker`). This module adds
no evaluator. It composes those two facts into one predicate and pins it:

    unreachable = inbound-zero AND not selected by the user or harness by
                  declaration (invoker in RESERVED_INVOKERS, or role explicit-only)

Fixture tests prove the predicate fires, exempts declared entry points, and
stops firing once a consumer names the skill (the negative control). The real
repository test fails when a new skill becomes unreachable.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_VALIDATION = _REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION) not in sys.path:
    sys.path.insert(0, str(_VALIDATION))

import check_skill_routing_roles as gate
from skill_routing_model import RESERVED_INVOKERS

from tests.validation._skill_routing_fixtures import (
    _routing,
    _skill,
    tree_fixture,  # noqa: F401 (registers the `tree` pytest fixture)
)


def unreachable_skills(repo_root: Path) -> list[str]:
    """Skills no text names and no declaration makes user or harness selectable."""
    skills, _findings, evidence = gate.survey(repo_root)
    by_name = {skill.name: skill for skill in skills}
    return sorted(
        name
        for name in evidence.inbound_zero
        if by_name[name].role != "explicit-only" and by_name[name].invoker not in RESERVED_INVOKERS
    )


def _front_door(tree: Path, body: str = "Routes work.") -> None:
    _skill(
        tree,
        "autoplan",
        _routing(role="front-door", invoker="harness", trigger="t", user_facing=True),
        body=body,
    )


def _helper(tree: Path, name: str = "orphan-helper") -> None:
    _skill(
        tree,
        name,
        _routing(role="nested-helper", invoker="autoplan", trigger="t", user_facing=False),
        body="A helper nobody names.",
    )


def test_skill_named_by_no_consumer_is_unreachable(tree: Path) -> None:
    _front_door(tree)
    _helper(tree)

    assert unreachable_skills(tree) == ["orphan-helper"]


def test_consumer_naming_the_skill_clears_it(tree: Path) -> None:
    """Negative control: the same skill stops being flagged once named."""
    _front_door(tree, body="Routes work, then calls orphan-helper.")
    _helper(tree)

    assert unreachable_skills(tree) == []


def test_explicit_only_skill_is_a_declared_entry_point(tree: Path) -> None:
    _front_door(tree)
    _skill(
        tree,
        "user-tool",
        _routing(
            role="explicit-only",
            invoker="user",
            trigger="t",
            user_facing=True,
            rationale="Reachable only by direct user request.",
        ),
    )

    assert unreachable_skills(tree) == []


def test_explicit_only_role_alone_exempts_a_skill(tree: Path) -> None:
    """The role clause is load-bearing even when the invoker is not reserved."""
    _front_door(tree)
    _skill(
        tree,
        "role-only",
        _routing(
            role="explicit-only",
            invoker="autoplan",
            trigger="t",
            user_facing=True,
            rationale="Deliberately never auto-selected.",
        ),
    )

    assert unreachable_skills(tree) == []


def test_harness_invoked_skill_is_a_declared_entry_point(tree: Path) -> None:
    _front_door(tree)

    assert unreachable_skills(tree) == []


def test_multiple_unreachable_skills_are_all_listed_sorted(tree: Path) -> None:
    _front_door(tree)
    _helper(tree, "zeta-helper")
    _helper(tree, "alpha-helper")

    assert unreachable_skills(tree) == ["alpha-helper", "zeta-helper"]


def test_empty_tree_is_a_config_error_not_a_clean_result(tmp_path: Path) -> None:
    with pytest.raises(gate.TreeError):
        unreachable_skills(tmp_path)


def test_real_repository_has_no_unreachable_skill() -> None:
    """Fails when a new skill is neither named by a consumer nor a declared entry point."""
    assert unreachable_skills(_REPO_ROOT) == []
