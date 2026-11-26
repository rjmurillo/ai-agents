"""Scenario-file rules of the ADR-127 evidence check.

Reads ``tests/evals/<name>-scenarios.json`` at head and at the merge base:
the file must parse, stay frozen after the first commit that touches the
skill, keep every kept scenario's label, and name a replacing test for each
scenario it drops. ``check_skill_rewrite_evidence.py`` owns the gate.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from typing import Any

from skill_rewrite_context import EVIDENCE_ROOT, RETIRED_FILE, Context
from skill_rewrite_skills import _SKILL_DIRS, PYTEST_FILE_GLOB, defines_test, is_collected_file


def _touches_surface(files: dict[str, str], name: str) -> bool:
    """True when a commit's paths hold the skill's template or anything under its skill dirs."""
    template = f"templates/skills/{name}.SKILL.md.tmpl"
    dirs = tuple(f"{d.format(n=name)}/" for d in _SKILL_DIRS)
    return any(f == template or f.startswith(dirs) for f in files)


def _freeze_findings(ctx: Context, name: str, scenario_path: str) -> list[str]:
    """Scenarios land before the skill changes and stay frozen, whatever the commit order.

    Two invariants hold for every commit in ``merge_base..head``. No commit
    changes the scenario file and the skill surface together. Every commit
    that touches the surface holds the scenario blob that head holds, or
    lacks the file exactly when head lacks it. A later edit fails the second;
    so does a merge that restores an older corpus after the skill changed.
    """
    head_blobs = ctx.git.tree_blobs(ctx.head, scenario_path)
    problems = []
    for commit in ctx.commits:
        files = ctx.changes(commit)
        if not _touches_surface(files, name):
            continue
        if scenario_path in files:
            problems.append(
                f"{scenario_path} changes in the same commit as the skill ({commit[:10]}); "
                "scenarios land in their own earlier commit and stay frozen"
            )
        elif ctx.git.tree_blobs(commit, scenario_path) != head_blobs:
            problems.append(
                f"{scenario_path} differs at {commit[:10]}, a commit that touches the skill; "
                "scenarios must land before the skill changes and stay frozen"
            )
    return problems


def scenario_rows(data: bytes) -> list[dict[str, Any]] | None:
    """The scenario rows, each a mapping with an ``id``, or None when the file is not that.

    Mirrors ``load_scenarios`` in ``scripts/eval/eval-prompt-change.py``, which
    reads ``data.get("scenarios", data) if isinstance(data, dict) else data``.
    A top-level array is a corpus, so the check hashes and verifies the same
    file the runner accepted. The runner also rejects an empty list and
    rows missing fields; ``load_scenarios`` applies those checks through the
    runner's own ``parse_scenarios``.
    """
    try:
        parsed = json.loads(data)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    rows = parsed.get("scenarios", parsed) if isinstance(parsed, dict) else parsed
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
    dict_rows = [r for r in rows if isinstance(r, dict)]
    problems = [
        f"{path} has a retired row whose scenario id {r.get('scenario')!r} is not a string"
        for r in dict_rows
        if not isinstance(r.get("scenario"), str)
    ]
    tests = {r["scenario"]: r.get("test") for r in dict_rows if isinstance(r.get("scenario"), str)}
    for sid in dropped:
        test = tests.get(sid)
        if not isinstance(test, str) or "::" not in test:
            problems.append(f"dropped scenario {sid} has no replacing test in {path}")
            continue
        problem = _retired_test_problem(ctx, test)
        if problem:
            problems.append(f"dropped scenario {sid}: test {test} {problem}")
    return problems


def _retired_test_problem(ctx: Context, test: str) -> str | None:
    """Why *test* cannot replace a dropped scenario, or None when pytest would run it."""
    if "[" in test:
        return "names a parameter id; name the function without a parameter id"
    test_path, *classes, func = test.split("::")
    if not is_collected_file(test_path):
        return (
            f"is not collected by pytest; the file must be under tests/ and match "
            f"{PYTEST_FILE_GLOB}"
        )
    found = test_path in ctx.git.files(ctx.head, test_path)
    text = ctx.git.blob(ctx.head, test_path).decode("utf-8", "replace") if found else ""
    if not (found and defines_test(text, classes, func)):
        return "does not exist at HEAD"
    return None


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


def _repeated_ids(rows: list[dict[str, Any]]) -> list[str]:
    """Ids used by more than one row, compared as ``str`` as the results check does.

    Results are keyed by that string, so eight rows that share an id would
    be recomputed from one result row and satisfy the scenario floors.
    """
    counts = Counter(str(r["id"]) for r in rows)
    return sorted(sid for sid, n in counts.items() if n > 1)


def load_scenarios(ctx: Context, name: str) -> tuple[Scenarios | None, list[str]]:
    """The head scenario file, plus findings against the merge base."""
    path = f"tests/evals/{name}-scenarios.json"
    if path not in ctx.git.files(ctx.head, path):
        return None, [f"{path} does not exist; a gated skill needs a scenario file"]
    data = ctx.git.blob(ctx.head, path)
    rows = scenario_rows(data)
    if rows is None:
        return None, [f"{path} is not valid scenario JSON with an id on every scenario"]
    repeated = _repeated_ids(rows)
    if repeated:
        return None, [f"{path} repeats scenario ids {repeated}; each scenario needs a distinct id"]
    if not all("expected_verdict" in r for r in rows):
        return None, [f"{path} has a scenario with no expected_verdict"]
    try:
        # The runner's own checks, such as expected_verdict in verdict_options.
        ctx.runner.parse_scenarios(data, path)
    except (RuntimeError, UnicodeDecodeError) as exc:
        return None, [f"{path} fails the eval runner's scenario checks: {exc}"]
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
