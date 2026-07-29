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


# The router's phases are ordered work. Verification has to happen while the
# finding is being triaged, not after the fix is written, or the skill's whole
# premise ("verify before you fix") is lost while the route still exists.
PHASE_HEADING_RE = re.compile(r"^### Phase (-?\d+)(?![.\d])[^\n]*$", re.MULTILINE)
FENCE_RE = re.compile(
    r"^(?P<fence>```+|~~~+)[^\n]*\n.*?^(?P=fence)[^\n]*$\n?",
    re.MULTILINE | re.DOTALL,
)
TRIAGE_PHASE = "2"
VERIFY_PHASE = "3"


def _blank_fences(text: str) -> str:
    """Blank fenced blocks, preserving offsets so heading positions stay comparable."""
    return FENCE_RE.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), text)


def _phase_headings(text: str) -> list[tuple[str, int, int]]:
    """Return ``(number, heading_start, body_start)`` for each real phase heading."""
    scannable = _blank_fences(text)
    return [(m.group(1), m.start(), m.end()) for m in PHASE_HEADING_RE.finditer(scannable)]


def _phase_heading_start(text: str, phase: str) -> int:
    """Return the offset where ``### Phase N`` begins, failing loudly when absent."""
    for number, start, _ in _phase_headings(text):
        if number == phase:
            return start
    pytest.fail(f"no '### Phase {phase}' heading found outside fenced blocks")


def _phase_section(text: str, phase: str) -> str:
    """Return the body of one ``### Phase N`` section, excluding later phases."""
    starts = _phase_headings(text)
    for index, (number, _, body_start) in enumerate(starts):
        if number != phase:
            continue
        body_end = starts[index + 1][1] if index + 1 < len(starts) else len(text)
        return text[body_start:body_end]
    pytest.fail(f"no '### Phase {phase}' heading found; phases present: "
                f"{[n for n, _, _ in starts] or 'none'}")


class TestTheRouteFiresWhileTheFindingIsStillBeingTriaged:
    def test_the_route_sits_in_the_triage_phase(self) -> None:
        """Positive: the route is inside the phase that decides what to do."""
        router = _read(ROUTER_SKILL)
        assert SKILL_NAME in _routed_skills(_phase_section(router, TRIAGE_PHASE)), (
            f"{ROUTER_SKILL} no longer routes to {SKILL_NAME} from Phase "
            f"{TRIAGE_PHASE}. A route that survives only in a later phase "
            f"verifies the finding after the fix is written, which inverts "
            f"the order this skill exists to enforce"
        )

    def test_the_route_precedes_the_verify_phase(self) -> None:
        """Edge: ordering, not just membership, is what carries the meaning."""
        router = _read(ROUTER_SKILL)
        route = re.search(rf'Skill\(skill="{SKILL_NAME}"\)|skill:\s*"{SKILL_NAME}"', router)
        assert route is not None, f"{ROUTER_SKILL} contains no route to {SKILL_NAME}"
        triage = _phase_heading_start(router, TRIAGE_PHASE)
        verify = _phase_heading_start(router, VERIFY_PHASE)
        assert triage < verify, (
            f"Phase {TRIAGE_PHASE} begins after Phase {VERIFY_PHASE} in "
            f"{ROUTER_SKILL}, so triage no longer precedes verification"
        )
        assert route.start() < verify, (
            f"the {SKILL_NAME} route appears after Phase {VERIFY_PHASE} begins, "
            f"so the workflow reaches verification before it has verified the "
            f"finding it acted on"
        )

    def test_the_phase_slice_excludes_other_phases(self) -> None:
        """Negative control: prove the slice is a slice, not the whole file."""
        synthetic = (
            "### Phase 2: Triage and Delegate\n"
            "Nothing routes here.\n"
            "### Phase 3: Verify\n"
            'Run `Skill(skill="some-later-skill")` now.\n'
        )
        assert _routed_skills(_phase_section(synthetic, TRIAGE_PHASE)) == set(), (
            "the phase slice leaked a later phase's route, so the positive "
            "assertion above would pass for a route in any phase at all"
        )

    def test_a_heading_inside_a_fenced_block_is_not_a_phase(self) -> None:
        """Negative control: illustrative markdown must not stand in for structure."""
        synthetic = (
            "```markdown\n"
            "### Phase 2: Triage and Delegate\n"
            f'Run `Skill(skill="{SKILL_NAME}")`.\n'
            "```\n"
            "### Phase 2: Triage and Delegate\n"
            "Nothing routes here.\n"
            "### Phase 3: Verify\n"
        )
        assert _routed_skills(_phase_section(synthetic, TRIAGE_PHASE)) == set(), (
            "a phase heading quoted inside a fenced example was treated as the "
            "real section, so a documentation snippet could satisfy the route"
        )

    def test_a_subphase_heading_is_not_its_parent_phase(self) -> None:
        """Negative control: 'Phase 2.1' is a different section from 'Phase 2'."""
        synthetic = (
            "### Phase 2.1: Not the triage phase\n"
            f'Run `Skill(skill="{SKILL_NAME}")`.\n'
            "### Phase 2: Triage and Delegate\n"
            "Nothing routes here.\n"
            "### Phase 3: Verify\n"
        )
        assert _routed_skills(_phase_section(synthetic, TRIAGE_PHASE)) == set(), (
            "'### Phase 2.1' was captured as phase 2, so a route in any "
            "sub-numbered section would satisfy the triage assertion"
        )

    def test_the_ordering_check_compares_the_two_phase_headings(self) -> None:
        """Negative control: a stray early mention must not stand in for Phase 2."""
        synthetic = (
            f'Mentioned early: `Skill(skill="{SKILL_NAME}")`.\n'
            "### Phase 3: Verify\n"
            "### Phase 2: Triage and Delegate\n"
        )
        triage = _phase_heading_start(synthetic, TRIAGE_PHASE)
        verify = _phase_heading_start(synthetic, VERIFY_PHASE)
        assert triage > verify, (
            "the heading offsets no longer reflect document order, so the "
            "ordering assertion could not detect a swapped Phase 2 and Phase 3"
        )
