"""Fetching main's testmon database: the accepted path and the refusals (issue #6239)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.validation.testmon_seed_helpers import (
    DATABASE,
    FakeGh,
    artifact_entry,
    make_routes,
    make_run,
    make_zip,
    write_inputs,
)


def test_a_matching_main_push_artifact_is_written(tmp_path: Path) -> None:
    write_inputs(tmp_path)
    gh = FakeGh(
        make_routes(
            [make_run(7)], {7: [artifact_entry(tmp_path)]}, make_zip({".testmondata": DATABASE})
        )
    )
    result = gh.fetch(tmp_path)
    assert result.seeded, result.detail
    assert (tmp_path / ".testmondata").read_bytes() == DATABASE
    assert not list(tmp_path.glob("*.tmp"))


def test_the_newest_run_with_the_key_is_chosen_and_the_query_is_main_push_only(
    tmp_path: Path,
) -> None:
    write_inputs(tmp_path)
    other = [{"id": 1, "name": "other", "expired": False}]
    listing = {8: other, 7: [artifact_entry(tmp_path)]}
    gh = FakeGh(
        make_routes([make_run(8), make_run(7)], listing, make_zip({".testmondata": DATABASE}))
    )
    assert gh.fetch(tmp_path).seeded
    assert "event=push" in gh.calls[0]
    assert "branch=main" in gh.calls[0]
    assert [c.split("/")[-2] for c in gh.calls if c.endswith("/artifacts")] == ["8", "7"]


@pytest.mark.parametrize(
    "run",
    [
        make_run(7, event="pull_request"),
        make_run(7, branch="topic"),
        make_run(7, repo="fork/ai-agents"),
    ],
    ids=["pull-request", "other-branch", "fork"],
)
def test_an_untrusted_run_is_never_listed_or_downloaded(tmp_path: Path, run: dict) -> None:
    write_inputs(tmp_path)
    gh = FakeGh(
        make_routes([run], {7: [artifact_entry(tmp_path)]}, make_zip({".testmondata": DATABASE}))
    )
    assert not gh.fetch(tmp_path).seeded
    assert not (tmp_path / ".testmondata").exists()
    assert not any("/runs/7/" in call or "/zip" in call for call in gh.calls)


def test_a_key_mismatch_finds_no_artifact(tmp_path: Path) -> None:
    write_inputs(tmp_path)
    stale = artifact_entry(tmp_path, name="testmon-db-" + "0" * 64)
    gh = FakeGh(make_routes([make_run(7)], {7: [stale]}, make_zip({".testmondata": DATABASE})))
    result = gh.fetch(tmp_path)
    assert not result.seeded
    assert "no main push run" in result.detail


def test_an_existing_database_is_never_replaced_and_nothing_is_fetched(tmp_path: Path) -> None:
    write_inputs(tmp_path)
    (tmp_path / ".testmondata").write_bytes(b"mine")
    gh = FakeGh({})
    assert not gh.fetch(tmp_path).seeded
    assert (tmp_path / ".testmondata").read_bytes() == b"mine"
    assert gh.calls == []
