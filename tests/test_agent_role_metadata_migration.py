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
# new agent tree has to be added here deliberately.
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


def test_every_configured_tree_exists_on_disk():
    """Fail if a configured tree is missing or misspelled.

    The ``is_dir()`` filter in ``_agent_files`` silently skips missing paths,
    so a typo'd entry would go dark and the guards below would pass on fewer
    files. This is the first half of the bidirectional config-set check.
    """
    missing = {tree for tree in _AGENT_TREES if not (_REPO_ROOT / tree).is_dir()}
    assert not missing, f"configured agent trees missing from disk: {missing}"


def test_every_on_disk_agent_tree_is_configured():
    """Fail if a new agent tree is added but not listed in _AGENT_TREES.

    This is the converse of ``test_every_configured_tree_exists_on_disk``.
    Without it, a new tree added to the repo would never be scanned and any
    ``tier:`` keys introduced there would silently pass.

    The pattern matches the one in ``test_validate_agent_matrix_refs.py``.
    """
    from tests.build_scripts.test_validate_agent_matrix_refs import (
        EXPECTED_TREES as MATRIX_EXPECTED_TREES,
    )

    configured = set(_AGENT_TREES)
    assert configured == MATRIX_EXPECTED_TREES, (
        f"_AGENT_TREES drifted from the canonical set: "
        f"extra={configured - MATRIX_EXPECTED_TREES}, "
        f"missing={MATRIX_EXPECTED_TREES - configured}"
    )


def test_agent_trees_are_discovered():
    """Negative control: if the globs stop matching, the guards below are vacuous."""
    assert len(_agent_files()) > 100


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
