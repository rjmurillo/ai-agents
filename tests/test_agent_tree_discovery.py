"""Guards on the agent-tree roster itself (issue #5130).

The converse-guard family: the configured roster must match what is on disk,
and discovery must not depend on the field the migration guards validate. Every
test here exists because a review found the previous version blind in exactly
the case it was written to catch.

It also owns the two guards that are about the corpus the roster yields
rather than about any one file: every agent file in a configured tree must be
readable as a definition, and an agent shipped into several trees must declare
one role in all of them.

Split from `test_agent_role_metadata_migration.py` at the 500-line ceiling.
"""

from __future__ import annotations

import pytest

from tests.agent_metadata_helpers import (
    _AGENT_FILE_SUFFIXES,
    _AGENT_TREES,
    _CANONICAL_TREE,
    _NON_AGENT_ROLE_DIRS,
    _NON_AGENT_SIBLINGS,
    _REPO_ROOT,
    _agent_definitions,
    _agent_files,
    _cross_tree_role_disagreements,
    _declares_agent_metadata,
    _discover_agent_trees,
    _frontmatter,
    _looks_like_an_agent_file,
    _roles_by_agent_name,
    _why_not_an_agent_definition,
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


def test_agents_present_in_several_trees_declare_one_role():
    """A shared agent must not carry different roles in different trees.

    31 agent names ship in more than one of the six trees. Nothing checked that
    the copies agree. Proven on PR #5177 by setting `.claude/agents/janitor.md`
    to `role: strategic` while `templates/agents/janitor.shared.md` kept
    `role: support`: 119 tests stayed green and
    `build/scripts/detect_agent_drift.py` reported no drift.

    `test_role_vocabulary_table_names_real_agents_with_those_roles` above looks
    like it would catch this and cannot. It builds its map with
    `declared.setdefault(...)` over `_agent_files()`, which walks `AGENT_TREES`
    with `templates/agents` first, so it only ever records the template's value
    and every divergent copy is masked by the one that came first.
    """
    roles = _roles_by_agent_name()

    # Anti-vacuous control. An empty or single-tree map makes the assertion
    # below hold for free, which is the exact shape of the bug it guards.
    shared = [name for name, by_tree in roles.items() if len(by_tree) > 1]
    assert len(shared) >= 25, (
        f"only {len(shared)} agent names appear in more than one tree, so the "
        "cross-tree comparison is close to vacuous. Measured on PR #5177: 31."
    )

    offenders = _cross_tree_role_disagreements(roles)
    assert not offenders, (
        "the same agent declares different roles in different trees: "
        + "; ".join(offenders)
        + f". {_CANONICAL_TREE} is the canonical source; re-copy the role from "
        "the template rather than editing one install's copy."
    )


@pytest.mark.parametrize(
    ("case", "roles", "expected"),
    [
        (
            "agreement across three trees is silent",
            {"janitor": {_CANONICAL_TREE: "support", ".claude/agents": "support"}},
            [],
        ),
        (
            "an agent in one tree only has nothing to disagree with",
            {"quality-auditor": {".claude/agents": "executor"}},
            [],
        ),
        (
            "divergence is reported against the template",
            {
                "janitor": {
                    _CANONICAL_TREE: "support",
                    ".claude/agents": "strategic",
                    "src/claude": "support",
                }
            },
            [
                f"janitor: {_CANONICAL_TREE} declares 'support', but "
                ".claude/agents declares 'strategic'"
            ],
        ),
        (
            "divergence with no template falls back to the first tree",
            {"ghost": {"src/claude": "executor", ".claude/agents": "support"}},
            ["ghost: .claude/agents declares 'support', but src/claude declares 'executor'"],
        ),
        (
            "a copy that declares no role at all diverges",
            {"janitor": {_CANONICAL_TREE: "support", ".claude/agents": None}},
            [f"janitor: {_CANONICAL_TREE} declares 'support', but .claude/agents declares None"],
        ),
        (
            "an unhashable role is reported, not crashed on",
            {"janitor": {_CANONICAL_TREE: "support", ".claude/agents": ["support"]}},
            [
                f"janitor: {_CANONICAL_TREE} declares 'support', but "
                ".claude/agents declares ['support']"
            ],
        ),
    ],
)
def test_cross_tree_role_comparison_verdicts(case: str, roles: dict, expected: list[str]):
    """Unit cases for the comparison, since the repo has no divergence to show.

    Every one of the 31 shared names agrees today and every one ships a
    template, so the repo sweep above exercises the agreeing path only. The
    tree-specific and no-template branches would be dead code measured against
    live data alone, which is how the masking bug in the older table test
    survived.
    """
    assert _cross_tree_role_disagreements(roles) == expected, case


def test_every_agent_file_in_a_configured_tree_is_a_readable_definition():
    """A malformed agent must fail the build, not drop out of the corpus.

    Every other role guard iterates `_agent_definitions()`, which filters
    through `is_agent_definition`. That predicate requires parseable
    frontmatter with a usable `description`, so a broken file is not reported
    as broken; it stops being an agent as far as the suite is concerned, and
    every assertion about roles then holds over a corpus that no longer
    contains it. Proven on PR #5177: a planted `.claude/agents/zzqaprobe.md`
    with unbalanced YAML and `role: strategc` passed the migration suite,
    `validate_agent_matrix_refs.py` (exit 0, `OK`), and
    `validate_copilot_agent_frontmatter.py` (`[PASS]`, which reads
    `.github/agents/` only). Copilot asked for the same thing: "Make configured
    agent files fail closed on malformed frontmatter instead of dropping them
    from the corpus."

    Scope is a file that already sits in a configured tree carrying that
    tree's suffix. Two of the six trees use a bare `.md`, which admits sibling
    documents, so `_NON_AGENT_SIBLINGS` names the four that are deliberately
    not agents. That allowlist is itself guarded below.
    """
    offenders = []
    for path in _agent_files():
        relative = path.relative_to(_REPO_ROOT).as_posix()
        if relative in _NON_AGENT_SIBLINGS:
            continue
        reason = _why_not_an_agent_definition(path)
        if reason:
            offenders.append(f"{relative}: {reason}")

    assert not offenders, (
        "files in a configured agent tree are not readable as agent "
        "definitions, so every role guard skips them: " + "; ".join(offenders) + ". Fix the "
        "frontmatter, or add the file to _NON_AGENT_SIBLINGS in "
        "tests/agent_metadata_helpers.py if it is a sibling document rather "
        "than an agent."
    )


def test_the_non_agent_sibling_allowlist_is_neither_stale_nor_vacuous():
    """The allowlist above must not excuse a live agent or a deleted file.

    An allowlist is the hole in a fail-closed guard. A path that no longer
    exists is dead weight that hides the next real exclusion, and a path that
    has since grown real agent frontmatter would be silently exempted from
    every guard the fail-closed check exists to feed.
    """
    discovered = {path.relative_to(_REPO_ROOT).as_posix() for path in _agent_files()}

    missing = sorted(_NON_AGENT_SIBLINGS - discovered)
    assert not missing, (
        "_NON_AGENT_SIBLINGS names files no configured tree ships: "
        f"{missing}. Remove them rather than leaving a stale exemption."
    )

    now_agents = sorted(
        relative
        for relative in _NON_AGENT_SIBLINGS
        if not _why_not_an_agent_definition(_REPO_ROOT / relative)
    )
    assert not now_agents, (
        "_NON_AGENT_SIBLINGS exempts files that now read as real agent "
        f"definitions: {now_agents}. Drop them from the allowlist so their "
        "roles are checked."
    )
