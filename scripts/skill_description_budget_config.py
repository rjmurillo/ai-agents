"""Budget file loader for `skill_description_budget.py` (issue #5762, PR #7871).

Parses `scripts/skill_description_budget.json` into typed limits. Any bad shape
raises `BudgetFileError`, which the CLI maps to exit 2.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path


class BudgetFileError(ValueError):
    """The budget file is missing, unparseable, or has an invalid entry."""


@dataclass(frozen=True)
class RootBudget:
    """Limits for one skill root. `max_listing_chars` is optional."""

    max_total_chars: int
    max_listing_chars: int | None = None


@dataclass(frozen=True)
class HostBudget:
    """A published or observed host listing budget, with its evidence state."""

    host: str
    chars: int
    state: str
    source: str
    date: str


@dataclass(frozen=True)
class BudgetConfig:
    """Parsed budget file."""

    roots: dict[str, RootBudget]
    host_budgets: tuple[HostBudget, ...] = ()


def _is_positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _parse_root_budget(root: str, entry: object) -> RootBudget:
    fields = entry if isinstance(entry, dict) else {}
    limit = fields.get("max_total_chars")
    if not isinstance(limit, int) or not _is_positive_int(limit):
        raise BudgetFileError(f"root {root!r} needs a positive integer 'max_total_chars'")
    if "max_listing_chars" not in fields:
        return RootBudget(max_total_chars=limit)
    ceiling = fields["max_listing_chars"]
    if not isinstance(ceiling, int) or not _is_positive_int(ceiling):
        raise BudgetFileError(f"root {root!r} needs a positive integer 'max_listing_chars'")
    return RootBudget(max_total_chars=limit, max_listing_chars=ceiling)


def _parse_host_budget(index: int, entry: object) -> HostBudget:
    where = f"host_budgets[{index}]"
    if not isinstance(entry, dict):
        raise BudgetFileError(f"{where} must be an object")
    for key in ("host", "state", "source", "date"):
        value = entry.get(key)
        if not isinstance(value, str) or not value.strip():
            raise BudgetFileError(f"{where} needs a non-empty string {key!r}")
    if not _is_positive_int(entry.get("chars")):
        raise BudgetFileError(f"{where} needs a positive integer 'chars'")
    try:
        date.fromisoformat(entry["date"])
    except ValueError as exc:
        raise BudgetFileError(f"{where} 'date' must be an ISO date (YYYY-MM-DD)") from exc
    return HostBudget(
        host=entry["host"],
        chars=entry["chars"],
        state=entry["state"],
        source=entry["source"],
        date=entry["date"],
    )


def load_budget_config(path: Path) -> BudgetConfig:
    """Parse a budget file, or raise BudgetFileError on any bad shape."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BudgetFileError(f"cannot read budget file {path}: {exc}") from exc
    roots = data.get("roots") if isinstance(data, dict) else None
    if not isinstance(roots, dict) or not roots:
        raise BudgetFileError(f"budget file {path} needs a non-empty 'roots' object")
    parsed_roots = {root: _parse_root_budget(root, entry) for root, entry in roots.items()}
    raw_hosts = data.get("host_budgets", [])
    if not isinstance(raw_hosts, list):
        raise BudgetFileError(f"budget file {path} 'host_budgets' must be a list")
    hosts = tuple(_parse_host_budget(i, entry) for i, entry in enumerate(raw_hosts))
    return BudgetConfig(roots=parsed_roots, host_budgets=hosts)


def load_root_budgets(path: Path) -> dict[str, int]:
    """Return `{root: max_total_chars}` from a budget file, or raise BudgetFileError."""
    return {root: b.max_total_chars for root, b in load_budget_config(path).roots.items()}
