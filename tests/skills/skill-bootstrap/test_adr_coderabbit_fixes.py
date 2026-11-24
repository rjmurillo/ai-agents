"""Tests for the PR #7527 CodeRabbit findings and the round 7 review findings."""

from __future__ import annotations

import os
import time
from hashlib import sha256
from pathlib import Path
from typing import Any

import adr_commits
import adr_docs
import adr_log
import adr_scan
import adr_shape
import adr_write
import bootstrap_adr
import pytest
from adr_helpers import commit, git, new_repo, run_cli, write

WHY = "Because the team already runs it in production and a second system needs a second on-call."
ORIGIN = "https://github.com/o/r"


def _entry(ident: str, title: str) -> tuple[str, adr_log.LogEntry]:
    return "DECISIONS.md", adr_log.LogEntry(ident, title, title, f"{title}\n\n{WHY}")


def _row(number: int, title: str, **over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "number": number,
        "title": title,
        "body": WHY,
        "url": f"{ORIGIN}/pull/{number}",
        "merged_at": "2026-03-04T10:00:00Z",
        "author": {"login": "ada"},
    }
    return {**base, **over}


def _origin_repo(tmp_path: Path) -> Path:
    repo = new_repo(tmp_path / "r")
    write(repo, "docs/adr/0001-first.md", "# 1. First\n\n## Status\n\nAccepted\n")
    commit(repo, "Initial work")
    git(repo, "remote", "add", "origin", f"{ORIGIN}.git")
    return repo


# Decision-log keys


def test_a_literal_id_equal_to_a_twin_key_still_gets_a_distinct_key() -> None:
    twin = _entry("D-1", "D-1 - Use pnpm")
    hashed = f"D-1--{sha256(twin[1].title.encode()).hexdigest()[:8]}"

    keys = adr_log._entry_keys([twin, twin, _entry(f"{hashed}-2", "Other choice")])

    assert len({key.lower() for key in keys}) == 3


def test_ids_that_differ_only_in_case_are_twins() -> None:
    keys = adr_log._entry_keys([_entry("D-7", "D-7 - A"), _entry("d-7", "d-7 - B")])

    assert all("--" in key for key in keys) and len(set(keys)) == 2


def test_a_dotted_id_does_not_name_its_prefix() -> None:
    existing = adr_docs.ExistingAdrs([("a.md", "This follows D-001.2. See also D-9.")])

    assert existing.names_id("D-001.2") and existing.names_id("D-9")
    assert not existing.names_id("D-001")


def test_a_log_keeps_at_most_max_log_entries_per_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = new_repo(tmp_path / "r")
    write(repo, "DECISIONS.md", "".join(f"## D-{n} - Decision {n}\n\n{WHY}\n\n" for n in range(3)))
    monkeypatch.setattr(adr_log, "MAX_LOG_ENTRIES", 2)
    dropped = dict.fromkeys(adr_docs.DROP_KEYS, 0)

    entries, _files, _skipped = adr_log.read_log_entries(repo, dropped)

    assert [entry.id for _rel, entry in entries] == ["D-0", "D-1"]
    assert dropped["log_over_limit"] == 1


# Numbers and pull request rows


def test_an_oversized_issue_number_is_skipped_and_the_rest_kept() -> None:
    assert adr_commits.issue_numbers("see #" + "9" * 5000 + " and #42") == {42}


def test_an_oversized_squash_number_is_not_a_pr_number() -> None:
    assert adr_commits.trailing_pr_number("feat: x (#" + "9" * 5000 + ")") is None


@pytest.mark.parametrize(
    "over",
    [
        {"url": f"{ORIGIN}/pull/7"},
        {"html_url": "https://[x/pull/3"},
        {"url": "https://api.github.com/repos/o/r/pulls/3"},
    ],
)
def test_a_row_whose_url_is_not_its_own_pull_page_is_incomplete(over: dict[str, Any]) -> None:
    dropped: dict[str, int] = {}

    rows = adr_commits.select_prs([_row(3, "Adopt Rust for the parser", **over)], dropped)

    assert rows == [] and dropped["pr_incomplete"] == 1


def test_a_repeated_pr_number_keeps_the_first_row() -> None:
    dropped: dict[str, int] = {}
    first, second = _row(3, "Adopt Rust for the parser"), _row(3, "Keep Go for the parser")

    rows = adr_commits.select_prs([first, second], dropped, ORIGIN)

    assert [row.title for row in rows] == ["Adopt Rust for the parser"]
    assert dropped["pr_duplicate"] == 1


def test_a_merge_names_its_own_pull_request_before_a_title_suffix() -> None:
    record = adr_commits.CommitRecord("a" * 40, "Merge pull request #78 from x/y", "ada", "", "")

    assert adr_commits.commit_pr_number(record, "Adopt Rust for the parser (#12)") == 78
    assert adr_commits.covering_pr(record, "Adopt Rust (#12)", {}, {12, 78}) == 78
    assert adr_commits.covering_pr(record, "Adopt Rust (#12)", {}, {12}) is None


def test_every_final_candidate_id_is_unique() -> None:
    candidates: list[dict[str, Any]] = [
        {"id": "pr-3", "kind": "pr"},
        {"id": "pr-3", "kind": "pr"},
        {"id": "pr-3.2", "kind": "decision-log"},
    ]

    adr_scan._unique_ids(candidates)

    assert [c["id"] for c in candidates] == ["pr-3", "pr-3.2", "pr-3.2.2"]


def test_an_adr_that_cites_the_covered_commit_hides_the_pull_request(tmp_path: Path) -> None:
    repo = _origin_repo(tmp_path)
    squash = commit(repo, f"Adopt Rust for the parser (#12)\n\n{WHY}")
    write(repo, "docs/adr/0002-rust.md", f"# 2. Rust\n\nFrom commit {squash}.\n")
    commit(repo, "docs: record the Rust decision")

    payload = adr_scan.scan(repo, "HEAD", 300, None, [_row(12, "Adopt Rust for the parser")])

    assert payload["candidates"] == []
    assert payload["dropped"]["already_documented"] == 1


# Git reads


def test_git_runs_without_replacement_objects() -> None:
    assert adr_scan.git_env()["GIT_NO_REPLACE_OBJECTS"] == "1"


def test_a_replaced_commit_is_read_as_its_original(tmp_path: Path) -> None:
    repo = _origin_repo(tmp_path)
    original = commit(repo, f"Adopt Rust for the parser\n\n{WHY}")
    other = commit(repo, f"Adopt Kotlin for the build\n\n{WHY}")
    git(repo, "reset", "-q", "--hard", original)
    git(repo, "replace", original, other)

    titles = [c["title"] for c in adr_scan.scan(repo, "HEAD", 300, None, None)["candidates"]]

    assert titles == ["Adopt Rust for the parser"]


# Reference lists


def test_a_long_url_list_followed_by_prose_is_rejected_quickly() -> None:
    line = "fixes " + ",".join(["https://a/b"] * 200) + " and then some prose"

    start = time.perf_counter()
    found = adr_shape.FIXES_ONLY.match(line)

    assert found is None and time.perf_counter() - start < 1.0


@pytest.mark.parametrize(
    "line",
    [
        "fixes https://a/b?x=1&y=2, https://c/d",
        "fixes #1 & #2",
        "closes #1, and #2.",
        "refs o/r#4; gh-5",
    ],
)
def test_reference_lists_still_read_as_fixes_only(line: str) -> None:
    assert adr_shape.FIXES_ONLY.match(line)


# Writes and inputs


def test_a_failed_write_leaves_no_file(tmp_path: Path) -> None:
    target = tmp_path / "out" / "scan.json"

    data: Any = "not bytes"

    with pytest.raises(TypeError):
        adr_write.create_new(target, data)

    assert not target.exists()


def test_create_new_never_touches_a_file_already_there(tmp_path: Path) -> None:
    target = write(tmp_path, "scan.json", "keep me")

    with pytest.raises(FileExistsError):
        adr_write.create_new(target, b"new")

    assert target.read_text(encoding="utf-8") == "keep me"


def test_scan_out_inside_a_repository_nested_in_a_linked_worktree_is_refused(
    tmp_path: Path,
) -> None:
    repo = new_repo(tmp_path / "main")
    commit(repo, "Initial work")
    linked = tmp_path / "linked"
    git(repo, "worktree", "add", "-q", str(linked))
    new_repo(linked / "vendor")
    out = linked / "vendor" / "scan.json"

    code, payload = run_cli("scan", "--repo", str(repo), "--out", str(out))

    assert code == 2 and payload["error"] == "config" and not out.exists()


@pytest.mark.parametrize("since", ["20260131", "2026W051", "2026-W05-1", "2026-01-31T"])
def test_iso_forms_that_git_misreads_exit_two(tmp_path: Path, since: str) -> None:
    repo = new_repo(tmp_path / "r")
    commit(repo, "Initial work")

    code, payload = run_cli(
        "scan", "--repo", str(repo), "--since", since, "--out", str(tmp_path / "s.json")
    )

    assert code == 2 and payload["error"] == "config"


def test_a_bare_since_date_means_local_midnight() -> None:
    assert bootstrap_adr._check_since("2026-01-31") == "2026-01-31T00:00:00"
    assert bootstrap_adr._check_since("2026-01-31T08:00:00Z") == "2026-01-31T08:00:00Z"


@pytest.mark.skipif(os.name == "nt", reason="POSIX path")
def test_work_trees_lists_the_main_and_linked_trees(tmp_path: Path) -> None:
    repo = new_repo(tmp_path / "main")
    commit(repo, "Initial work")
    git(repo, "worktree", "add", "-q", str(tmp_path / "linked"))

    assert adr_write.work_trees(repo) == [repo, (tmp_path / "linked").resolve()]
