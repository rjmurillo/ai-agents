"""Unreachable executable instructions, found with existing routing evidence.

Issue #5397 maps "dead code" to a skill no one can activate. The routing-role
gate already reads every skill's `metadata.routing` declaration and the
canonical text of every skill and agent (`skill_routing_evidence`). This module
adds no evaluator and no tooling. It walks those same facts as a graph:

    entry points = skills selected without another skill's help: invoker is
                   `user` or `harness`, role is `explicit-only` or `deprecated`
                   (a retirement is declared, not a route), or `intents` is
                   declared (the autoplan resolver selects it by intent);
                   plus every agent's canonical text
    edge A -> B  = A's canonical text names B as an exact token
    unreachable  = a skill no entry point reaches

Counting mentions alone would miss two helpers that name each other with no
entry point (a disconnected cycle), so reachability is transitive.
Fixture tests prove the predicate fires, exempts entry points, follows chains,
catches cycles, and stops firing once a reachable consumer names the skill.
The real-repository test fails when a new skill becomes unreachable.
"""

from __future__ import annotations

import sys
from collections import deque
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_VALIDATION = _REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION) not in sys.path:
    sys.path.insert(0, str(_VALIDATION))

import check_skill_routing_roles as gate
import skill_routing_evidence as evidence_lib
from skill_routing_model import RESERVED_INVOKERS

from tests.validation._skill_routing_fixtures import (
    _agent,
    _routing,
    _skill,
    tree_fixture,  # noqa: F401 (registers the `tree` pytest fixture)
)

_ENTRY_ROLES = frozenset({"explicit-only", "deprecated"})


def _declares_intents(path: Path) -> bool:
    front = gate._frontmatter(path.read_text(encoding="utf-8", errors="replace"))
    metadata = front.get("metadata")
    routing = metadata.get("routing") if isinstance(metadata, dict) else None
    return isinstance(routing, dict) and bool(routing.get("intents"))


def _entry_points(skills: list, templates: dict[str, Path]) -> set[str]:
    return {
        skill.name
        for skill in skills
        if skill.role in _ENTRY_ROLES
        or skill.invoker in RESERVED_INVOKERS
        or _declares_intents(templates[skill.name])
    }


def _named_by(text: str, candidates: set[str]) -> set[str]:
    return {name for name in candidates if evidence_lib._names_token(name, text)}


def unreachable_skills(repo_root: Path) -> list[str]:
    """Skills no entry point reaches through canonical-text mentions."""
    skills, _findings, _evidence = gate.survey(repo_root)
    templates = gate._skill_template_map(repo_root)
    skill_text, agent_text = evidence_lib._canonical_texts(
        repo_root, templates, gate._agent_template_map(repo_root)
    )
    names = {skill.name for skill in skills}
    reached = _entry_points(skills, templates)
    queue = deque(reached)
    for text in agent_text.values():
        for name in _named_by(text, names) - reached:
            reached.add(name)
            queue.append(name)
    while queue:
        for name in _named_by(skill_text[queue.popleft()], names) - reached:
            reached.add(name)
            queue.append(name)
    return sorted(names - reached)


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


def test_deprecated_skill_with_no_references_is_not_flagged(tree: Path) -> None:
    _front_door(tree)
    _skill(
        tree,
        "legacy-tool",
        _routing(
            role="deprecated",
            invoker="autoplan",
            trigger="t",
            user_facing=False,
            replaced_by="autoplan",
            removal_issue=42,
        ),
    )

    assert unreachable_skills(tree) == []


def test_front_door_skill_with_intents_is_reachable_without_a_mention(tree: Path) -> None:
    _front_door(tree)
    _skill(
        tree,
        "invoice-audit",
        _routing(
            role="front-door",
            invoker="autoplan",
            trigger="t",
            user_facing=True,
            intents="[invoice audit]",
        ),
    )

    assert unreachable_skills(tree) == []


def test_helper_named_only_by_an_agent_is_reachable(tree: Path) -> None:
    _front_door(tree)
    _helper(tree)
    _agent(tree, "reviewer", body="Hands off to orphan-helper.")

    assert unreachable_skills(tree) == []


def test_chain_from_an_entry_point_is_reachable(tree: Path) -> None:
    _front_door(tree, body="Routes work, then calls helper-a.")
    _skill(
        tree,
        "helper-a",
        _routing(role="nested-helper", invoker="autoplan", trigger="t", user_facing=False),
        body="Then calls helper-b.",
    )
    _helper(tree, "helper-b")

    assert unreachable_skills(tree) == []


def test_disconnected_cycle_is_unreachable(tree: Path) -> None:
    """Each helper has an inbound mention, yet no entry point reaches either."""
    _front_door(tree)
    for name, other in (("helper-a", "helper-b"), ("helper-b", "helper-a")):
        _skill(
            tree,
            name,
            _routing(role="nested-helper", invoker="autoplan", trigger="t", user_facing=False),
            body=f"Calls {other}.",
        )

    assert unreachable_skills(tree) == ["helper-a", "helper-b"]


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
