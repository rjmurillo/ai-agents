"""Repo-wide guards for the tier-to-role migration (issue #5130).

The migration replaced `tier:` with `role:` on 186 agent files across six
trees. Nothing prevented it from coming back. The install-parity gate catches
a *missing sibling*, and `validate_copilot_agent_frontmatter.py` constrains
`role` only under `.github/agents/`, so a new agent added tomorrow with
`tier: builder` in any other tree would pass every existing gate.

These tests are that missing guard. They assert the end state directly rather
than any one consumer's view of it, because the defect this migration fixed was
precisely a consumer reading one shape and missing the other.

Raised in review of PR #5177: "No repo-wide test asserts zero `tier:` keys
across the six agent trees... a reintroduced `tier:` on a new agent would not
fail any gate."
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[1]

# The six trees the migration covered. Kept explicit rather than globbed so a
# new agent tree has to be added here deliberately;
# `test_every_on_disk_agent_tree_is_configured` is what makes that deliberate
# rather than optional.
_AGENT_TREES = (
    "templates/agents",
    ".claude/agents",
    ".github/agents",
    "src/claude",
    "src/vs-code-agents",
    "src/copilot-cli/agents",
)

# Must stay in sync with _KNOWN_ROLES in scripts/openclaw_bridge.py,
# scripts/validation/validate_copilot_agent_frontmatter.py, and
# build/generate_agent_catalog.py.
_KNOWN_ROLES = frozenset({"strategic", "coordinator", "executor", "support"})

_FRONTMATTER_RE = re.compile(r"^---\r?\n([\s\S]*?)\r?\n---\r?\n")


def _agent_files() -> list[Path]:
    files: list[Path] = []
    for tree in _AGENT_TREES:
        root = _REPO_ROOT / tree
        if root.is_dir():
            files.extend(sorted(root.glob("*.md")))
    return files


def _frontmatter(path: Path) -> dict | None:
    match = _FRONTMATTER_RE.match(path.read_text(encoding="utf-8"))
    if match is None:
        return None
    try:
        parsed = yaml.safe_load(match.group(1))
    except yaml.YAMLError:
        return None
    return parsed if isinstance(parsed, dict) else None


# Frozen measurement artifacts for issue #1738. They deliberately retain
# `metadata.tier` because rewriting them would alter a recorded measurement.
# Listed per file, not per directory, so adding a new one is a deliberate edit
# here rather than a silent inheritance of a directory-wide exemption.
_EXEMPT_FILES = frozenset(
    {
        ".agents/prototypes/agents/implementer.compressed.md",
        ".agents/prototypes/agents/orchestrator.compressed.md",
        ".agents/prototypes/agents/security.compressed.md",
        ".agents/analysis/instruction-specificity-prototype-security-compressed.md",
    }
)

# Directories that never hold agent definitions, skipped when walking.
_UNSEARCHED = frozenset(
    {".git", ".venv", "node_modules", "__pycache__", ".mypy_cache", ".pytest_cache"}
)

# The pre-migration vocabulary. Detection keys on these *values*, not on the
# key names: `tier:` and `role:` are both overloaded in this repo. Skills use
# `metadata.tier: 3` for skill tier, Serena memories use `tier:` for memory
# tier, and `.claude/skills/review/references/*.md` use `role: analyst` for a
# review axis. None of those are agent metadata, and a key-name check would
# drag all three in as false positives.
_LEGACY_TIERS = frozenset({"expert", "manager", "builder", "integration"})


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


def _discover_agent_trees() -> set[str]:
    """Every directory on disk holding agent frontmatter, found by walking, not config."""
    found: set[str] = set()
    for path in _REPO_ROOT.rglob("*.md"):
        relative = path.relative_to(_REPO_ROOT)
        if _UNSEARCHED & set(relative.parts) or relative.as_posix() in _EXEMPT_FILES:
            continue
        front = _frontmatter(path)
        if front is not None and _declares_agent_metadata(front):
            found.add(relative.parent.as_posix())
    return found


def test_configured_trees_match_the_canonical_set():
    """Cross-check against the repo's canonical tree list, not just against disk.

    `test_every_on_disk_agent_tree_is_configured` catches a tree that exists on
    disk and is unlisted here. This catches the other drift: this list and
    `test_validate_agent_matrix_refs.EXPECTED_TREES` disagreeing about what the
    canonical set is, which disk-walking alone cannot see.

    Contributed by the Cursor autofix agent on PR #5177. Its own converse test
    was this comparison; it is kept for that cross-check but does not replace
    the disk walk above, since two hardcoded lists agreeing says nothing about
    a seventh tree neither one names.
    """
    from tests.build_scripts.test_validate_agent_matrix_refs import (
        EXPECTED_TREES as MATRIX_EXPECTED_TREES,
    )

    configured = set(_AGENT_TREES)
    assert configured == MATRIX_EXPECTED_TREES, (
        "_AGENT_TREES drifted from the canonical set: "
        f"extra={configured - MATRIX_EXPECTED_TREES}, "
        f"missing={MATRIX_EXPECTED_TREES - configured}"
    )



def test_agent_trees_are_discovered():
    """Negative control: if the globs stop matching, the guards below are vacuous."""
    assert len(_agent_files()) > 100


def test_every_configured_tree_exists():
    """A typo in `_AGENT_TREES` is silently skipped by `is_dir()`, so name it here.

    Without this, renaming a tree on disk turns its guard into a no-op that
    still reports green.
    """
    missing = [tree for tree in _AGENT_TREES if not (_REPO_ROOT / tree).is_dir()]
    assert not missing, f"_AGENT_TREES names directories that do not exist: {missing}"


def test_every_on_disk_agent_tree_is_configured():
    """Converse guard: the config set must cover what is actually on disk.

    `_AGENT_TREES` is a hardcoded list, so on its own it only proves things
    about trees someone remembered to add. A seventh tree added tomorrow would
    carry `tier:` past every check in this file. Raised by Cursor Bugbot on
    PR #5177 against the learned rule that a configuration-set test needs a
    converse guard.
    """
    unconfigured = _discover_agent_trees() - set(_AGENT_TREES)
    assert not unconfigured, (
        "agent frontmatter found in unconfigured trees: "
        f"{sorted(unconfigured)}. Add each to _AGENT_TREES so the tier and role "
        "guards cover it, or to _EXEMPT_FILES with the reason."
    )


def test_no_agent_file_carries_a_tier_key():
    """The migrated key must not come back, in either shape.

    `tier:` at the top level and `metadata.tier` nested are both failures. The
    first migration pass matched only the top-level shape and silently left 50
    files behind, so this checks both.
    """
    offenders = []
    for path in _agent_files():
        frontmatter = _frontmatter(path)
        if frontmatter is None:
            continue
        if "tier" in frontmatter:
            offenders.append(f"{path.relative_to(_REPO_ROOT)} (top-level tier)")
        nested = frontmatter.get("metadata")
        if isinstance(nested, dict) and "tier" in nested:
            offenders.append(f"{path.relative_to(_REPO_ROOT)} (metadata.tier)")

    assert not offenders, (
        "agent files still carry the migrated `tier:` key: "
        + ", ".join(offenders)
        + ". Use `role:` with one of: "
        + ", ".join(sorted(_KNOWN_ROLES))
    )


def test_every_declared_role_is_a_known_value():
    """A role outside the closed set is a typo that silently becomes `support`."""
    offenders = []
    for path in _agent_files():
        frontmatter = _frontmatter(path)
        if frontmatter is None:
            continue
        nested = frontmatter.get("metadata")
        declared = frontmatter.get("role")
        if declared is None and isinstance(nested, dict):
            declared = nested.get("role")
        if declared is None:
            continue
        if not isinstance(declared, str) or declared.strip() not in _KNOWN_ROLES:
            offenders.append(f"{path.relative_to(_REPO_ROOT)}: {declared!r}")

    assert not offenders, (
        "agent files declare an unknown role: "
        + ", ".join(offenders)
        + ". Known roles: "
        + ", ".join(sorted(_KNOWN_ROLES))
    )


@pytest.mark.parametrize(
    "document",
    [
        ".agents/AGENT-SYSTEM.md",
        ".agents/SESSION-PROTOCOL.md",
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
