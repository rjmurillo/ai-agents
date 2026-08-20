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

import importlib.util
import re
import sys

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

    A second round found the sweep still escapable: an *unterminated* block has
    no closing fence, so even the raw extractor returned None and the file was
    skipped. The sweep now falls back to the whole file text in that case.
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

        # `_frontmatter_block` returns None for an *unterminated* block, since
        # the fence regex needs a closing `---`. Falling through on that would
        # skip the file outright, which the spec validator caught on PR #5177:
        # a file whose frontmatter is never closed evaded both sweeps. Fall back
        # to the whole text, which is safe here because the match also requires
        # a pre-migration tier value. Measured across all 190 agent files: zero
        # hits, so this adds no false positives.
        block = _frontmatter_block(path)
        haystack = block if block is not None else path.read_text(encoding="utf-8")
        shape = "unparseable frontmatter" if block is not None else "unterminated frontmatter"
        for value in _RAW_TIER_RE.findall(haystack):
            if value.strip().strip("\"'") in _LEGACY_TIERS:
                offenders.append(f"{relative} ({shape}, raw tier: {value!r})")

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

    The `front is None` branch below does NOT cover a malformed agent, and its
    message used to claim it did. `_agent_definitions()` filters through
    `is_agent_definition`, which already requires a parseable block with a
    usable `description`, so a malformed file leaves the corpus before this
    loop runs. Copilot and this PR's qa pass found the same hole
    independently, and a planted `.claude/agents/zzqaprobe.md` carrying
    unbalanced YAML and `role: strategc` passed this test. That case is now
    `test_every_agent_file_in_a_configured_tree_is_a_readable_definition` in
    `test_agent_tree_discovery.py`, which fails closed on the corpus instead.

    What the branch really catches is narrower and still worth reporting: the
    two parsers disagreeing about one file. `agent_frontmatter` reads with
    `utf-8-sig` while `_frontmatter` here reads with `utf-8`, so a byte-order
    mark makes the first accept the file and the second reject it, and the
    agent's role then goes unchecked. Verified by planting a BOM.
    """
    offenders = []
    for path in _agent_definitions():
        relative = path.relative_to(_REPO_ROOT)
        front = _frontmatter(path)
        if front is None:
            offenders.append(
                f"{relative}: accepted as an agent by "
                "build/scripts/validate_agent_matrix_refs.py but rejected by "
                "this module's parser, so its role is checked by neither"
            )
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


def _adr_009_block(start_marker: str, end_marker: str) -> str:
    """Return the ADR-009 span from `start_marker` through `end_marker`."""
    adr = (
        _REPO_ROOT / ".agents/architecture/ADR-009-parallel-safe-multi-agent-design.md"
    ).read_text(encoding="utf-8")
    start = adr.index(start_marker)
    end = adr.index(end_marker, start) + len(end_marker)
    return adr[start:end]


@pytest.mark.parametrize(
    ("document", "start_marker", "end_marker"),
    [
        (
            ".agents/AGENT-SYSTEM.md",
            "| **merge** |",
            "| **escalate** | Conflicts detected | Route to high-level-advisor |",
        ),
        (
            "docs/orchestrator-routing-algorithm.md",
            "| **merge** |",
            "| **escalate** | Conflicts detected | Route to high-level-advisor |",
        ),
        (
            ".agents/AGENT-SYSTEM.md",
            "1. Orchestrator dispatches to N agents in parallel",
            "4. Final decision applied",
        ),
    ],
)
def test_adr_009_blocks_are_quoted_byte_for_byte(document: str, start_marker: str, end_marker: str):
    """The ADR-009 quotes must stay byte-identical to ADR-009.

    Issue #5130 exists because PR #5127 shipped a *paraphrase* that named the
    wrong arbiter. The fix was to quote ADR-009 verbatim instead, and
    `.claude/rules/canonical-source-mirror.md` requires exactly that. But
    nothing enforced it: `test_escalation_target_is_high_level_advisor` above
    pins the target string only, so editing ADR-009's table or protocol would
    leave both mirrors silently stale and restore the #5127 condition. The
    byte comparison existed only as a copy-pasteable snippet in
    `.agents/critique/5130-tier-hierarchy-removal-debate-log.md`.

    Added by the issue #5130 `adr-review` debate (critic P1-5, architect P2).

    Note the asymmetry in the parametrization: `docs/orchestrator-routing-algorithm.md`
    quotes the aggregation table but not the consensus protocol, which its own
    per-file table discloses. Asserting the protocol there would fail on a
    documented, intentional omission, so it is not asserted.
    """
    quoted = _adr_009_block(start_marker, end_marker)
    text = (_REPO_ROOT / document).read_text(encoding="utf-8")

    assert quoted in text, (
        f"{document} no longer quotes ADR-009 byte-for-byte.\n"
        f"ADR-009 says:\n{quoted}\n"
        "Re-copy the block from "
        ".agents/architecture/ADR-009-parallel-safe-multi-agent-design.md "
        "rather than editing the mirror."
    )


# The three production modules that each restate the closed role vocabulary.
# Every one of them rejects a value outside its own copy, so a copy that drifts
# does not fail loudly; it changes what one gate accepts while the other two
# keep refusing, and the disagreement surfaces as a rejected agent somewhere
# downstream.
_ROLE_VOCABULARY_CONSUMERS = (
    "scripts/openclaw_bridge.py",
    "scripts/validation/validate_copilot_agent_frontmatter.py",
    "build/generate_agent_catalog.py",
)


def _module_constant(relative: str, attribute: str) -> object:
    """Read `attribute` from the module at `relative`, loaded by path.

    By path rather than by dotted import, because the three consumers do not
    share one import root: two are under the `scripts` package and the third
    sits in `build/`, which is not a package and is reached by a `sys.path`
    insert in its own tests. Loading by path treats all three the same and
    names the file in the failure.

    The probe name is namespaced and popped afterwards so this never shadows
    the real `scripts.openclaw_bridge` for a sibling test module.
    """
    path = _REPO_ROOT / relative
    name = f"_role_vocabulary_probe_{path.stem}"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader, f"cannot load {relative}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(name, None)
    return getattr(module, attribute, None)


@pytest.mark.parametrize("consumer", _ROLE_VOCABULARY_CONSUMERS)
def test_role_vocabulary_agrees_across_consumers(consumer: str):
    """The four `_KNOWN_ROLES` definitions must name the same closed set.

    Three of the four carry a "Must stay in sync" comment and nothing enforced
    it. Proven on PR #5177 by adding `"auditor"` to the validator's copy alone:
    all six affected modules stayed green, 119 passed. Copilot asked for the
    same guard independently.

    A shared constant would be better and is not reachable from here. The three
    consumers run as standalone scripts from three different roots, one of them
    outside any package, so centralizing means editing three production entry
    points and their import bootstraps. This asserts the invariant those
    comments already claim, at the cost of a fourth copy: the literal in
    `agent_metadata_helpers` is the independent witness each consumer is
    measured against, which is what keeps the comparison from being two aliases
    of one value.

    Parametrized per consumer so the failure names the file to edit rather than
    reporting that some set somewhere disagrees.
    """
    roles = _module_constant(consumer, "_KNOWN_ROLES")

    # Anti-vacuous control. A renamed or deleted constant returns None, and
    # `None != _KNOWN_ROLES` would fail with a message blaming the vocabulary
    # instead of the rename.
    assert isinstance(roles, frozenset | set) and roles, (
        f"{consumer} no longer defines a non-empty `_KNOWN_ROLES`; it is "
        f"{roles!r}. Update _ROLE_VOCABULARY_CONSUMERS to the new name rather "
        "than dropping the consumer from the comparison."
    )
    assert all(isinstance(role, str) for role in roles), (
        f"{consumer} defines non-string roles: {sorted(map(repr, roles))}"
    )

    assert set(roles) == set(_KNOWN_ROLES), (
        f"{consumer} disagrees with the role vocabulary: "
        f"extra={sorted(set(roles) - set(_KNOWN_ROLES))}, "
        f"missing={sorted(set(_KNOWN_ROLES) - set(roles))}. All four copies "
        "must name the same set: the three in "
        f"{', '.join(_ROLE_VOCABULARY_CONSUMERS)} and the one in "
        "tests/agent_metadata_helpers.py."
    )


_ROLE_INERTNESS_CLAUSES = (
    "It grants and withholds nothing at runtime.",
    "not by comparing two agents'\nrole values.",
)


def test_the_role_inertness_sentence_survives_in_agent_system():
    """Pin the sentence ADR-098 names as the mitigation for its Standing Dissent.

    ADR-098 retires the tier hierarchy on the ground that a documented
    constraint nothing verifies drifts from behavior silently. Its own residual
    risk is that a reader re-derives a rank from the four `role` values, and the
    single mitigation it names is this sentence in `.agents/AGENT-SYSTEM.md`
    section 2.5. The ADR's Standing Dissent says in as many words that if the
    sentence is dropped, the dissent becomes live again.

    Nothing checked it. The ADR-009 quotes are pinned byte-for-byte, the
    escalation target is pinned, and the role table is pinned, while the one
    sentence the decision record calls load-bearing was held by nothing. An ADR
    that condemns unverified documented constraints cannot rest on one.

    Raised independently by the high-level-advisor (P0), architect (P1), and
    security (P2) passes of the issue #5130 `adr-review` debate on ADR-098.
    """
    text = (_REPO_ROOT / ".agents/AGENT-SYSTEM.md").read_text(encoding="utf-8")

    missing = [clause for clause in _ROLE_INERTNESS_CLAUSES if clause not in text]
    assert not missing, (
        "`.agents/AGENT-SYSTEM.md` no longer states that `role` is inert and does "
        f"not order agents. Missing: {missing}. ADR-098 names this sentence as the "
        "mitigation for its Standing Dissent, so removing it reopens that dissent: "
        "either restore the wording or amend ADR-098 to say what replaced it."
    )
