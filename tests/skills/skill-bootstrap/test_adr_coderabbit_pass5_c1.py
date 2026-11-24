"""Tests for the PR #7527 CodeRabbit pass 5 findings, group C1 (C11 to C18).

Each test names the finding it pins. The export tests call ``select_prs`` directly; the scan
tests build real repositories with ``adr_helpers``.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import adr_commits
import adr_scan
import adr_shape
import pytest
from adr_helpers import commit, git, new_repo

ORIGIN = "https://github.com/o/r"
WHY = "Because the team already runs it in production and a second system needs a second on-call."
BREAKING = "The settings file moved.\n\nBREAKING CHANGE: the config format changed."


def _row(number: int = 12, **over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "number": number,
        "title": "Use SQLite for client storage",
        "body": WHY,
        "url": f"{ORIGIN}/pull/{number}",
        "merged_at": "2026-03-04T10:00:00Z",
        "author": {"login": "ada"},
    }
    return {**base, **over}


def _without(row: dict[str, Any], *keys: str) -> dict[str, Any]:
    return {key: value for key, value in row.items() if key not in keys}


def _scan(repo: Path, prs: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = adr_scan.scan(repo, "HEAD", 50, None, prs)
    return payload


def _fake_git_version(monkeypatch: pytest.MonkeyPatch, version: str) -> None:
    """Answer ``git version`` with ``version``; every other git call runs for real."""
    real = adr_scan.git_text

    def fake(repo: Path, *args: str, ok: tuple[int, ...] = (0,)) -> Any:
        if args == ("version",):
            return subprocess.CompletedProcess(
                ["git", "version"], 0, f"git version {version}\n", ""
            )
        return real(repo, *args, ok=ok)

    monkeypatch.setattr(adr_scan, "git_text", fake)


def _partial_clone(tmp_path: Path) -> Path:
    repo = new_repo(tmp_path / "r")
    commit(repo, "Initial work")
    git(repo, "config", "extensions.partialClone", "origin")
    return repo


# --- C11: scan() itself refuses a partial clone on a git that may fetch ---


@pytest.mark.parametrize("version", ["2.45.0", "2.39.3", "2.44.0"])
def test_c11_scan_refuses_a_partial_clone_on_a_git_that_may_fetch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, version: str
) -> None:
    repo = _partial_clone(tmp_path)
    _fake_git_version(monkeypatch, version)

    with pytest.raises(adr_scan.ConfigError, match="partial clone"):
        _scan(repo)


def test_c11_the_refusal_comes_before_the_rev_is_resolved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _partial_clone(tmp_path)
    _fake_git_version(monkeypatch, "2.40.1")

    def never(_root: Path, _rev: str) -> str:
        raise AssertionError("resolve_rev ran before the offline check")

    monkeypatch.setattr(adr_scan, "resolve_rev", never)

    with pytest.raises(adr_scan.ConfigError, match="partial clone"):
        adr_scan.scan(repo, "no-such-rev", 5, None, None)


@pytest.mark.parametrize("version", ["2.45.1", "2.39.4", "2.44.1", "3.0.0"])
def test_c11_a_partial_clone_on_a_git_that_honors_no_lazy_fetch_is_scanned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, version: str
) -> None:
    repo = _partial_clone(tmp_path)
    _fake_git_version(monkeypatch, version)

    assert _scan(repo)["examined"]["commits"] == 1


def test_c11_a_full_clone_is_scanned_on_any_git(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = new_repo(tmp_path / "r")
    commit(repo, "Initial work")
    _fake_git_version(monkeypatch, "2.20.0")

    assert _scan(repo)["examined"]["commits"] == 1


def test_c11_an_unreadable_git_version_counts_as_one_that_may_fetch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _partial_clone(tmp_path)
    _fake_git_version(monkeypatch, "unknown")

    with pytest.raises(adr_scan.ConfigError, match="partial clone"):
        adr_scan.refuse_lazy_fetch(repo)


# --- C12: a PR number is reserved only after the title filter ---


def test_c12_a_later_row_with_a_decision_title_survives_an_earlier_non_decision_row() -> None:
    dropped: dict[str, int] = {}
    first = _row(12, title="Tidy the worker module")
    second = _row(12, title="Use SQLite for client storage")

    rows = adr_commits.select_prs([first, second], dropped, ORIGIN)

    assert [row.title for row in rows] == ["Use SQLite for client storage"]
    assert dropped == {"pr_not_decision_shaped": 1}


def test_c12_when_both_rows_pass_the_first_is_kept() -> None:
    dropped: dict[str, int] = {}
    first = _row(12, title="Use SQLite for client storage")
    second = _row(12, title="Adopt Postgres for client storage")

    rows = adr_commits.select_prs([first, second], dropped, ORIGIN)

    assert [row.title for row in rows] == ["Use SQLite for client storage"]
    assert dropped == {"pr_duplicate": 1}


def test_c12_the_scan_counts_the_title_drop_once(tmp_path: Path) -> None:
    repo = new_repo(tmp_path / "r")
    commit(repo, "Initial work")
    git(repo, "remote", "add", "origin", f"{ORIGIN}.git")
    prs = [_row(12, title="Tidy the worker module"), _row(12)]

    payload = _scan(repo, prs)

    assert [item["id"] for item in payload["candidates"]] == ["pr-12"]
    assert payload["dropped"]["pr_not_decision_shaped"] == 1
    assert payload["dropped"]["pr_duplicate"] == 0


# --- C13 and C15: the effective origin decides which PR rows are this repository's ---


def _covered_repo(tmp_path: Path, origin: str | None) -> Path:
    repo = new_repo(tmp_path / "r")
    commit(repo, f"Adopt Postgres instead of MySQL (#42)\n\n{WHY}\n")
    if origin is not None:
        git(repo, "remote", "add", "origin", origin)
    return repo


def test_c13_an_unsupported_origin_rejects_the_import_and_keeps_local_commits(
    tmp_path: Path,
) -> None:
    repo = _covered_repo(tmp_path, "https://git.example.com/team/app")
    foreign = _row(42, url="https://github.com/other/repo/pull/42")

    payload = _scan(repo, [foreign])

    assert [item["kind"] for item in payload["candidates"]] == ["commit"]
    assert payload["dropped"]["pr_other_repo"] == 1
    assert payload["dropped"]["covered_by_pr"] == 0


def test_c13_with_no_origin_every_complete_row_is_still_kept(tmp_path: Path) -> None:
    repo = _covered_repo(tmp_path, None)
    row = _row(42, url="https://github.com/other/repo/pull/42")

    payload = _scan(repo, [row])

    assert [item["id"] for item in payload["candidates"]] == ["pr-42"]
    assert payload["dropped"]["pr_other_repo"] == 0


def test_c13_an_unsupported_origin_gives_an_empty_base(tmp_path: Path) -> None:
    repo = _covered_repo(tmp_path, "https://git.example.com/team/app")

    assert adr_scan.origin_web_base(repo) == (None, "")


def test_c13_an_empty_base_keeps_no_row() -> None:
    dropped: dict[str, int] = {}

    assert adr_commits.select_prs([_row(42)], dropped, "") == []
    assert dropped == {"pr_other_repo": 1}


def test_c15_an_insteadof_alias_resolves_to_the_github_origin(tmp_path: Path) -> None:
    repo = _covered_repo(tmp_path, "gh:o/r.git")
    git(repo, "config", "url.https://github.com/.insteadOf", "gh:")
    own, foreign = _row(42), _row(43, url="https://github.com/x/y/pull/43")

    payload = _scan(repo, [own, foreign])

    (only,) = payload["candidates"]
    assert only["id"] == "pr-42" and only["source"]["url"] == f"{ORIGIN}/pull/42"
    assert payload["dropped"]["pr_other_repo"] == 1
    assert payload["dropped"]["covered_by_pr"] == 1
    assert adr_scan.origin_web_base(repo) == (("github", ORIGIN), ORIGIN)


def test_c15_a_commit_url_is_built_from_the_resolved_alias(tmp_path: Path) -> None:
    repo = _covered_repo(tmp_path, "gh:o/r.git")
    git(repo, "config", "url.https://github.com/.insteadOf", "gh:")

    (only,) = _scan(repo)["candidates"]

    assert only["source"]["url"].startswith(f"{ORIGIN}/commit/")
    assert only["source"]["pr_url"] == f"{ORIGIN}/pull/42"


def _fake_get_url(monkeypatch: pytest.MonkeyPatch, code: int, err: bytes) -> None:
    real = adr_scan.git_bytes

    def fake(repo: Path, *args: str, stdin: bytes | None = None) -> Any:
        if args[:2] == ("remote", "get-url"):
            return subprocess.CompletedProcess(["git", *args], code, b"", err)
        return real(repo, *args, stdin=stdin)

    monkeypatch.setattr(adr_scan, "git_bytes", fake)


def test_c15_no_such_remote_reads_as_no_origin_whatever_the_exit_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _covered_repo(tmp_path, None)
    _fake_get_url(monkeypatch, 128, b"fatal: No such remote 'origin'\n")

    assert adr_scan.origin_web_base(repo) == (None, None)
    assert [item["id"] for item in _scan(repo, [_row(42)])["candidates"]] == ["pr-42"]


def test_c15_any_other_get_url_failure_is_a_git_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _covered_repo(tmp_path, None)
    _fake_get_url(monkeypatch, 1, b"error: bad config line 3\n")

    with pytest.raises(adr_scan.GitError, match="bad config line 3"):
        adr_scan.origin_web_base(repo)


# --- C14: each commit batch is classified as it is read ---


def _mixed_history(tmp_path: Path) -> Path:
    repo = new_repo(tmp_path / "r")
    commit(repo, f"Adopt Postgres instead of MySQL\n\n{WHY}\n")
    commit(repo, "chore: tidy imports")
    commit(repo, f"Use SQLite for client storage\n\n{WHY}\n", date="2026-02-02T03:04:05+00:00")
    commit(repo, f"Update libfoo to 2.0\n\n{BREAKING}\n", date="2026-03-02T03:04:05+00:00")
    return repo


def test_c14_each_batch_is_classified_before_the_next_is_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _mixed_history(tmp_path)
    events: list[str] = []
    real_read, real_shape = adr_scan._read_batch, adr_shape.resolve_commit_shape

    def read(root: Path, shas: list[str]) -> list[adr_commits.CommitRecord]:
        events.append("read")
        return real_read(root, shas)

    def shape(subject: str, body: str) -> adr_shape.CommitShape:
        events.append("classify")
        return real_shape(subject, body)

    monkeypatch.setattr(adr_scan, "BATCH_SHAS", 1)
    monkeypatch.setattr(adr_scan, "_read_batch", read)
    monkeypatch.setattr(adr_scan, "resolve_commit_shape", shape)

    payload = _scan(repo)

    assert events == ["read", "classify"] * 4
    assert payload["examined"]["commits"] == 4


def test_c14_batch_size_does_not_change_the_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _mixed_history(tmp_path)
    whole = _scan(repo)
    monkeypatch.setattr(adr_scan, "BATCH_SHAS", 1)

    assert _scan(repo) == whole
    assert len(whole["candidates"]) == 3 and whole["dropped"]["housekeeping"] == 1


def test_c14_read_commits_still_returns_every_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _mixed_history(tmp_path)
    monkeypatch.setattr(adr_scan, "BATCH_SHAS", 1)
    dropped: dict[str, int] = {}

    records, truncated = adr_scan.read_commits(
        repo, git(repo, "rev-parse", "HEAD").strip(), 3, None, dropped
    )

    assert [record.subject for record in records][0] == "Update libfoo to 2.0"
    assert len(records) == 3 and truncated is True and dropped == {}


# --- C16 and C17: an export row needs a body key and an author object with a login ---


@pytest.mark.parametrize(
    "author",
    ["dependabot[bot]", {"login": "   "}, {"login": 7}, {"is_bot": False}, ["ada"], None],
)
def test_c16_an_author_that_is_not_an_object_with_a_login_is_incomplete(author: object) -> None:
    dropped: dict[str, int] = {}

    assert adr_commits.select_prs([_row(author=author)], dropped, ORIGIN) == []
    assert dropped == {"pr_incomplete": 1}


def test_c16_a_bot_login_in_an_author_object_is_still_a_bot() -> None:
    dropped: dict[str, int] = {}
    row = _row(author={"login": "dependabot[bot]"})

    assert adr_commits.select_prs([row], dropped, ORIGIN) == []
    assert dropped == {"pr_bot": 1}


def test_c16_a_user_object_stands_in_for_author() -> None:
    row = _without(_row(user={"login": "ada"}), "author")

    assert [kept.number for kept in adr_commits.select_prs([row], {}, ORIGIN)] == [12]


@pytest.mark.parametrize(("missing"), [("body",), ("author",), ("body", "author")])
def test_c17_a_breaking_row_without_a_body_key_or_an_author_is_incomplete(
    missing: tuple[str, ...],
) -> None:
    dropped: dict[str, int] = {}
    row = _without(_row(title="feat!: Switch to the new transport"), *missing)

    assert adr_commits.select_prs([row], dropped, ORIGIN) == []
    assert dropped == {"pr_incomplete": 1}


def test_c17_an_explicit_null_body_stays_valid() -> None:
    row = _row(title="feat!: Switch to the new transport", body=None)

    (kept,) = adr_commits.select_prs([row], {}, ORIGIN)

    assert kept.body == "" and kept.reason is None and kept.breaking is True


# --- C18: a breaking change lifts only the release-or-bump clause of the floor ---


def test_c18_a_breaking_bump_pr_is_kept() -> None:
    dropped: dict[str, int] = {}
    row = _row(7, title="Update libfoo to 2.0", body=BREAKING)

    rows = adr_commits.select_prs([row], dropped, ORIGIN)

    assert [(kept.number, kept.breaking) for kept in rows] == [(7, True)] and dropped == {}


@pytest.mark.parametrize(
    ("title", "body"),
    [("Update libfoo to 2.0", WHY), ("chore: bump libfoo to 2.0", BREAKING)],
)
def test_c18_a_plain_bump_or_a_mechanical_breaking_bump_is_housekeeping(
    title: str, body: str
) -> None:
    dropped: dict[str, int] = {}

    assert adr_commits.select_prs([_row(7, title=title, body=body)], dropped, ORIGIN) == []
    assert dropped == {"pr_housekeeping": 1}


def test_c18_a_breaking_bump_commit_is_a_candidate_and_a_plain_one_is_not(tmp_path: Path) -> None:
    repo = new_repo(tmp_path / "r")
    commit(repo, f"Update libfoo to 2.0\n\n{BREAKING}\n")
    commit(repo, f"Update libbar to 3.0\n\n{WHY}\n")

    payload = _scan(repo)

    found = [(item["title"], item["signals"]) for item in payload["candidates"]]
    assert found == [("Update libfoo to 2.0", ["breaking-change"])]
    assert payload["dropped"]["housekeeping"] == 1


def test_c18_a_breaking_bump_pr_is_a_scan_candidate(tmp_path: Path) -> None:
    repo = new_repo(tmp_path / "r")
    commit(repo, "Initial work")
    git(repo, "remote", "add", "origin", f"{ORIGIN}.git")

    payload = _scan(repo, [_row(7, title="Update libfoo to 2.0", body=BREAKING)])

    (only,) = payload["candidates"]
    assert only["id"] == "pr-7" and only["signals"] == ["breaking-change"]


_FLOOR_SUBJECTS = [
    "Update libfoo to 2.0",
    "Upgrade libfoo from 1.0 to 2.0",
    "Release 5.9.0 of the client library",
    "Bump libfoo from 1.0 to 2.0 in /api",
    "chore: bump libfoo to 2.0",
    "Update foo to 2.0",
    "release: 2.0.0 of the client",
    "Removed src/old_module.py",
    "Adopt Postgres instead of MySQL",
    "feat!: bump libfoo to 2.0.0",
    "short",
]


@pytest.mark.parametrize("subject", _FLOOR_SUBJECTS)
def test_c18_the_floor_moves_only_for_a_breaking_bump(subject: str) -> None:
    assert adr_commits.passes_floor(subject, False) == adr_shape.is_decision_commit(subject)
    if not adr_shape.is_release_or_bump_subject(subject):
        assert adr_commits.passes_floor(subject, True) == adr_shape.is_decision_commit(subject)


@pytest.mark.parametrize(
    ("subject", "kept"),
    [
        ("Update libfoo to 2.0", True),
        ("Upgrade libfoo from 1.0 to 2.0", True),
        ("Release 5.9.0 of the client library", True),
        ("Bump libfoo from 1.0 to 2.0 in /api", False),
        ("chore: bump libfoo to 2.0", False),
        ("Update foo to 2.0", False),
    ],
)
def test_c18_a_breaking_bump_passes_unless_another_floor_check_fails(
    subject: str, kept: bool
) -> None:
    assert adr_shape.is_release_or_bump_subject(subject)
    assert not adr_shape.is_decision_commit(subject)
    assert adr_commits.passes_floor(subject, True) is kept
