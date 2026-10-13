"""Aggregation and reporting for the adr-review catch-rate harness (issue #5248).

Pure functions over trial rows: Wilson intervals, per-(arm, role) rates, the
panel union, and the markdown report. Kept apart from corpus and scoring code
in `_adr_catch_rate_core.py` so each module stays under the taste file-size
limit.
"""

from __future__ import annotations

import math
from typing import Any

from _adr_catch_rate_core import ARMS, ROLES


def wilson_interval(hits: int, total: int, z: float = 1.96) -> tuple[float, float]:
    """95 percent Wilson score interval. Defined as (0, 1) with no trials."""
    if total <= 0:
        return (0.0, 1.0)
    p = hits / total
    denom = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denom
    half = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def _rate(hits: int, total: int) -> dict[str, Any]:
    low, high = wilson_interval(hits, total)
    return {
        "hits": hits,
        "n": total,
        "rate": (hits / total) if total else None,
        "ci95": [round(low, 4), round(high, 4)],
    }


def aggregate(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Roll trial rows up to a rate per (arm, role).

    A row is {entry, arm, role, trial, flagged, blocked, error}. An errored
    trial counts toward `errors`, never toward `n`, so a failing provider
    cannot lower a rate by looking like a miss.
    """
    cells: dict[tuple[str, str], dict[str, int]] = {}
    for row in results:
        tally = cells.setdefault((row["arm"], row["role"]), {"n": 0, "f": 0, "b": 0, "e": 0})
        if row.get("error"):
            tally["e"] += 1
            continue
        tally["n"] += 1
        tally["f"] += 1 if row["flagged"] else 0
        tally["b"] += 1 if row["blocked"] else 0
    table: dict[str, dict[str, Any]] = {}
    for (arm, role), tally in sorted(cells.items()):
        table.setdefault(arm, {})[role] = {
            "flagged": _rate(tally["f"], tally["n"]),
            "blocked": _rate(tally["b"], tally["n"]),
            "errors": tally["e"],
        }
    return table


def panel_union(results: list[dict[str, Any]], arm: str) -> dict[str, Any]:
    """Share of entries at least one role caught, per strength, for one arm."""
    caught: dict[str, dict[str, bool]] = {}
    for row in results:
        if row["arm"] != arm or row.get("error"):
            continue
        entry = caught.setdefault(row["entry"], {"flagged": False, "blocked": False})
        entry["flagged"] = entry["flagged"] or bool(row["flagged"])
        entry["blocked"] = entry["blocked"] or bool(row["blocked"])
    total = len(caught)
    return {
        "flagged": _rate(sum(1 for c in caught.values() if c["flagged"]), total),
        "blocked": _rate(sum(1 for c in caught.values() if c["blocked"]), total),
    }


def _pct(cell: dict[str, Any]) -> str:
    if cell["rate"] is None:
        return "n/a"
    low, high = cell["ci95"]
    return f"{cell['hits']}/{cell['n']} ({cell['rate']:.0%}, CI {low:.0%} to {high:.0%})"


def _role_row(role: str, cell: dict[str, Any]) -> str:
    flagged, blocked = _pct(cell["flagged"]), _pct(cell["blocked"])
    return f"| {role} | {flagged} | {blocked} | {cell['errors']} |"


def _arm_section(arm: str, roles: dict[str, Any], union: dict[str, Any] | None) -> list[str]:
    lines = [f"## Arm: {arm}", "", "| Role | Flagged | Blocked | Errors |", "|---|---|---|---|"]
    lines += [_role_row(role, roles[role]) for role in ROLES if role in roles]
    if union:
        lines.append(f"| any role | {_pct(union['flagged'])} | {_pct(union['blocked'])} | |")
    return lines + [""]


def render_report(table: dict[str, Any], unions: dict[str, Any], meta: dict[str, Any]) -> str:
    lines = [
        "# adr-review catch rate",
        "",
        f"Model: {meta.get('model', 'unknown')}. Trials per cell: {meta.get('trials', 'unknown')}. "
        f"Entries: {meta.get('entries', 'unknown')}.",
        "",
    ]
    for arm in ARMS:
        if arm in table:
            lines += _arm_section(arm, table[arm], unions.get(arm))
    return "\n".join(lines)
