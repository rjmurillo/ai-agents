"""codeql-analysis.yml trigger contract (issue #5636, decision D12).

CodeQL scans the whole tree per language, so a path filter cannot prove a change
left the verdict alone. The pull request path filter stays, because it is what
lets the required check report on every PR. The merge queue and a nightly
schedule always run the full analysis, so a skipped PR run cannot hide a
finding for longer than a day.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github/workflows/codeql-analysis.yml"
PATHS_FILTER_ACTION = "dorny/paths-filter@"
SHA_PIN = re.compile(r"^[^@\s]+@[0-9a-f]{40}$")


def _document() -> Any:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _triggers() -> Any:
    """YAML 1.1 reads the bare key ``on`` as boolean True, so try both."""
    document = _document()
    return document["on"] if "on" in document else document[True]


def _steps(job: str) -> list[dict[str, Any]]:
    return _document()["jobs"][job]["steps"]


def test_merge_group_trigger_is_present() -> None:
    assert "merge_group" in _triggers()


def test_schedule_trigger_is_nightly_not_weekly() -> None:
    schedules = _triggers()["schedule"]
    assert len(schedules) == 1
    minute, hour, day_of_month, month, day_of_week = schedules[0]["cron"].split()
    assert (day_of_month, month, day_of_week) == ("*", "*", "*")
    assert minute.isdigit()
    assert hour.isdigit()


def test_schedule_is_not_the_old_weekly_cron() -> None:
    """Negative control: the pre-#5636 value ran once a week."""
    assert _triggers()["schedule"][0]["cron"] != "0 9 * * 1"


def test_pull_request_trigger_has_no_trigger_level_paths() -> None:
    """A trigger-level ``paths:`` would skip the workflow and its required check."""
    assert "paths" not in _triggers()["pull_request"]


def test_pr_path_filter_is_kept() -> None:
    filters = [
        step
        for step in _steps("check-paths")
        if str(step.get("uses", "")).startswith(PATHS_FILTER_ACTION)
    ]
    assert len(filters) == 1
    assert "scannable" in yaml.safe_load(filters[0]["with"]["filters"])


@pytest.mark.parametrize("event", ["schedule", "merge_group"])
def test_full_run_events_bypass_the_path_filter(event: str) -> None:
    determine = next(step for step in _steps("check-paths") if step.get("id") == "determine")
    forced = {e.strip() for e in determine["env"]["FORCE_RUN_EVENTS"].split(",")}
    assert event in forced


def test_path_filter_step_is_skipped_for_the_full_run_events() -> None:
    step = next(
        s for s in _steps("check-paths") if str(s.get("uses", "")).startswith(PATHS_FILTER_ACTION)
    )
    condition = step["if"]
    assert "schedule" in condition
    assert "merge_group" in condition


def test_every_action_reference_is_pinned_to_a_40_hex_sha() -> None:
    unpinned = [
        step["uses"]
        for job in _document()["jobs"].values()
        for step in job["steps"]
        if "uses" in step
        and not step["uses"].startswith("./")  # a local action is the same commit
        and not SHA_PIN.match(step["uses"].split()[0])
    ]
    assert unpinned == []


def test_docs_describe_the_nightly_schedule() -> None:
    text = (REPO_ROOT / "docs/codeql-integration.md").read_text(encoding="utf-8")
    cron = _triggers()["schedule"][0]["cron"]
    assert f"cron `{cron}`" in text
    assert "0 9 * * 1" not in text
