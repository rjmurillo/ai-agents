"""Scenario-file rules of the ADR-127 evidence check.

Reads ``tests/evals/<name>-scenarios.json`` at head and at the merge base:
the file must parse, stay frozen after the first commit that touches the
skill, keep every kept scenario's label, and name a replacing test for each
scenario it drops. ``check_skill_rewrite_evidence.py`` owns the gate.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from skill_rewrite_context import EVIDENCE_ROOT, RETIRED_FILE, Context
from skill_rewrite_skills import _SKILL_DIRS, defines_test


def _freeze_findings(ctx: Context, name: str, scenario_path: str) -> list[str]:
    surface = (
        f"templates/skills/{name}.SKILL.md.tmpl",
        *(f"{d.format(n=name)}/" for d in _SKILL_DIRS),
    )
    last_scenario = first_surface = None
    for index, commit in enumerate(ctx.commits):
        files = ctx.changes(commit)
        if scenario_path in files:
            last_scenario = index
        if first_surface is None and any(f.startswith(surface) for f in files):
            first_surface = index
    if last_scenario is not None and first_surface is not None and last_scenario >= first_surface:
        return [
            f"{scenario_path} changes in or after the first commit that touches the skill; "
            "scenarios land in their own earlier commit and stay frozen"
        ]
    return []


def scenario_rows(data: bytes) -> list[dict[str, Any]] | None:
    """The scenario rows, each a mapping with an ``id``, or None when the file is not that."""
    try:
        parsed = json.loads(data)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    rows = parsed.get("scenarios") if isinstance(parsed, dict) else None
    if not isinstance(rows, list) or not all(isinstance(r, dict) and "id" in r for r in rows):
        return None
    return rows


def _retired_findings(ctx: Context, name: str, dropped: list[str]) -> list[str]:
    if not dropped:
        return []
    path = f"{EVIDENCE_ROOT}/{name}/{RETIRED_FILE}"
    if path not in ctx.git.files(ctx.head, path):
        return [f"scenarios {dropped} were dropped and {path} does not exist"]
    try:
        rows = json.loads(ctx.git.blob(ctx.head, path)).get("retired")
    except (json.JSONDecodeError, UnicodeDecodeError, AttributeError):
        rows = None
    if not isinstance(rows, list):
        return [f"{path} is not valid JSON with a 'retired' list"]
    tests = {r.get("scenario"): r.get("test") for r in rows if isinstance(r, dict)}
    problems = []
    for sid in dropped:
        test = tests.get(sid)
        if not isinstance(test, str) or "::" not in test:
            problems.append(f"dropped scenario {sid} has no replacing test in {path}")
            continue
        test_path, *classes, func = test.split("::")
        found = test_path in ctx.git.files(ctx.head, test_path)
        text = ctx.git.blob(ctx.head, test_path).decode("utf-8", "replace") if found else ""
        if not (found and defines_test(text, classes, func)):
            problems.append(f"dropped scenario {sid}: test {test} does not exist at HEAD")
    return problems


def _label_findings(base: list[dict[str, Any]], head: list[dict[str, Any]]) -> list[str]:
    """A kept scenario may not change its label (ADR-127 decision 7 item 10)."""
    before = {str(r["id"]): str(r.get("expected_verdict")).strip().upper() for r in base}
    return [
        f"scenario {s['id']} changes expected_verdict from {before[str(s['id'])]!r} "
        f"to {s['expected_verdict']!r}; a kept scenario's label may not change"
        for s in head
        if str(s["id"]) in before
        and before[str(s["id"])] != str(s["expected_verdict"]).strip().upper()
    ]


@dataclass
class Scenarios:
    path: str
    data: bytes
    rows: list[dict[str, Any]]


def load_scenarios(ctx: Context, name: str) -> tuple[Scenarios | None, list[str]]:
    """The head scenario file, plus findings against the merge base."""
    path = f"tests/evals/{name}-scenarios.json"
    if path not in ctx.git.files(ctx.head, path):
        return None, [f"{path} does not exist; a gated skill needs a scenario file"]
    data = ctx.git.blob(ctx.head, path)
    rows = scenario_rows(data)
    if rows is None:
        return None, [f"{path} is not valid scenario JSON with an id on every scenario"]
    if not all("expected_verdict" in r for r in rows):
        return None, [f"{path} has a scenario with no expected_verdict"]
    problems = _freeze_findings(ctx, name, path)
    if path in ctx.git.files(ctx.merge_base, path):
        base = scenario_rows(ctx.git.blob(ctx.merge_base, path))
        if base is None:
            return None, [
                f"{path} does not parse at the merge base, so dropped scenarios and "
                "label changes cannot be checked"
            ]
        head_ids = {str(r["id"]) for r in rows}
        dropped = [str(r["id"]) for r in base if str(r["id"]) not in head_ids]
        problems += _retired_findings(ctx, name, dropped)
        problems += _label_findings(base, rows)
    return Scenarios(path, data, rows), problems
