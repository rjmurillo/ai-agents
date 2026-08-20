"""Contract tests for the reviewer-findings skill bundle.

Lives under ``tests/`` per ``.claude/rules/testing.md`` MUST 6 ("New tests
MUST live in `tests/` ... Do not add tests to shipped skill directories"),
not inside ``.claude/skills/reviewer-findings/tests/``. A colocated test file
there would be mirrored by ``build/scripts/build_all.py`` into
``src/copilot-cli/skills/reviewer-findings/tests/``, shipping the suite
twice to plugin consumers who never run it
(``scripts/validation/check_colocated_skill_tests.py``, issue #4838).

Each check below is parametrized over both plugin roots that ship
``reviewer-findings`` and ``pr-comment-responder`` (``.claude`` and
``src/copilot-cli``), so this suite still catches a mirroring drift between
the two even though it no longer lives inside either one. The ``plugin_root``
fixture lives in the sibling ``conftest.py``; parsing/lookup helpers live in
the sibling ``_helpers.py`` (split out to keep this file under the
repository's 500-line ceiling).

What these guard: the reviewer-findings SKILL.md description asserts that
pr-comment-responder applies it per finding. That claim is only true because
of an edit to pr-comment-responder, in a different file, that nothing else
in this suite checks by accident. If the route is dropped, the description
becomes false and the skill stops being reachable from the workflow that
needs it.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

# pytest here runs under --import-mode=importlib (pyproject.toml), which never
# inserts a test file's own directory onto sys.path, so a plain
# `import _helpers` cannot resolve. Load the sibling module by file path
# instead, matching the wrapper idiom already used in
# tests/skills/pr-comment-responder/test_cluster_threads.py.
_HELPERS_PATH = Path(__file__).resolve().parent / "_helpers.py"
_helpers_spec = importlib.util.spec_from_file_location(
    "reviewer_findings_test_helpers", _HELPERS_PATH
)
assert _helpers_spec is not None and _helpers_spec.loader is not None
_helpers = importlib.util.module_from_spec(_helpers_spec)
_helpers_spec.loader.exec_module(_helpers)

DISPOSITION_TOKENS = _helpers.DISPOSITION_TOKENS
PLUGIN_ROOTS = _helpers.PLUGIN_ROOTS
REPO_ROOT = _helpers.REPO_ROOT
ROUTER_SKILL = _helpers.ROUTER_SKILL
SKILL_NAME = _helpers.SKILL_NAME
TRIAGE_PHASE = _helpers.TRIAGE_PHASE
VERIFY_PHASE = _helpers.VERIFY_PHASE
_bounded_section = _helpers._bounded_section
_missing_disposition_tokens = _helpers._missing_disposition_tokens
_phase_heading_start = _helpers._phase_heading_start
_phase_section = _helpers._phase_section
_read = _helpers._read
_read_reference = _helpers._read_reference
_routed_skills = _helpers._routed_skills
_row_disposition = _helpers._row_disposition
_skills_dir = _helpers._skills_dir
_workflow_phase_section = _helpers._workflow_phase_section


def test_this_skill_ships_in_its_own_root(plugin_root: Path) -> None:
    """The bundle that carries this suite must also carry its SKILL.md."""
    assert (_skills_dir(plugin_root) / SKILL_NAME / "SKILL.md").is_file(), (
        f"{SKILL_NAME}/SKILL.md is missing from plugin root {plugin_root}, "
        f"so an installed plugin from this root ships without the skill "
        f"this suite tests"
    )


def test_responder_routes_to_this_skill(plugin_root: Path) -> None:
    """pr-comment-responder must invoke this skill, as its description claims."""
    routed = _routed_skills(_read(plugin_root, ROUTER_SKILL))
    assert SKILL_NAME in routed, (
        f"{ROUTER_SKILL} in {plugin_root} no longer routes to {SKILL_NAME}. "
        f"The {SKILL_NAME} description asserts that {ROUTER_SKILL} applies "
        f"it per finding; without the route that claim is false. Routes "
        f"found: {sorted(routed) or 'none'}"
    )


def test_every_route_in_the_responder_resolves_in_this_root(plugin_root: Path) -> None:
    """A route that names a skill absent from this root is a dangling route."""
    routed = _routed_skills(_read(plugin_root, ROUTER_SKILL))
    dangling = sorted(
        name for name in routed if not (_skills_dir(plugin_root) / name / "SKILL.md").is_file()
    )
    assert not dangling, (
        f"{ROUTER_SKILL} routes to skill(s) that do not ship in plugin root "
        f"{plugin_root}: {dangling}. An installed plugin cannot follow a "
        f"route to a skill it does not carry"
    )


def test_every_on_disk_root_shipping_this_skill_is_covered() -> None:
    """Converse guard: PLUGIN_ROOTS is hand-maintained; nothing else checks it
    against reality. Without this, a third mirror could land on disk and stay
    untested forever while this suite stays green (Cursor Bugbot on PR #5178).

    Source of truth for "which plugin roots exist" is the marketplace
    manifests, via the same helper the plugin-self-containment gate uses
    (scripts/validation/check_plugin_frontmatter_self_containment.py), not a
    second hand-rolled filesystem walk.

    ``declared_plugin_roots`` reads its entries verbatim from JSON manifest
    text, so they are forward-slash always (``src/copilot-cli``), whatever
    the host OS. ``PLUGIN_ROOTS.values()`` are ``Path`` objects, and
    ``str(Path)`` renders with ``os.sep``, which is a backslash on Windows;
    comparing the two directly makes this guard fail on Windows for a root
    it actually covers (Cursor Bugbot on PR #5178). ``Path.as_posix()``
    always renders forward-slash, matching the manifest-sourced spelling on
    every platform.
    """
    from scripts.validation.check_plugin_frontmatter_self_containment import (
        plugin_roots as declared_plugin_roots,
    )

    shipping = {
        root
        for root in declared_plugin_roots(REPO_ROOT)
        if (REPO_ROOT / root / "skills" / SKILL_NAME / "SKILL.md").is_file()
    }
    covered = {path.relative_to(REPO_ROOT).as_posix() for path in PLUGIN_ROOTS.values()}
    assert shipping == covered, (
        f"plugin roots shipping {SKILL_NAME} on disk ({sorted(shipping)}) no "
        f"longer match the roots this suite tests ({sorted(covered)}); update "
        f"PLUGIN_ROOTS in _helpers.py to cover the difference"
    )


def test_the_posix_spelling_is_what_makes_the_converse_guard_platform_independent() -> None:
    """Edge: prove str(Path) and Path.as_posix() diverge under a backslash
    separator, the exact divergence that would false-fail the guard above on
    Windows (Cursor Bugbot on PR #5178). Uses PureWindowsPath so the assertion
    does not depend on which OS actually runs the suite.
    """
    from pathlib import PureWindowsPath

    windows_relative = PureWindowsPath("src") / "copilot-cli"
    assert str(windows_relative) == "src\\copilot-cli", (
        "PureWindowsPath did not render with a backslash separator; this "
        "test no longer exercises the platform difference it is named for"
    )
    assert windows_relative.as_posix() == "src/copilot-cli", (
        "as_posix() no longer normalizes a Windows-style path to forward "
        "slashes, so it would no longer match the manifest-sourced spelling "
        "the converse guard compares against"
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


class TestTheRouteFiresWhileTheFindingIsStillBeingTriaged:
    def test_the_route_sits_in_the_triage_phase(self, plugin_root: Path) -> None:
        """Positive: the route is inside the phase that decides what to do."""
        router = _read(plugin_root, ROUTER_SKILL)
        assert SKILL_NAME in _routed_skills(_phase_section(router, TRIAGE_PHASE)), (
            f"{ROUTER_SKILL} in {plugin_root} no longer routes to {SKILL_NAME} "
            f"from Phase {TRIAGE_PHASE}. A route that survives only in a "
            f"later phase verifies the finding after the fix is written, "
            f"which inverts the order this skill exists to enforce"
        )

    def test_the_route_precedes_the_verify_phase(self, plugin_root: Path) -> None:
        """Edge: ordering, not just membership, is what carries the meaning."""
        router = _read(plugin_root, ROUTER_SKILL)
        route = re.search(rf'Skill\(skill="{SKILL_NAME}"\)|skill:\s*"{SKILL_NAME}"', router)
        assert route is not None, (
            f"{ROUTER_SKILL} in {plugin_root} contains no route to {SKILL_NAME}"
        )
        triage = _phase_heading_start(router, TRIAGE_PHASE)
        verify = _phase_heading_start(router, VERIFY_PHASE)
        assert triage < verify, (
            f"Phase {TRIAGE_PHASE} begins after Phase {VERIFY_PHASE} in "
            f"{ROUTER_SKILL} ({plugin_root}), so triage no longer precedes "
            f"verification"
        )
        assert route.start() < verify, (
            f"the {SKILL_NAME} route appears after Phase {VERIFY_PHASE} "
            f"begins in {plugin_root}, so the workflow reaches verification "
            f"before it has verified the finding it acted on"
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
            "a phase heading quoted inside a fenced example was treated as "
            "the real section, so a documentation snippet could satisfy the "
            "route"
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
