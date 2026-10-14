#!/usr/bin/env python3
"""Route-change gate: a new or changed autoplan route ships a scenario (issue #6291).

`check_shipped_skill_routes.py` proves that every routed skill ships.
`check_rule_activation_coverage.py` stops the exemption baseline from growing.
Neither looks at a route change. A PR can add a row to the autoplan routing
table, or send an existing row somewhere else, and merge with no scenario that
would catch a model routing the request wrongly.

This gate closes that gap. It compares the `Intent | Route` table in the
autoplan SKILL.md at the merge base with the working tree. For each row that
is new or whose route text changed, it requires an edited scenario in
`tests/evals/skill-scenarios/autoplan.json` whose `expected_route` names a
target of that row. The failure message names the row and the targets a
scenario must cover.

Definitions
-----------

- Route row: a row of a table whose header is exactly `Intent | Route`.
- Targets: the names after `Skill:`, `Agent:` and `subagent_type="..."` in the
  route cell, in order. A cell with none of those falls back to its `/command`
  names (`/ship`). A cell with no targets at all, such as "Lifecycle chain per
  size tier above", is satisfied by any edited scenario.
- Changed row: a head row whose (intent, route text) pair is absent from the
  base. A row is a rename, not a route change, only when its intent is new to
  the table and its route text equals that of a removed base row whose intent
  no longer appears at head. Merging two rows or swapping two routes is a
  route change.
- Edited scenario: a scenario id absent from the base, or one whose `input`,
  `expected_route`, `expected_gate`, `expected_signals` or `forbidden_routes`
  differ from the base. A rationale or description edit does not count.

Removing a row is not a route change here. Removing a skill is caught by the
shipped-route and orphan-scenario gates.

Fail-closed: a missing file, a missing or renamed route table, malformed JSON,
or an unresolvable base ref exits 2. A gate that read nothing never passes.

Usage:
    python3 scripts/validation/check_route_scenario_coverage.py
    python3 scripts/validation/check_route_scenario_coverage.py --base-ref origin/main

Exit codes (ADR-035):
  0  no route changed, or every changed route has an edited scenario.
  1  a new or changed route has no matching edited scenario.
  2  config error: unresolvable ref, missing file, no route table, bad JSON.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.utils.markdown_parser import parse_tables

EXIT_OK = 0
EXIT_UNCOVERED = 1
EXIT_CONFIG = 2

SKILL_PATH = ".claude/skills/autoplan/SKILL.md"
SCENARIO_PATH = "tests/evals/skill-scenarios/autoplan.json"
DEFAULT_BASE_REF = "origin/main"
ROUTE_TABLE_HEADERS = ["Intent", "Route"]
SCENARIO_FIELDS = (
    "input",
    "expected_route",
    "expected_gate",
    "expected_signals",
    "forbidden_routes",
)

_PREFIXED_TARGET_RE = re.compile(r"\b(?:Skill|Agent):\s*`?([a-z][a-z0-9-]*)")
_SUBAGENT_RE = re.compile(r"subagent_type\s*=\s*\"([a-z][a-z0-9-]*)\"")
_COMMAND_RE = re.compile(r"(?<![\w/])/([a-z][a-z0-9-]*)")
_SPACE_RE = re.compile(r"\s+")


class CoverageConfigError(Exception):
    """An input is missing or malformed, so the gate cannot decide."""


@dataclass(frozen=True)
class RouteRow:
    """One row of the autoplan `Intent | Route` table."""

    intent: str
    route: str
    targets: tuple[str, ...]


def _normalize(text: str) -> str:
    return _SPACE_RE.sub(" ", text).strip()


def _dedupe(names: list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(names))


def extract_targets(route: str) -> tuple[str, ...]:
    """Return the skills, agents and commands a route cell sends the request to."""
    named = _PREFIXED_TARGET_RE.findall(route) + _SUBAGENT_RE.findall(route)
    if named:
        return _dedupe(named)
    return _dedupe(_COMMAND_RE.findall(route))


def parse_route_rows(markdown: str) -> list[RouteRow]:
    """Return every row of every `Intent | Route` table, in document order."""
    rows: list[RouteRow] = []
    for table in parse_tables(markdown):
        if table.headers != ROUTE_TABLE_HEADERS:
            continue
        for row in table.rows:
            intent, route = _normalize(row.cells[0]), _normalize(row.cells[1])
            rows.append(RouteRow(intent, route, extract_targets(route)))
    return rows


def changed_rows(base: list[RouteRow], head: list[RouteRow]) -> list[RouteRow]:
    """Return head rows that are new or whose route text changed.

    A reworded intent with an unchanged route is paired with its removed base
    row and dropped, so a wording edit does not demand a scenario. A pairing
    needs both ends to be a true rename: the head intent is new to the table,
    and the removed base intent is gone from the head. Without that, merging two
    rows or swapping two routes would pair a changed row with a deleted or
    moved one and hide a real route change.
    """
    base_pairs = {(r.intent, r.route) for r in base}
    head_pairs = {(r.intent, r.route) for r in head}
    base_intents = {r.intent for r in base}
    head_intents = {r.intent for r in head}
    renamable = Counter(
        r.route
        for r in base
        if (r.intent, r.route) not in head_pairs and r.intent not in head_intents
    )
    changed: list[RouteRow] = []
    for row in head:
        if (row.intent, row.route) in base_pairs:
            continue
        if row.intent not in base_intents and renamable[row.route] > 0:
            renamable[row.route] -= 1
            continue
        changed.append(row)
    return changed


def _scenario_map(text: str, label: str) -> dict[str, dict[str, Any]]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise CoverageConfigError(f"{label} is not valid JSON: {exc}") from exc
    scenarios = data.get("scenarios") if isinstance(data, dict) else None
    if not isinstance(scenarios, list):
        raise CoverageConfigError(f"{label} has no 'scenarios' list")
    mapped: dict[str, dict[str, Any]] = {}
    for item in scenarios:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            raise CoverageConfigError(f"{label} has a scenario without a string 'id'")
        mapped[item["id"]] = item
    return mapped


def _scenario_changed(base: dict[str, Any] | None, head: dict[str, Any]) -> bool:
    if base is None:
        return True
    return any(base.get(name) != head.get(name) for name in SCENARIO_FIELDS)


def edited_scenarios(base_text: str | None, head_text: str) -> list[dict[str, Any]]:
    """Return head scenarios that are new or changed in a coverage-bearing field."""
    head = _scenario_map(head_text, SCENARIO_PATH)
    base = _scenario_map(base_text, f"{SCENARIO_PATH} at base") if base_text is not None else {}
    return [item for sid, item in head.items() if _scenario_changed(base.get(sid), item)]


def _expected_names(scenario: dict[str, Any]) -> set[str]:
    raw = scenario.get("expected_route")
    if not isinstance(raw, list):
        return set()
    return {item.split(":", 1)[-1] for item in raw if isinstance(item, str)}


def uncovered_rows(rows: list[RouteRow], edited: list[dict[str, Any]]) -> list[RouteRow]:
    """Return changed rows that no edited scenario's expected_route covers."""
    names = [_expected_names(item) for item in edited]
    missing: list[RouteRow] = []
    for row in rows:
        if not row.targets and edited:
            continue
        if any(set(row.targets) & covered for covered in names):
            continue
        missing.append(row)
    return missing


def _git(repo_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo_root), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def resolve_merge_base(repo_root: Path, base_ref: str) -> str:
    """Return the merge-base commit of `base_ref` and HEAD."""
    if not base_ref or base_ref.startswith("-"):
        raise CoverageConfigError(f"invalid base ref: {base_ref!r}")
    result = _git(repo_root, "merge-base", base_ref, "HEAD")
    sha = result.stdout.strip()
    if result.returncode != 0 or not sha:
        raise CoverageConfigError(
            f"cannot find a merge base between {base_ref!r} and HEAD "
            f"(shallow clone? fetch the base ref): {result.stderr.strip()}"
        )
    return sha


def read_at(repo_root: Path, sha: str, path: str) -> str | None:
    """Return a file's text at a commit, or None when the commit lacks the file."""
    if _git(repo_root, "cat-file", "-e", f"{sha}:{path}").returncode != 0:
        return None
    result = _git(repo_root, "show", f"{sha}:{path}")
    if result.returncode != 0:
        raise CoverageConfigError(f"git show {sha}:{path} failed: {result.stderr.strip()}")
    return result.stdout


def read_head(repo_root: Path, path: str) -> str:
    """Return a working-tree file's text."""
    try:
        return (repo_root / path).read_text(encoding="utf-8")
    except OSError as exc:
        raise CoverageConfigError(f"cannot read {path}: {exc}") from exc


def _format_failure(row: RouteRow) -> str:
    covers = ", ".join(row.targets) if row.targets else "any route"
    return (
        f'ERROR: route "{row.intent}" -> {row.route}\n'
        f"  is new or changed with no edited scenario. Add or update a scenario in "
        f"{SCENARIO_PATH}\n  whose expected_route includes: {covers}"
    )


def run(repo_root: Path, base_ref: str) -> int:
    """Compare routes and scenarios against the merge base and return an exit code."""
    sha = resolve_merge_base(repo_root, base_ref)
    head_rows = parse_route_rows(read_head(repo_root, SKILL_PATH))
    if not head_rows:
        raise CoverageConfigError(
            f"{SKILL_PATH} has no 'Intent | Route' table; the gate would check nothing"
        )
    base_skill = read_at(repo_root, sha, SKILL_PATH)
    base_rows = parse_route_rows(base_skill) if base_skill is not None else []
    changed = changed_rows(base_rows, head_rows)
    if not changed:
        print(f"[PASS] no autoplan route added or changed since {sha[:12]}")
        return EXIT_OK
    base_scenarios = read_at(repo_root, sha, SCENARIO_PATH)
    edited = edited_scenarios(base_scenarios, read_head(repo_root, SCENARIO_PATH))
    missing = uncovered_rows(changed, edited)
    for row in missing:
        print(_format_failure(row), file=sys.stderr)
    if missing:
        print(
            f"[FAIL] {len(missing)} of {len(changed)} changed routes lack a scenario",
            file=sys.stderr,
        )
        return EXIT_UNCOVERED
    print(f"[PASS] {len(changed)} changed routes each have an edited scenario")
    return EXIT_OK


def _resolve_repo_root(explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit.resolve()
    return Path(__file__).resolve().parents[2]


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo-root", type=Path, default=None)
    parser.add_argument("--base-ref", default=DEFAULT_BASE_REF)
    args = parser.parse_args(argv)
    try:
        return run(_resolve_repo_root(args.repo_root), args.base_ref)
    except CoverageConfigError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_CONFIG


if __name__ == "__main__":
    sys.exit(main())
