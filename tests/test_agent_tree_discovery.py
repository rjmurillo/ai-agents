"""Guards on the agent-tree roster itself (issue #5130).

The converse-guard family: the configured roster must match what is on disk,
and discovery must not depend on the field the migration guards validate. Every
test here exists because a review found the previous version blind in exactly
the case it was written to catch.

Split from `test_agent_role_metadata_migration.py` at the 500-line ceiling.
"""

from __future__ import annotations

from tests.agent_metadata_helpers import (
    _AGENT_FILE_SUFFIXES,
    _AGENT_TREES,
    _NON_AGENT_ROLE_DIRS,
    _REPO_ROOT,
    _agent_definitions,
    _declares_agent_metadata,
    _discover_agent_trees,
    _frontmatter,
    _looks_like_an_agent_file,
)


def test_agent_trees_are_discovered():
    """Negative control: if the globs stop matching, the guards below are vacuous."""
    assert len(_agent_definitions()) > 100


def test_every_configured_tree_exists():
    """A typo in the roster is silently skipped by `is_dir()`, so name it here.

    Without this, renaming a tree on disk turns its guard into a no-op that
    still reports green.
    """
    missing = [tree for tree in _AGENT_TREES if not (_REPO_ROOT / tree).is_dir()]
    assert not missing, f"configured trees that do not exist on disk: {missing}"


def test_every_on_disk_agent_tree_is_configured():
    """Converse guard: the roster must cover what is actually on disk.

    A roster only proves things about trees someone remembered to add. A
    seventh tree added tomorrow would carry `tier:` past every other check in
    this file. Raised by Cursor Bugbot on PR #5177 against the learned rule
    that a configuration-set test needs a converse guard.
    """
    unconfigured = _discover_agent_trees() - set(_AGENT_TREES) - _NON_AGENT_ROLE_DIRS
    assert not unconfigured, (
        "agent frontmatter found in unconfigured trees: "
        f"{sorted(unconfigured)}. Add each to AGENT_TREES in "
        "build/scripts/validate_agent_matrix_refs.py so the tier and role "
        "guards cover it, or to _EXEMPT_FILES here with the reason."
    )


def test_discovery_does_not_depend_on_the_field_it_validates():
    """A new tree must be discovered when its role is misspelled, empty, or absent.

    Two rounds of review on this one test. Copilot first found discovery
    matching only valid roles, so `role: strategc` in a new tree was invisible.
    Copilot then found the fix incomplete: the docstring promised "absent or
    misspelled" while every case still carried a role or tier, so a tree whose
    files omit `role` entirely stayed invisible and the control read as passing.

    Both signals are exercised here. Frontmatter carrying any string role or
    tier is one. A distinctive agent suffix on a real agent definition is the
    other, and it is what covers the absent case.
    """
    by_frontmatter = [
        {"name": "foo", "description": "misspelled", "role": "strategc"},
        {"name": "foo", "description": "empty", "role": ""},
        {"name": "foo", "description": "legacy top level", "tier": "builder"},
        {"name": "foo", "description": "nested misspell", "metadata": {"role": "coordinatr"}},
    ]
    missed = [case for case in by_frontmatter if not _declares_agent_metadata(case)]
    assert not missed, f"agent metadata not recognized, so its tree stays invisible: {missed}"

    # The absent-role case, which the frontmatter signal cannot see by design.
    absent = {"name": "foo", "description": "a new agent declaring no role at all"}
    assert not _declares_agent_metadata(absent), (
        "frontmatter signal is not supposed to fire without a role or tier key; "
        "if it does, the suffix signal below is untested"
    )
    real_agent = next(
        path for path in _agent_definitions() if path.name.endswith(_AGENT_FILE_SUFFIXES)
    )
    relative = real_agent.relative_to(_REPO_ROOT).as_posix()
    front = _frontmatter(real_agent)
    assert front is not None
    stripped = {key: value for key, value in front.items() if key not in {"role", "tier"}}
    assert not _declares_agent_metadata(stripped), "fixture still carries a role; test is vacuous"
    assert _looks_like_an_agent_file(relative, real_agent, stripped), (
        "a real agent file with its role stripped is still not recognized, so a new "
        "tree whose agents omit `role` would go undiscovered"
    )

    # The converse: overloaded integer tiers must stay excluded, or every skill
    # and Serena memory becomes a spurious unconfigured tree.
    not_agents = [
        {"name": "s", "description": "skill tier", "metadata": {"tier": 3}},
        {"name": "m", "description": "memory tier", "tier": 2},
    ]
    wrong = [case for case in not_agents if _declares_agent_metadata(case)]
    assert not wrong, f"non-agent frontmatter treated as agent metadata: {wrong}"


def test_configured_trees_match_the_canonical_set():
    """Cross-check the roster against the other list that names the same trees.

    `test_every_on_disk_agent_tree_is_configured` catches a tree that exists on
    disk and is unlisted. This catches the other drift: the two lists
    disagreeing about what the canonical set is, which disk-walking alone
    cannot see.

    Contributed by the Cursor autofix agent on PR #5177. Its own converse test
    was this comparison; it is kept for that cross-check but does not replace
    the disk walk above, since two lists agreeing says nothing about a seventh
    tree neither one names.
    """
    from tests.build_scripts.test_validate_agent_matrix_refs import (
        EXPECTED_TREES as MATRIX_EXPECTED_TREES,
    )

    configured = set(_AGENT_TREES)
    assert configured == MATRIX_EXPECTED_TREES, (
        "the agent tree roster drifted from the canonical set: "
        f"extra={configured - MATRIX_EXPECTED_TREES}, "
        f"missing={MATRIX_EXPECTED_TREES - configured}"
    )
