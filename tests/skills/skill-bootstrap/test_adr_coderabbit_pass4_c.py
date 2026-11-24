"""Tests for the PR #7527 CodeRabbit pass 4 findings, group C.

Each test names the finding it pins. The PR export tests call ``select_prs`` directly; the git
tests build real repositories with ``adr_helpers``.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any

import adr_commits
import adr_locate
import adr_scan
import adr_write
import bootstrap_adr
import pytest
from adr_helpers import commit, git, new_repo
from draft_helpers import _cand, _scan_file, _text

ORIGIN = "https://github.com/o/r"
WHY = "Because the team already runs it in production and a second system needs a second on-call."
BREAKING_TITLE = "feat!: Adopt Postgres instead of MySQL"


def _row(number: int = 7, **over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "number": number,
        "title": "Adopt Postgres instead of MySQL",
        "body": WHY,
        "url": f"{ORIGIN}/pull/{number}",
        "merged_at": "2026-03-04T10:00:00Z",
        "author": {"login": "ada"},
    }
    return {**base, **over}


def _select(rows: list[Any], base: str | None = None) -> tuple[list[int], dict[str, int]]:
    dropped: dict[str, int] = {}
    kept = adr_commits.select_prs(rows, dropped, base)
    return [row.number for row in kept], dropped


# --- Thread PRRT_kwDOQoWRls67QJQ6: a reason absorbed from a covered commit cites that commit ---


def _covered_repo(tmp_path: Path) -> tuple[Path, str]:
    repo = new_repo(tmp_path / "r")
    git(repo, "remote", "add", "origin", f"{ORIGIN}.git")
    sha = commit(repo, f"Adopt Postgres instead of MySQL (#12)\n\n{WHY}\n")
    return repo, sha


def test_a_reason_taken_from_a_covered_commit_records_that_commit(tmp_path: Path) -> None:
    repo, sha = _covered_repo(tmp_path)
    row = _row(12, title=BREAKING_TITLE, body="")

    payload = adr_scan.scan(repo, "HEAD", 300, None, [row])

    (item,) = payload["candidates"]
    assert item["id"] == "pr-12" and item["reason"]
    assert item["source"]["reason_sha"] == sha
    assert item["source"]["reason_url"] == f"{ORIGIN}/commit/{sha}"
    assert item["source"]["url"] == f"{ORIGIN}/pull/12"


def test_a_pull_request_that_states_its_own_reason_keeps_its_source(tmp_path: Path) -> None:
    repo, _sha = _covered_repo(tmp_path)

    payload = adr_scan.scan(repo, "HEAD", 300, None, [_row(12)])

    (item,) = payload["candidates"]
    assert item["source"] == {"number": 12, "url": f"{ORIGIN}/pull/12", "sha": None}


def _pr_candidate(**source: Any) -> dict[str, Any]:
    return _cand(
        id="pr-12",
        kind="pr",
        title="Adopt Postgres instead of MySQL",
        source={"number": 12, "url": f"{ORIGIN}/pull/12", "sha": None, **source},
    )


def test_the_draft_cites_the_commit_that_stated_the_reason(tmp_path: Path) -> None:
    sha = "ab" * 20
    url = f"{ORIGIN}/commit/{sha}"
    scan = _scan_file(tmp_path, tmp_path, _pr_candidate(reason_sha=sha, reason_url=url))

    text = _text(bootstrap_adr.draft(scan, "pr-12", str(tmp_path / "out"), "Proposed"))

    reason = _cand()["reason"]
    assert f"The reason given at the time: {reason} (stated in commit {url})" in text
    assert f"Decided in {ORIGIN}/pull/12" in text


def test_the_draft_cites_the_reason_sha_when_no_web_address_is_known(tmp_path: Path) -> None:
    sha = "cd" * 20
    scan = _scan_file(tmp_path, tmp_path, _pr_candidate(reason_sha=sha, reason_url=None))

    text = _text(bootstrap_adr.draft(scan, "pr-12", str(tmp_path / "out"), "Proposed"))

    assert f"(stated in commit {sha})" in text


def test_a_draft_with_no_reason_source_cites_only_the_pull_request(tmp_path: Path) -> None:
    scan = _scan_file(tmp_path, tmp_path, _pr_candidate())

    text = _text(bootstrap_adr.draft(scan, "pr-12", str(tmp_path / "out"), "Proposed"))

    assert f"The reason given at the time: {_cand()['reason']}\n" in text
    assert "stated in commit" not in text


@pytest.mark.parametrize(
    "source",
    [
        {"reason_url": "https://a.example/x\n## Injected", "reason_sha": "nothex"},
        {"reason_url": "http://a.example/x", "reason_sha": "ab" * 19},
        {"reason_url": "javascript:alert(1)", "reason_sha": "ab\n" * 20},
    ],
)
def test_a_hostile_reason_source_adds_nothing_to_the_draft(
    tmp_path: Path, source: dict[str, Any]
) -> None:
    prepared = bootstrap_adr._prepare_candidate(_pr_candidate(**source))
    assert "reason_url" not in prepared["source"] and "reason_sha" not in prepared["source"]
    scan = _scan_file(tmp_path, tmp_path, _pr_candidate(**source))

    text = _text(bootstrap_adr.draft(scan, "pr-12", str(tmp_path / "out"), "Proposed"))

    assert "stated in commit" not in text and "Injected" not in text


def test_clean_source_keeps_a_valid_reason_source() -> None:
    source = {"reason_sha": "ef" * 32, "reason_url": f"{ORIGIN}/commit/{'ef' * 32}"}

    assert adr_locate.clean_source(source) == source


# --- C1: a template comment cut open by the sample is not quoted ---


def test_a_comment_cut_open_by_the_sample_leaves_no_comment_text() -> None:
    body = "<!-- " + "template hint " * 400 + "-->\nThe real prose."

    quoted = adr_commits.excerpt("Adopt X", body)

    assert "template hint" not in quoted and "<!--" not in quoted


def test_prose_after_a_comment_closed_inside_the_sample_is_kept() -> None:
    body = "<!-- a template hint -->\nThe real prose.\n<!-- another -->\nMore prose."

    quoted = adr_commits.excerpt("Adopt X", body)

    assert quoted == "Adopt X\n\n\nThe real prose.\n\nMore prose."


def test_an_unclosed_comment_on_a_hostile_body_stays_fast() -> None:
    start = time.perf_counter()
    adr_commits.excerpt("Adopt X", "<!--" * 16384)
    assert time.perf_counter() - start < 1.0


# --- C2: a merge field with text after the date is not a merge time ---


@pytest.mark.parametrize(
    "value",
    [
        "2026-05-04 not merged",
        "2026-05-04Tlater",
        "2026-03-04T25:00:00Z",
        "2026-05-04x",
        "2026-05-04x10:00",
        "2026-05-04 10:00",
        "2026-05-04 12",
    ],
)
def test_a_merge_field_with_trailing_text_is_incomplete(value: str) -> None:
    kept, dropped = _select([_row(title=BREAKING_TITLE, body="", merged_at=value)])

    assert kept == [] and dropped == {"pr_incomplete": 1}


@pytest.mark.parametrize(
    "value",
    [
        "2026-05-04",
        "2026-03-04T10:00:00Z",
        "2026-03-04T10:00:00.123+02:00",
        " 2026-03-04T10:00:00Z ",
        "2026-03-04T10:00",
    ],
)
def test_a_bare_date_or_a_full_timestamp_is_a_merge_time(value: str) -> None:
    kept, dropped = _select([_row(merged_at=value)])

    assert kept == [7] and dropped == {}


def test_the_mergedat_spelling_is_checked_the_same_way() -> None:
    kept, dropped = _select([_row(merged_at=None, mergedAt="2026-05-04 not merged")])

    assert kept == [] and dropped == {"pr_incomplete": 1}


def test_iso_day_still_reads_only_the_date_prefix() -> None:
    assert adr_commits.iso_day("2026-05-04 not merged") == "2026-05-04"


# --- C3: the default https port is the same origin on both sides ---


@pytest.mark.parametrize(
    ("url", "base", "kept"),
    [
        ("https://github.com:443/o/r/pull/7", ORIGIN, True),
        ("https://GitHub.com/O/R/pull/7", ORIGIN, True),
        ("https://github.com/o/r/pull/7", "https://github.com:8443/o/r", False),
        ("https://github.com:8443/o/r/pull/7", ORIGIN, False),
        ("https://github.com:8443/o/r/pull/7", "https://github.com:8443/o/r", True),
        ("https://github.com:9443/o/r/pull/7", "https://github.com:8443/o/r", False),
        ("https://github.com/o/r2/pull/7", ORIGIN, False),
    ],
)
def test_the_origin_check_compares_normalized_parts(url: str, base: str, kept: bool) -> None:
    numbers, dropped = _select([_row(url=url)], base)

    assert numbers == ([7] if kept else []) and dropped == ({} if kept else {"pr_other_repo": 1})


def test_a_port_out_of_range_is_incomplete() -> None:
    kept, dropped = _select([_row(url="https://github.com:99999/o/r/pull/7")])

    assert kept == [] and dropped == {"pr_incomplete": 1}


# --- C4: the number after /pull/ must be the row's number ---


@pytest.mark.parametrize("base", [None, "https://github.com/acme/app"])
@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/acme/app/pull/7/files/42",
        "https://github.com/acme/app/pull/archive/42",
        "https://github.com/acme/app/PULL/7/files/42",
    ],
)
def test_a_nested_path_after_pull_is_incomplete(url: str, base: str | None) -> None:
    kept, dropped = _select([_row(42, url=url)], base)

    assert kept == [] and dropped == {"pr_incomplete": 1}


@pytest.mark.parametrize("base", [None, "https://github.com/acme/pull"])
@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/acme/pull/pull/42",
        "https://github.com/acme/pull/pull/42/",
        "https://github.com/acme/pull/pull/42?tab=files#top",
    ],
)
def test_a_page_ending_in_pull_and_its_number_is_kept(url: str, base: str | None) -> None:
    kept, dropped = _select([_row(42, url=url)], base)

    assert kept == [42] and dropped == {}


def test_a_page_with_no_pull_segment_keeps_its_no_origin_handling() -> None:
    kept, dropped = _select([_row(11, url="https://h.example/p/11")])

    assert kept == [11] and dropped == {}


# --- C5: the scan records carry no per-instance dictionary ---


def test_the_scan_records_use_slots() -> None:
    record = adr_commits.CommitRecord("a" * 40, "s", "a", "", "")
    row = adr_commits.PrRow(1, "t", "b", f"{ORIGIN}/pull/1", "2026-01-01", None, None)

    assert not hasattr(record, "__dict__") and not hasattr(row, "__dict__")


# --- C6: a body that is not text is not an empty body ---


@pytest.mark.parametrize("body", [{"text": WHY}, ["x"], 3, True])
def test_a_body_that_is_not_text_is_incomplete(body: object) -> None:
    kept, dropped = _select([_row(title=BREAKING_TITLE, body=body)])

    assert kept == [] and dropped == {"pr_incomplete": 1}


def test_a_null_body_on_a_breaking_pull_request_is_kept() -> None:
    kept, dropped = _select([_row(title=BREAKING_TITLE, body=None)])

    assert kept == [7] and dropped == {}


# --- C7 and C8: work-tree paths stay exact, with or without ``worktree list -z`` ---


def _without_z(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make ``worktree list -z`` fail as git before 2.36 does; every other call runs git."""
    real = adr_scan.git_bytes

    def old_git(repo: Path, *args: str, stdin: bytes | None = None) -> Any:
        if "-z" in args:
            return subprocess.CompletedProcess(args, 129, b"", b"error: unknown switch `z'")
        return real(repo, *args, stdin=stdin)

    monkeypatch.setattr(adr_scan, "git_bytes", old_git)
    monkeypatch.setattr(adr_write, "git_bytes", old_git)


def _linked(repo: Path, path: Path) -> Path:
    """A linked work tree at ``path``. A name the filesystem refuses (a newline on Windows, bytes
    that are not UTF-8 on macOS) skips the test."""
    try:
        git(repo, "worktree", "add", "-q", "--detach", str(path))
    except (subprocess.CalledProcessError, UnicodeError, ValueError):
        pytest.skip(f"this filesystem refuses the work tree name {path.name!r}")
    return path.resolve()


def test_without_z_a_newline_path_still_bounds_the_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = new_repo(tmp_path / "main")
    commit(repo, "Initial work")
    linked = _linked(repo, tmp_path / "wt\nname")
    nested = new_repo(linked / "nested")
    _without_z(monkeypatch)

    assert adr_write.work_trees(repo) == [repo, linked]
    with pytest.raises(adr_scan.ConfigError, match="inside the repository"):
        adr_write.out_outside_repo(repo, str(nested / "report.json"))


def test_the_legacy_inventory_matches_the_z_listing(tmp_path: Path) -> None:
    repo = new_repo(tmp_path / "main")
    commit(repo, "Initial work")
    for name in ("b", "a", "c\nd"):
        _linked(repo, tmp_path / name)

    assert sorted(adr_write._admin_trees(repo)) == sorted(adr_write.work_trees(repo))
    assert len(adr_write.work_trees(repo)) == 4


def test_the_legacy_inventory_of_a_linked_tree_of_a_bare_repository(tmp_path: Path) -> None:
    bare = tmp_path / "bare.git"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(bare))
    seed = new_repo(tmp_path / "seed")
    commit(seed, "Initial work")
    git(seed, "push", "-q", str(bare), "main")
    linked = _linked(bare, tmp_path / "wt")

    assert (
        adr_write._admin_trees(linked) == adr_write.work_trees(linked) == [bare.resolve(), linked]
    )


def test_a_plain_legacy_list_still_allows_an_outside_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = new_repo(tmp_path / "main")
    commit(repo, "Initial work")
    linked = _linked(repo, tmp_path / "wt")
    _without_z(monkeypatch)

    assert adr_write.work_trees(repo) == [repo, linked]
    target = tmp_path / "out" / "report.json"
    assert adr_write.out_outside_repo(repo, str(target)) == target.resolve()
    with pytest.raises(adr_scan.ConfigError, match="inside the repository"):
        adr_write.out_outside_repo(repo, str(linked / "report.json"))


def test_a_worktree_list_failure_other_than_129_is_a_git_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(repo: Path, *args: str, stdin: bytes | None = None) -> Any:
        return subprocess.CompletedProcess(args, 128, b"", b"fatal: broken")

    monkeypatch.setattr(adr_write, "git_bytes", broken)

    with pytest.raises(adr_scan.GitError, match="broken"):
        adr_write.work_trees(tmp_path)


def _raw_dir(tmp_path: Path) -> Path:
    """A folder whose name holds bytes that are not UTF-8, or a skip where that is impossible."""
    try:
        path = tmp_path / os.fsdecode(b"caf\xe9-\xff")
        path.mkdir()
    except (OSError, UnicodeError):
        pytest.skip("this filesystem refuses a name that is not UTF-8")
    return path


def test_repo_root_keeps_bytes_that_are_not_utf8(tmp_path: Path) -> None:
    repo = new_repo(_raw_dir(tmp_path) / "r")

    assert adr_scan.repo_root(repo) == repo


def test_the_write_gate_keeps_bytes_that_are_not_utf8(tmp_path: Path) -> None:
    repo = new_repo(tmp_path / "main")
    commit(repo, "Initial work")
    linked = _linked(repo, _raw_dir(tmp_path) / "wt")

    assert adr_write.enclosing_tree(linked / "docs") == linked
    assert adr_write.work_trees(repo) == [repo, linked]
    assert adr_write._same_repo(repo, linked)


# --- C9: a draft number the locator cannot read is refused ---


def test_adr_files_reads_six_digits_and_not_seven(tmp_path: Path) -> None:
    (tmp_path / "999999-last.md").write_text("# 999999. Last\n", encoding="utf-8")
    (tmp_path / "1000000-over.md").write_text("# 1000000. Over\n", encoding="utf-8")

    assert [item.number for item in adr_locate.adr_files(tmp_path)] == [999999]
    assert bootstrap_adr.MAX_ADR_NUMBER == 999999


def test_a_draft_past_the_last_readable_number_is_refused(tmp_path: Path) -> None:
    out = tmp_path / "out"
    out.mkdir()
    (out / "999999-last.md").write_text("# 999999. Last\n", encoding="utf-8")
    scan = _scan_file(tmp_path, tmp_path, _cand())

    with pytest.raises(adr_scan.ConfigError, match="999999"):
        bootstrap_adr.draft(scan, "c-1234567", str(out), "Proposed")

    assert sorted(path.name for path in out.iterdir()) == ["999999-last.md"]


def test_the_last_readable_number_is_still_drafted(tmp_path: Path) -> None:
    out = tmp_path / "out"
    out.mkdir()
    (out / "999998-prev.md").write_text("# 999998. Prev\n", encoding="utf-8")
    scan = _scan_file(tmp_path, tmp_path, _cand())

    result = bootstrap_adr.draft(scan, "c-1234567", str(out), "Proposed")

    assert result["number"] == 999999 and Path(result["path"]).name.startswith("999999-")


# --- C10: offline evidence that is not UTF-8 is bad input ---


def test_a_scan_file_with_invalid_utf8_is_refused(tmp_path: Path) -> None:
    scan = tmp_path / "scan.json"
    good = json.dumps({"repo": str(tmp_path), "candidates": [_cand(title="Adopt XX here")]})
    scan.write_bytes(good.encode("ascii").replace(b"XX", b"\xff\xfe"))

    with pytest.raises(adr_scan.ConfigError, match="cannot read scan file"):
        bootstrap_adr.draft(str(scan), "c-1234567", str(tmp_path / "out"), "Proposed")

    assert not (tmp_path / "out").exists()


def test_a_pull_request_export_with_invalid_utf8_is_refused(tmp_path: Path) -> None:
    export = tmp_path / "prs.json"
    export.write_bytes(b'[{"title": "Adopt \xff"}]')

    with pytest.raises(adr_scan.ConfigError, match="cannot read --prs-json"):
        bootstrap_adr._read_prs(str(export))


def test_a_valid_utf8_title_is_drafted_unchanged(tmp_path: Path) -> None:
    scan = tmp_path / "scan.json"
    data = {"repo": str(tmp_path), "candidates": [_cand(title="Adopt Café for caching")]}
    scan.write_bytes(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    text = _text(bootstrap_adr.draft(str(scan), "c-1234567", str(tmp_path / "out"), "Proposed"))

    assert "Adopt Café for caching" in text


# --- C12: --since filters by date and does not stop at an older child ---


def test_since_keeps_a_parent_behind_an_older_child(tmp_path: Path) -> None:
    repo = new_repo(tmp_path / "r")
    parent = commit(repo, f"Adopt X instead of Y\n\n{WHY}\n", date="2026-06-20T12:00:00+00:00")
    commit(repo, f"Adopt Z instead of X\n\n{WHY}\n", date="2026-06-10T12:00:00+00:00")
    head = adr_scan.resolve_rev(repo, "HEAD")

    records, truncated = adr_scan.read_commits(repo, head, 10, "2026-06-15T00:00:00+00:00")

    assert [record.sha for record in records] == [parent] and truncated is False


# --- C13: the work tree git names must contain the requested path ---


def test_repo_root_refuses_a_work_tree_that_does_not_hold_the_path(tmp_path: Path) -> None:
    other = new_repo(tmp_path / "other")
    repo = new_repo(tmp_path / "repo")
    git(repo, "config", "core.worktree", str(other))
    shown = adr_scan.git_bytes(repo, "rev-parse", "--show-toplevel").stdout
    assert Path(os.fsdecode(shown.removesuffix(b"\n"))).resolve() == other

    with pytest.raises(adr_scan.ConfigError, match="does not contain"):
        adr_scan.repo_root(repo)


def test_repo_root_accepts_a_folder_inside_its_work_tree(tmp_path: Path) -> None:
    repo = new_repo(tmp_path / "repo")
    (repo / "docs" / "adr").mkdir(parents=True)

    assert adr_scan.repo_root(repo / "docs" / "adr") == repo
