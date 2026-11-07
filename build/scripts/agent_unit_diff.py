"""Unit-level comparison helpers for check_agent_source_parity.py (issue #5688).

A unit is one comparable piece of an agent member: a frontmatter key, the
preamble, an H2 section, or a capability set. These helpers decide which units
two members disagree on and return a digest per disagreement.
"""

from __future__ import annotations

import hashlib

# H2 sections that exist only in a Claude template by design (the Claude Code
# tool list, GENERATOR-FILES.md). One-sided, they are not a divergence.
CLAUDE_ONLY_SECTIONS: frozenset[str] = frozenset({"section:Claude Code Tools"})


def digest(left: str, right: str) -> str:
    return hashlib.sha256(f"{left}\0{right}".encode()).hexdigest()


def diverged_units(
    left: dict[str, str],
    right: dict[str, str],
    *,
    strict: bool,
    left_only_ok: frozenset[str] = frozenset(),
) -> dict[str, str]:
    """Return ``{unit: digest}`` for each unit the two members disagree on.

    A section on one side only counts only when ``strict`` is set. A unit named
    in ``left_only_ok`` is exempt only when it sits on the left and is missing
    from the right, so a shared section the left side dropped still counts. The
    preamble and the frontmatter keys count in every pair.
    """
    found: dict[str, str] = {}
    for unit in sorted(set(left) | set(right)):
        one_sided = unit not in left or unit not in right
        if unit in left_only_ok and unit in left and unit not in right:
            continue
        if one_sided and not strict and unit.startswith("section:"):
            continue
        a, b = left.get(unit, ""), right.get(unit, "")
        if one_sided or a != b:
            found[unit] = digest(a, b)
    return found


def section_order_divergence(left: dict[str, str], right: dict[str, str]) -> dict[str, str]:
    """Return ``{"order": digest}`` when shared sections appear in a different order."""
    both = [u for u in left if u.startswith("section:") and u in right]
    in_right = [u for u in right if u in set(both)]
    if both == in_right:
        return {}
    return {"order": digest("\n".join(both), "\n".join(in_right))}
