"""Repo-wide guards for the tier-to-role migration (issue #5130).

The migration replaced `tier:` with `role:` on 186 agent files across six
trees. Nothing prevented it from coming back. The install-parity gate catches a
*missing sibling*, and `validate_copilot_agent_frontmatter.py` constrains `role`
only under `.github/agents/`, so a new agent added tomorrow with `tier: builder`
in any other tree would pass every existing gate.

These tests are that missing guard. They assert the end state directly rather
than any one consumer's view of it, because the defect this migration fixed was
precisely a consumer reading one shape and missing the other.

Raised in review of PR #5177: "No repo-wide test asserts zero `tier:` keys
across the six agent trees... a reintroduced `tier:` on a new agent would not
fail any gate."

The tree roster and the predicate for what counts as an agent definition are
imported from `build/scripts/validate_agent_matrix_refs.py` rather than
restated. An earlier revision hardcoded both, which Cursor Bugbot flagged as a
one-directional config set: a seventh tree, or a renamed one, went unchecked.
Deriving from the canonical constant removes that class rather than guarding it.
"""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_matrix_validator():
    """Load the canonical agent-tree roster and agent-definition predicate."""
    path = _REPO_ROOT / "build" / "scripts" / "validate_agent_matrix_refs.py"
    spec = importlib.util.spec_from_file_location("validate_agent_matrix_refs", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_vamr = _load_matrix_validator()

# (tree path, filename suffix) for each configured tree, from the canonical
# constant. Suffix matters: `.claude/agents` uses a bare `.md`, so it admits
# sibling docs like `AGENTS.md` that are not agent definitions.
# `as_posix()`, not `str()`: on Windows `str(Path)` yields backslashes while
# discovery below records parents with `as_posix()`, so the two sets would
# never intersect and every real tree would read as unconfigured.
_AGENT_TREES = tuple(tree.as_posix() for tree, _ in _vamr.AGENT_TREES)

# Must stay in sync with _KNOWN_ROLES in scripts/openclaw_bridge.py,
# scripts/validation/validate_copilot_agent_frontmatter.py, and
# build/generate_agent_catalog.py.
_KNOWN_ROLES = frozenset({"strategic", "coordinator", "executor", "support"})

# The pre-migration vocabulary. Discovery keys on these *values*, not on the key
# names, because both keys are overloaded here: skills use `metadata.tier: 3`
# for skill tier, Serena memories use `tier:` for memory tier, and
# `.claude/skills/review/references/*.md` use `role: analyst` for a review axis.
# A key-name check drags all three in as false positives.
_LEGACY_TIERS = frozenset({"expert", "manager", "builder", "integration"})

# Frozen measurement artifacts for issue #1738. They deliberately retain
# `metadata.tier` because rewriting them would alter a recorded measurement.
# Listed per file, not per directory, so adding one is a deliberate edit here
# rather than silent inheritance of a directory-wide exemption.
_EXEMPT_FILES = frozenset(
    {
        ".agents/prototypes/agents/implementer.compressed.md",
        ".agents/prototypes/agents/orchestrator.compressed.md",
        ".agents/prototypes/agents/security.compressed.md",
        ".agents/analysis/instruction-specificity-prototype-security-compressed.md",
    }
)

_FRONTMATTER_RE = re.compile(r"^---\r?\n([\s\S]*?)\r?\n---\r?\n")

# Matches a `tier:` key inside a frontmatter block at any indent. Used for the
# textual sweep that does not depend on the block parsing as YAML.
_RAW_TIER_RE = re.compile(r"^[ \t]*tier:[ \t]*(\S.*)$", re.M)


def _agent_files() -> list[Path]:
    """Every file in a configured tree that carries that tree's suffix."""
    files: list[Path] = []
    for tree, suffix in _vamr.AGENT_TREES:
        root = _REPO_ROOT / tree
        if root.is_dir():
            files.extend(sorted(root.glob(f"*{suffix}")))
    return files


def _agent_definitions() -> list[Path]:
    """Agent files the repo's own predicate accepts as definitions.

    Excludes siblings like `AGENTS.md` and `claude-instructions.template.md`
    that share a tree's bare `.md` suffix but ship no agent frontmatter.
    """
    return [path for path in _agent_files() if _vamr.is_agent_definition(path)]


def _frontmatter_block(path: Path) -> str | None:
    """The raw text between the frontmatter fences, unparsed."""
    match = _FRONTMATTER_RE.match(path.read_text(encoding="utf-8"))
    return match.group(1) if match else None


def _frontmatter(path: Path) -> dict | None:
    block = _frontmatter_block(path)
    if block is None:
        return None
    try:
        parsed = yaml.safe_load(block)
    except yaml.YAMLError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _declared_role(front: dict) -> object | None:
    """The role a file declares, top-level shape taking precedence over nested.

    Mirrors `_read_declared_role` in scripts/openclaw_bridge.py.
    """
    if front.get("role") is not None:
        return front["role"]
    nested = front.get("metadata")
    if isinstance(nested, dict):
        return nested.get("role")
    return None


def _declares_agent_metadata(front: dict) -> bool:
    """True when frontmatter carries an agent role or a pre-migration agent tier."""
    scopes = [front]
    nested = front.get("metadata")
    if isinstance(nested, dict):
        scopes.append(nested)
    return any(
        scope.get("role") in _KNOWN_ROLES or scope.get("tier") in _LEGACY_TIERS
        for scope in scopes
    )


def _tracked_markdown() -> list[str]:
    """Every markdown path git tracks, as repo-relative posix strings.

    Deliberately not `rglob`. This suite runs under xdist alongside tests that
    materialize git worktrees and scratch repositories, and a raw filesystem
    walk races them: a sibling test's temporary checkout carries the six real
    agent trees under a path this file has never heard of, and the converse
    guard below reports them as unconfigured. That failure is scheduling
    dependent, so it passes locally and fails in CI, which is how it was found
    (PR #5177, the `bulk-nested` partition).

    Asking git removes the race. It answers about committed and staged content
    only, which is the exact scope this guard is about: a seventh agent tree
    someone added to the repository, not a directory that existed for 200ms
    inside another test.
    """
    result = subprocess.run(
        ["git", "ls-files", "-z", "--", "*.md"],
        cwd=_REPO_ROOT,
        capture_output=True,
        check=True,
        encoding=None,
    )
    return [name for name in result.stdout.decode("utf-8").split("\0") if name]


def _discover_agent_trees() -> set[str]:
    """Every tracked directory holding agent frontmatter, found by search, not config."""
    found: set[str] = set()
    for name in _tracked_markdown():
        if name in _EXEMPT_FILES:
            continue
        path = _REPO_ROOT / name
        if not path.is_file():
            continue
        front = _frontmatter(path)
        if front is not None and _declares_agent_metadata(front):
            found.add(PurePosixPath(name).parent.as_posix())
    return found


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
    unconfigured = _discover_agent_trees() - set(_AGENT_TREES)
    assert not unconfigured, (
        "agent frontmatter found in unconfigured trees: "
        f"{sorted(unconfigured)}. Add each to AGENT_TREES in "
        "build/scripts/validate_agent_matrix_refs.py so the tier and role "
        "guards cover it, or to _EXEMPT_FILES here with the reason."
    )


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


def test_no_agent_file_carries_a_tier_key():
    """The migrated key must not come back, in either shape.

    Two independent sweeps. The parsed sweep reads `tier:` at the top level and
    `metadata.tier` nested; the first migration pass matched only the top-level
    shape and silently left 50 files behind.

    The textual sweep re-checks the same files without parsing. Raised by
    Copilot on PR #5177: a file whose frontmatter fails to parse was dropped
    from the corpus entirely, so a malformed agent could retain `tier:` and
    keep this green. The value must also be an agent tier, since a suffix-
    matching sibling doc may legitimately use `tier:` for something else.
    """
    offenders = []
    for path in _agent_files():
        relative = path.relative_to(_REPO_ROOT)
        front = _frontmatter(path)
        if front is not None:
            if "tier" in front:
                offenders.append(f"{relative} (top-level tier)")
            nested = front.get("metadata")
            if isinstance(nested, dict) and "tier" in nested:
                offenders.append(f"{relative} (metadata.tier)")
            continue

        block = _frontmatter_block(path)
        if block is None:
            continue
        for value in _RAW_TIER_RE.findall(block):
            if value.strip().strip("\"'") in _LEGACY_TIERS:
                offenders.append(f"{relative} (unparseable frontmatter, raw tier: {value!r})")

    assert not offenders, (
        "agent files still carry the migrated `tier:` key: "
        + ", ".join(offenders)
        + ". Use `role:` with one of: "
        + ", ".join(sorted(_KNOWN_ROLES))
    )


def test_every_agent_definition_declares_a_known_role():
    """Every agent must declare a role, and it must be in the closed set.

    Checking only *declared* roles let an agent with no role at all pass.
    Raised by Copilot on PR #5177: that is material for the nested Claude
    trees, because the OpenClaw bridge exports an absent role as `support`
    without complaint and the Copilot-side validator does not reach those
    files, so the asserted 186-file migration would stop being enforced.
    """
    offenders = []
    for path in _agent_definitions():
        relative = path.relative_to(_REPO_ROOT)
        front = _frontmatter(path)
        if front is None:
            offenders.append(f"{relative}: frontmatter does not parse")
            continue
        declared = _declared_role(front)
        if declared is None:
            offenders.append(f"{relative}: no role declared")
        elif not isinstance(declared, str) or declared.strip() not in _KNOWN_ROLES:
            offenders.append(f"{relative}: unknown role {declared!r}")

    assert not offenders, (
        "agent definitions with a missing or unknown role: "
        + ", ".join(offenders)
        + ". Known roles: "
        + ", ".join(sorted(_KNOWN_ROLES))
    )


def test_no_agent_definition_declares_conflicting_roles():
    """A file must not declare one role at the top level and another nested.

    `_read_declared_role` gives the top level precedence, so a contradictory
    file resolves to one value in the OpenClaw export and could be read as the
    other by a consumer that looks only at the nested shape. Nothing else fails
    on the disagreement. Raised by the spec validator on PR #5177.
    """
    offenders = []
    for path in _agent_definitions():
        front = _frontmatter(path)
        if front is None:
            continue
        nested = front.get("metadata")
        if not isinstance(nested, dict):
            continue
        top, inner = front.get("role"), nested.get("role")
        if top is not None and inner is not None and top != inner:
            offenders.append(f"{path.relative_to(_REPO_ROOT)}: {top!r} vs {inner!r}")

    assert not offenders, (
        "agent definitions declare conflicting roles in the two shapes: " + ", ".join(offenders)
    )


# `.agents/SESSION-PROTOCOL.md` was in this list until PR #5179 deleted the file
# and every living reference to it. Dropped rather than left behind, because a
# parametrized case naming a path that no longer exists fails on the read, which
# reports a missing escalation target where the real answer is that the document
# is gone.
@pytest.mark.parametrize(
    "document",
    [
        ".agents/AGENT-SYSTEM.md",
        "docs/orchestrator-routing-algorithm.md",
    ],
)
def test_escalation_target_is_high_level_advisor(document: str):
    """Pin the escalation target ADR-009 actually names.

    PR #5127 was reverted for naming the wrong target, and the replacement in
    PR #5177 reintroduced it two sections later in a single document that then
    carried two contradicting contracts. Nothing would have caught either.

    ADR-009:81 and :91 say `high-level-advisor`. These documents must not name
    a different arbiter.
    """
    text = (_REPO_ROOT / document).read_text(encoding="utf-8")

    assert "high-level-advisor" in text, f"{document} does not name the ADR-009 target"

    forbidden = (
        "escalate_to_architect",
        "Escalate to architect",
        '"escalate_to": "manager"',
        "escalate to the orchestrator",
    )
    present = [phrase for phrase in forbidden if phrase in text]
    assert not present, (
        f"{document} names a non-ADR-009 escalation target: {present}. "
        "ADR-009:81 and :91 route conflicts to high-level-advisor."
    )
