"""Tests for the PR #7527 CodeRabbit pass 4 findings, group C.

Each test names the finding it pins. The PR export tests call ``select_prs`` directly; the git
tests build real repositories with ``adr_helpers``.
"""

from __future__ import annotations

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


def _pr_candidate(**source: Any) -> dict[str, Any]:
    return _cand(
        id="pr-12",
        kind="pr",
        title="Adopt Postgres instead of MySQL",
        source={"number": 12, "url": f"{ORIGIN}/pull/12", "sha": None, **source},
    )


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


def _raw_dir(tmp_path: Path) -> Path:
    """A folder whose name holds bytes that are not UTF-8, or a skip where that is impossible."""
    try:
        path = tmp_path / os.fsdecode(b"caf\xe9-\xff")
        path.mkdir()
    except (OSError, UnicodeError):
        pytest.skip("this filesystem refuses a name that is not UTF-8")
    return path


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
