"""The seed lookup pages through runs and keeps git inside the shared deadline (issue #6239)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from scripts.validation import testmon_seed_gh as gh_module
from scripts.validation import testmon_seed_runs as runs_module
from scripts.validation import testmon_seed_trust as trust
from tests.validation.testmon_seed_helpers import (
    DATABASE,
    FakeGh,
    artifact_entry,
    make_run,
    make_zip,
    write_inputs,
)


def _paged_gh(root: Path, pages: dict[int, list[dict]], hit_run: int | None) -> FakeGh:
    """Runs split by page; only ``hit_run`` has the artifact."""
    routes: dict[str, bytes | int] = {}
    for number in sorted(pages, reverse=True):
        routes[f"&page={number}"] = json.dumps({"workflow_runs": pages[number]}).encode()
    for runs in pages.values():
        for run in runs:
            listing = [artifact_entry(root)] if run["id"] == hit_run else []
            routes[f"/runs/{run['id']}/artifacts"] = json.dumps({"artifacts": listing}).encode()
    return FakeGh(routes, zip_bytes=make_zip({".testmondata": DATABASE}))


def test_an_older_seed_behind_a_full_page_of_seedless_runs_is_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_inputs(tmp_path)
    monkeypatch.setattr(runs_module, "RUNS_PER_PAGE", 2)
    gh = _paged_gh(tmp_path, {1: [make_run(9), make_run(8)], 2: [make_run(7)]}, hit_run=7)
    assert gh.fetch(tmp_path).seeded
    assert sum("&page=" in call for call in gh.calls) == 2


def test_paging_stops_at_a_short_page_and_at_the_page_cap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_inputs(tmp_path)
    monkeypatch.setattr(runs_module, "RUNS_PER_PAGE", 1)
    short = _paged_gh(tmp_path, {1: []}, hit_run=None)
    assert not short.fetch(tmp_path).seeded
    assert sum("&page=" in call for call in short.calls) == 1
    pages = {n: [make_run(100 + n)] for n in range(1, runs_module.MAX_RUN_PAGES + 3)}
    capped = _paged_gh(tmp_path, pages, hit_run=None)
    assert not capped.fetch(tmp_path).seeded
    assert sum("&page=" in call for call in capped.calls) == runs_module.MAX_RUN_PAGES


def test_every_git_check_draws_on_the_one_shared_deadline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_inputs(tmp_path)
    clock = {"now": 100.0}
    monkeypatch.setattr(gh_module.time, "monotonic", lambda: clock["now"])
    budgets: list[float] = []

    def has_origin_main(_root: Path, timeout: float) -> bool:
        budgets.append(timeout)
        clock["now"] += 12.0
        return True

    def ancestor(_root: Path, _sha: str, timeout: float) -> bool:
        budgets.append(timeout)
        clock["now"] += 12.0
        return False

    gh = _paged_gh(tmp_path, {1: [make_run(9), make_run(8), make_run(7)]}, hit_run=None)
    result = gh.fetch(
        tmp_path, ancestor=ancestor, has_origin_main=has_origin_main, timeout_seconds=30.0
    )
    assert not result.seeded
    assert budgets == [pytest.approx(30.0), pytest.approx(18.0), pytest.approx(6.0)]
    assert "deadline" in result.detail


@pytest.mark.parametrize("function", ["origin_main_present", "is_main_ancestor"])
def test_the_git_timeout_is_the_smaller_of_the_default_and_what_remains(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, function: str
) -> None:
    seen: list[float] = []

    def fake_run(command: list[str], **kwargs: float) -> subprocess.CompletedProcess[bytes]:
        seen.append(kwargs["timeout"])
        return subprocess.CompletedProcess(command, 0, b"", b"")

    monkeypatch.setattr(trust.subprocess, "run", fake_run)
    call = getattr(trust, function)
    args = (tmp_path, "a" * 40) if function == "is_main_ancestor" else (tmp_path,)
    call(*args, 2.5)
    call(*args, 99.0)
    call(*args)
    assert seen == [2.5, trust.GIT_TIMEOUT_SECONDS, trust.GIT_TIMEOUT_SECONDS]
