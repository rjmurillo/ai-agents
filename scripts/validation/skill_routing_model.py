"""Shared vocabulary for the skill routing-role gate (DESIGN-036).

`check_skill_routing_roles.py` validates declarations and
`skill_routing_evidence.py` reports on them; both read these names.
"""

from __future__ import annotations

from dataclasses import dataclass

ROLES: tuple[str, ...] = (
    "front-door",
    "lifecycle",
    "conditional-adjunct",
    "nested-helper",
    "explicit-only",
    "deprecated",
)

# The six lifecycle skills. autoplan routes to them (they are themselves
# `front-door`); a skill *they* select is `lifecycle` (DESIGN-036).
LIFECYCLE_SKILLS: frozenset[str] = frozenset({"spec", "plan", "build", "test", "review", "ship"})

RESERVED_INVOKERS: frozenset[str] = frozenset({"user", "harness"})

ROUTING_KEYS: tuple[str, ...] = (
    "role",
    "invoker",
    "trigger",
    "user-facing",
    "scenario",
    "rationale",
    "replaced-by",
    "removal-issue",
    "intents",
)


@dataclass(frozen=True)
class SkillDecl:
    """One skill's best-effort parsed routing declaration.

    Fields hold ``None`` when the corresponding block value is absent or the
    wrong type; the shape defect itself is recorded separately by
    :func:`_block_defects` so a malformed field is never silently
    indistinguishable from an absent one. ``scenario`` always holds a usable
    path: the declared override when valid, otherwise the REQ-038 default.
    """

    name: str
    path: str
    role: str | None
    invoker: str | None
    replaced_by: str | None
    scenario: str

