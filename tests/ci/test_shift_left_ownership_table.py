"""The SHIFT-LEFT job ownership table must list every lefthook job (issue #6734).

``.project-toolkit/devops/SHIFT-LEFT.md`` carries one row per job declared in
``lefthook.yml``, naming the hook that owns the check and the CI counterpart.
A job added to or removed from ``lefthook.yml`` without a matching row leaves
the table describing a hook that no longer exists, which is how the earlier
"46 jobs" and "34 jobs" figures in that document went stale.

Coverage:

- positive: every job in the real ``lefthook.yml`` has exactly one row under its
  own hook, and every row names a real job.
- negative: a job missing from the table, a row for a job that does not exist,
  and a row filed under the wrong hook each fail the comparison.
- edge: jobs nested inside ``group`` blocks are counted; a job declared in both
  hooks needs two rows; the "Also runs at" cell agrees with the config; the
  Security and CI cells hold only declared values.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
_LEFTHOOK = REPO_ROOT / "lefthook.yml"
_DOC = REPO_ROOT / ".project-toolkit" / "devops" / "SHIFT-LEFT.md"
_HEADING = "### Job ownership table"
_HOOKS = ("pre-commit", "pre-push")
_SECURITY_VALUES = {"yes", "adjacent", "no"}
_CI_PREFIXES = (
    "Required:",
    "CI, not required:",
    "None found",
    "Local state",
    "Not mapped",
    "Not applicable",
)


def _walk(jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Flatten a lefthook job list, descending into ``group`` blocks."""
    flat: list[dict[str, Any]] = []
    for job in jobs:
        if "group" in job:
            flat.extend(_walk(job["group"].get("jobs", [])))
        else:
            flat.append(job)
    return flat


def _config_jobs(config: dict[str, Any]) -> dict[str, list[str]]:
    return {hook: [job["name"] for job in _walk(config[hook]["jobs"])] for hook in _HOOKS}


def _table_rows(markdown: str) -> list[dict[str, str]]:
    """Parse the ownership table that follows ``_HEADING`` into one dict per row."""
    lines = markdown.splitlines()
    try:
        start = lines.index(_HEADING)
    except ValueError:
        return []
    header: list[str] = []
    rows: list[dict[str, str]] = []
    for line in lines[start + 1 :]:
        if line.startswith("#"):
            break
        if not line.startswith("|"):
            if rows:
                break
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if not header:
            header = cells
            continue
        if set(line.replace("|", "").strip()) <= {"-", " "}:
            continue
        rows.append(dict(zip(header, cells, strict=True)))
    return rows


def _compare(jobs: dict[str, list[str]], rows: list[dict[str, str]]) -> list[str]:
    """Return one message per mismatch between the config and the table."""
    problems: list[str] = []
    table = Counter((row["Hook"], row["Job"].strip("`")) for row in rows)
    for hook, names in jobs.items():
        for name, count in Counter(names).items():
            if table[(hook, name)] != count:
                problems.append(
                    f"{hook}/{name}: config has {count}, table has {table[(hook, name)]}"
                )
    known = {(hook, name) for hook, names in jobs.items() for name in names}
    for key in sorted(set(table) - known):
        problems.append(f"{key[0]}/{key[1]}: table row has no job in lefthook.yml")
    return problems


@pytest.fixture(scope="module")
def real_jobs() -> dict[str, list[str]]:
    return _config_jobs(yaml.safe_load(_LEFTHOOK.read_text(encoding="utf-8")))


@pytest.fixture(scope="module")
def real_rows() -> list[dict[str, str]]:
    return _table_rows(_DOC.read_text(encoding="utf-8"))


def test_every_lefthook_job_has_exactly_one_row_and_no_row_is_orphaned(real_jobs, real_rows):
    assert real_rows, f"no ownership table found under '{_HEADING}' in {_DOC}"
    assert _compare(real_jobs, real_rows) == []


def test_table_total_matches_the_job_count(real_jobs, real_rows):
    assert len(real_rows) == sum(len(names) for names in real_jobs.values())


def test_security_and_ci_cells_hold_only_declared_values(real_rows):
    for row in real_rows:
        assert row["Security"] in _SECURITY_VALUES, row
        assert row["CI counterpart"].startswith(_CI_PREFIXES), row


def test_also_runs_at_agrees_with_the_config(real_jobs, real_rows):
    for row in real_rows:
        hook, name = row["Hook"], row["Job"].strip("`")
        other = "pre-push" if hook == "pre-commit" else "pre-commit"
        expected = other if name in real_jobs[other] else "-"
        assert row["Also runs at"] == expected, row


def test_a_job_missing_from_the_table_is_reported(real_jobs, real_rows):
    trimmed = [
        row
        for row in real_rows
        if not (row["Hook"] == "pre-push" and row["Job"] == "`security-scan`")
    ]
    assert _compare(real_jobs, trimmed) == ["pre-push/security-scan: config has 1, table has 0"]


def test_a_row_for_a_job_that_does_not_exist_is_reported(real_jobs, real_rows):
    extra = [*real_rows, {"Hook": "pre-push", "Job": "`no-such-job`"}]
    assert _compare(real_jobs, extra) == [
        "pre-push/no-such-job: table row has no job in lefthook.yml"
    ]


def test_a_row_filed_under_the_wrong_hook_is_reported(real_jobs, real_rows):
    moved = [
        {**row, "Hook": "pre-commit"}
        if (row["Hook"] == "pre-push" and row["Job"] == "`mutation-safety`")
        else row
        for row in real_rows
    ]
    problems = _compare(real_jobs, moved)
    assert "pre-push/mutation-safety: config has 1, table has 0" in problems
    assert "pre-commit/mutation-safety: table row has no job in lefthook.yml" in problems


def test_a_job_declared_in_both_hooks_needs_two_rows(real_jobs, real_rows):
    shared = set(real_jobs["pre-commit"]) & set(real_jobs["pre-push"])
    assert {"repo-health", "repair-packed-refs", "branch-context-policy"} <= shared
    one_row_short = [
        row
        for row in real_rows
        if not (row["Hook"] == "pre-push" and row["Job"] == "`repo-health`")
    ]
    assert _compare(real_jobs, one_row_short) == ["pre-push/repo-health: config has 1, table has 0"]


def test_jobs_inside_groups_are_flattened():
    config = {
        "pre-commit": {
            "jobs": [{"name": "a"}, {"group": {"jobs": [{"name": "b"}, {"name": "c"}]}}]
        },
        "pre-push": {"jobs": [{"group": {"jobs": [{"group": {"jobs": [{"name": "d"}]}}]}}]},
    }
    assert _config_jobs(config) == {"pre-commit": ["a", "b", "c"], "pre-push": ["d"]}


def test_a_missing_heading_yields_no_rows():
    assert _table_rows("# Title\n\n| Hook | Job |\n|---|---|\n| pre-push | `x` |\n") == []


def test_the_heading_text_is_present_once():
    assert (
        len(re.findall(rf"^{re.escape(_HEADING)}$", _DOC.read_text(encoding="utf-8"), re.MULTILINE))
        == 1
    )
