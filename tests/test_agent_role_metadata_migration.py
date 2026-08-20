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

Tree-roster and discovery guards live in `test_agent_tree_discovery.py`.
"""

from __future__ import annotations

import re

import pytest

from tests.agent_metadata_helpers import (
    _KNOWN_ROLES,
    _LEGACY_TIERS,
    _RAW_TIER_RE,
    _REPO_ROOT,
    _agent_definitions,
    _agent_files,
    _declared_role,
    _frontmatter,
    _frontmatter_block,
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
def test_role_vocabulary_table_names_real_agents_with_those_roles():
    """Every example in the AGENT-SYSTEM role table must be an agent with that role.

    Copilot found `memory` listed as a support-role agent on PR #5177. It is a
    skill, not an agent, and `validate_agent_matrix_refs` documents a phantom
    `memory` agent as the incident it exists to prevent, so the new vocabulary
    was pointing readers at exactly the name that motivated that guard.

    A prose table naming agents is a citation, and citations rot. Nothing else
    checks this one.
    """
    text = (_REPO_ROOT / ".agents/AGENT-SYSTEM.md").read_text(encoding="utf-8")
    row = re.compile(r"^\|\s*`(strategic|coordinator|executor|support)`\s*\|[^|]*\|([^|]*)\|", re.M)

    declared: dict[str, object] = {}
    for path in _agent_definitions():
        front = _frontmatter(path)
        if front is not None:
            declared.setdefault(path.name.split(".")[0], _declared_role(front))

    rows = row.findall(text)
    assert rows, "role vocabulary table not found in .agents/AGENT-SYSTEM.md"

    offenders = []
    for claimed, examples in rows:
        for name in (part.strip() for part in examples.split(",")):
            if not name:
                continue
            if name not in declared:
                offenders.append(
                    f"{name}: named as a {claimed} agent but ships no agent definition"
                )
            elif declared[name] != claimed:
                offenders.append(
                    f"{name}: table says {claimed}, frontmatter says {declared[name]!r}"
                )

    assert not offenders, "role vocabulary table is wrong: " + "; ".join(offenders)


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
