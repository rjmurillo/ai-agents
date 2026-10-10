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

GOOD_ZIP = make_zip({".testmondata": DATABASE})


def _gh(root: Path, runs: list[dict], listing: dict[int, list[dict]] | None = None) -> FakeGh:
    artifacts = listing if listing is not None else {7: [artifact_entry(root)]}
    return FakeGh(make_routes(runs, artifacts), zip_bytes=GOOD_ZIP)


def test_a_matching_main_push_artifact_is_written_and_the_staging_dir_removed(
    tmp_path: Path,
) -> None:
    write_inputs(tmp_path)
    gh = _gh(tmp_path, [make_run(7)])
    result = gh.fetch(tmp_path)
    assert result.seeded, result.detail
    assert (tmp_path / ".testmondata").read_bytes() == DATABASE
    assert not list(tmp_path.glob("*.tmp"))
    assert not gh.downloads[0].parent.exists()


def test_the_newest_run_with_the_key_is_chosen_and_the_query_is_main_push_only(
    tmp_path: Path,
) -> None:
    write_inputs(tmp_path)
    other = [{"id": 1, "name": "other", "expired": False}]
    gh = _gh(tmp_path, [make_run(8), make_run(7)], {8: other, 7: [artifact_entry(tmp_path)]})
    assert gh.fetch(tmp_path).seeded
    assert "event=push" in gh.calls[0]
    assert "branch=main" in gh.calls[0]
    assert [c.split("/")[-2] for c in gh.calls if c.endswith("/artifacts")] == ["8", "7"]


@pytest.mark.parametrize(
    "run",
    [
        make_run(7, event="pull_request"),
        make_run(7, head_branch="topic"),
        make_run(7, head_repository={"full_name": "fork/ai-agents"}),
        make_run(7, conclusion="failure"),
        make_run(7, conclusion=None),
        make_run(7, path=".github/workflows/evil.yml"),
        make_run(7, head_sha="abc"),
    ],
    ids=[
        "pull-request",
        "other-branch",
        "fork",
        "failed",
        "unfinished",
        "other-workflow",
        "bad-sha",
    ],
)
def test_an_untrusted_run_is_never_listed_or_downloaded(tmp_path: Path, run: dict) -> None:
    write_inputs(tmp_path)
    gh = _gh(tmp_path, [run])
    assert not gh.fetch(tmp_path).seeded
    assert not (tmp_path / ".testmondata").exists()
    assert not any("/runs/7/" in call or "/zip" in call for call in gh.calls)


def test_a_run_whose_commit_is_not_in_main_history_is_skipped_for_an_older_one(
    tmp_path: Path,
) -> None:
    write_inputs(tmp_path)
    gh = _gh(
        tmp_path,
        [make_run(8), make_run(7)],
        {8: [artifact_entry(tmp_path, id=901)], 7: [artifact_entry(tmp_path)]},
    )
    checked: list[str] = []

    def ancestor(_root: Path, sha: str) -> bool:
        checked.append(sha)
        return sha == make_run(7)["head_sha"]

    assert gh.fetch(tmp_path, ancestor=ancestor).seeded
    assert checked == [make_run(8)["head_sha"], make_run(7)["head_sha"]]
    assert not any("/runs/8/" in call for call in gh.calls)


def test_a_missing_origin_main_falls_back_before_any_network_call(tmp_path: Path) -> None:
    write_inputs(tmp_path)
    gh = _gh(tmp_path, [make_run(7)])
    result = gh.fetch(tmp_path, has_origin_main=lambda _root: False)
    assert not result.seeded
    assert "origin/main" in result.detail
    assert gh.calls == []


def test_a_key_mismatch_finds_no_artifact(tmp_path: Path) -> None:
    write_inputs(tmp_path)
    stale = artifact_entry(tmp_path, name="testmon-db-" + "0" * 64)
    result = _gh(tmp_path, [make_run(7)], {7: [stale]}).fetch(tmp_path)
    assert not result.seeded
    assert "no main push run" in result.detail


def test_an_existing_database_is_never_replaced_and_nothing_is_fetched(tmp_path: Path) -> None:
    write_inputs(tmp_path)
    (tmp_path / ".testmondata").write_bytes(b"mine")
    gh = FakeGh({})
    assert not gh.fetch(tmp_path).seeded
    assert (tmp_path / ".testmondata").read_bytes() == b"mine"
    assert gh.calls == []
