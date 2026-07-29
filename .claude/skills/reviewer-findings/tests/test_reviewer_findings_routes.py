"""Contract tests for the reviewer-findings skill bundle.

Root-local by design. Each plugin root ships its own copy of this suite and
asserts only about files inside that same root, so the bundle stays
self-contained when the plugin is installed away from this repository. No
assertion here reaches across plugin roots or into the repository tree.

What these guard: the reviewer-findings SKILL.md description asserts that
pr-comment-responder applies it per finding. That claim is only true because
of an edit to pr-comment-responder, in a different file, that nothing else
in this root checks. If the route is dropped, the description becomes false
and the skill stops being reachable from the workflow that needs it.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

SKILL_NAME = "reviewer-findings"
ROUTER_SKILL = "pr-comment-responder"

# tests/ -> reviewer-findings/ -> skills/ -> <plugin root>
PLUGIN_ROOT = Path(__file__).resolve().parents[3]
SKILLS_DIR = PLUGIN_ROOT / "skills"

# Claude roots invoke a skill as Skill(skill="name"). The Copilot body
# translation rewrites that same call to skill: "name". Both forms appear
# inline inside backticks, so neither is anchored to the line start.
ROUTE_PATTERNS = (
    re.compile(r'Skill\(skill="([a-z0-9][a-z0-9-]*)"\)'),
    re.compile(r'skill:\s*"([a-z0-9][a-z0-9-]*)"'),
)


def _read(skill: str) -> str:
    path = SKILLS_DIR / skill / "SKILL.md"
    if not path.is_file():
        pytest.fail(f"{skill}/SKILL.md is missing from plugin root {PLUGIN_ROOT}")
    return path.read_text(encoding="utf-8")


def _routed_skills(text: str) -> set[str]:
    """Return every skill name invoked as a route in ``text``."""
    found: set[str] = set()
    for pattern in ROUTE_PATTERNS:
        found.update(pattern.findall(text))
    return found


def test_this_skill_ships_in_its_own_root() -> None:
    """The bundle that carries this suite must also carry its SKILL.md."""
    assert (SKILLS_DIR / SKILL_NAME / "SKILL.md").is_file(), (
        f"{SKILL_NAME}/SKILL.md is missing from plugin root {PLUGIN_ROOT}, "
        f"so this test suite ships without the skill it tests"
    )


def test_responder_routes_to_this_skill() -> None:
    """pr-comment-responder must invoke this skill, as its description claims."""
    routed = _routed_skills(_read(ROUTER_SKILL))
    assert SKILL_NAME in routed, (
        f"{ROUTER_SKILL} no longer routes to {SKILL_NAME}. The "
        f"{SKILL_NAME} description asserts that {ROUTER_SKILL} applies it "
        f"per finding; without the route that claim is false. Routes found: "
        f"{sorted(routed) or 'none'}"
    )


def test_every_route_in_the_responder_resolves_in_this_root() -> None:
    """A route that names a skill absent from this root is a dangling route."""
    routed = _routed_skills(_read(ROUTER_SKILL))
    dangling = sorted(
        name for name in routed if not (SKILLS_DIR / name / "SKILL.md").is_file()
    )
    assert not dangling, (
        f"{ROUTER_SKILL} routes to skill(s) that do not ship in plugin root "
        f"{PLUGIN_ROOT}: {dangling}. An installed plugin cannot follow a route "
        f"to a skill it does not carry"
    )


def test_route_patterns_reject_a_non_route_mention() -> None:
    """Negative control: prose naming the skill is not counted as a route."""
    prose = (
        f"See the {SKILL_NAME} skill for the three-claims split, and the "
        f"{ROUTER_SKILL} skill for where it fires."
    )
    assert _routed_skills(prose) == set(), (
        "route detection matched plain prose, so the routing assertions above "
        "would pass on a file that contains no route at all"
    )
