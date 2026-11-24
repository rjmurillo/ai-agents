"""Tests for the PR #7527 CodeRabbit minor findings that did not fit the review summary."""

from __future__ import annotations

import os
import subprocess
import time
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

FENCE4, FENCE3 = "`" * 4, "`" * 3


def test_a_shorter_fence_inside_a_longer_one_does_not_close_it() -> None:
    log = f"## D-1 - One\n\n{FENCE4}\n{FENCE3}\n## D-17 - Example\n{FENCE4}\n\n## D-2 - Two\n"

    assert [entry.id for entry in adr_log.split_decision_log(log)] == ["D-1", "D-2"]


def test_the_first_valid_date_wins_over_an_invalid_earlier_one() -> None:
    assert adr_log.entry_date("date: 2026-02-30\ndate: 2026-03-01") == "2026-03-01"


def test_a_date_inside_a_fenced_example_is_not_metadata() -> None:
    assert adr_log.entry_date(f"Example:\n{FENCE3}\ndate: 2026-03-01\n{FENCE3}\n") is None


def test_an_id_field_without_a_space_is_not_the_title() -> None:
    body = "  Use pnpm everywhere for every package\n"

    tight = adr_log.split_decision_log(f"- id:D-001\n{body}")
    spaced = adr_log.split_decision_log(f"- id: D-001\n{body}")

    assert [e.title for e in tight] == [e.title for e in spaced]
    assert tight[0].title == "Use pnpm everywhere for every package"


def test_a_release_heading_at_the_start_of_a_policy_body_ends_it() -> None:
    assert adr_docs.section_body("changelog", "# 1.2.0\n\n- Added a thing") == ""


def test_a_trailing_rule_is_removed_and_blank_runs_stay_linear() -> None:
    body = "Text" + "\n" * 200_000 + "more text"

    start = time.perf_counter()
    kept = adr_docs._without_trailing_rule(body)

    assert kept == body and time.perf_counter() - start < 1.0
    assert adr_docs._without_trailing_rule("Use semver.\n\n---") == "Use semver."
    assert adr_docs._without_trailing_rule("---") == "---"


def test_a_long_author_header_is_capped() -> None:
    raw = b"tree " + b"0" * 40 + b"\nauthor " + b"a" * 20_000 + b"\n\nAdopt Rust\n"

    record = adr_commits.parse_commit_object("1" * 40, raw)

    assert len(record.author) <= adr_commits.MAX_SUBJECT_CHARS


@pytest.mark.skipif(os.name == "nt", reason="a trailing space is not allowed in a Windows name")
def test_a_work_tree_path_that_ends_in_a_space_is_kept(tmp_path: Path) -> None:
    repo = new_repo(tmp_path / "r ")

    assert adr_scan.repo_root(repo) == repo


def test_a_missing_argument_prints_json_and_exits_two() -> None:
    code, payload = run_cli("locate")

    assert code == 2 and payload["error"] == "config" and "--repo" in payload["message"]


@pytest.mark.parametrize(("version", "refused"), [((2, 45, 0), True), ((2, 45, 1), False)])
def test_a_partial_clone_needs_a_git_that_honors_no_lazy_fetch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, version: tuple[int, ...], refused: bool
) -> None:
    repo = new_repo(tmp_path / "r")
    commit(repo, "Initial work")
    git(repo, "config", "extensions.partialClone", "origin")
    monkeypatch.setattr(bootstrap_adr, "_git_version", lambda _root: version)

    if refused:
        with pytest.raises(adr_scan.ConfigError, match="partial clone"):
            bootstrap_adr._refuse_lazy_fetch(repo)
    else:
        bootstrap_adr._refuse_lazy_fetch(repo)


def test_a_full_clone_is_never_refused_for_its_git_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = new_repo(tmp_path / "r")
    commit(repo, "Initial work")
    monkeypatch.setattr(bootstrap_adr, "_git_version", lambda _root: (2, 0, 0))

    bootstrap_adr._refuse_lazy_fetch(repo)


def test_a_work_tree_added_during_the_scan_still_refuses_the_out_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = new_repo(tmp_path / "r")
    commit(repo, "Initial work")
    linked = tmp_path / "linked"
    real_scan = adr_scan.scan

    def racing(*args: Any) -> dict[str, Any]:
        git(repo, "worktree", "add", "-q", str(linked))
        payload: dict[str, Any] = real_scan(*args)
        return payload

    monkeypatch.setattr(bootstrap_adr, "scan", racing)
    out = linked / "scan.json"

    assert bootstrap_adr.main(["scan", "--repo", str(repo), "--out", str(out)]) == 2
    assert not out.exists()


# Round 8 review findings

WHY = "Because the team already runs it in production and a second system needs a second on-call."
ORIGIN = "https://github.com/o/r"


def test_a_long_dotted_token_costs_linear_memory() -> None:
    start = time.perf_counter()
    existing = adr_docs.ExistingAdrs([("a.md", "a" + ".a" * 200_000)])

    assert time.perf_counter() - start < 2.0 and len(existing.ids) <= 3


def test_a_filtered_covered_commit_still_hides_its_pull_request(tmp_path: Path) -> None:
    repo = new_repo(tmp_path / "r")
    write(repo, "docs/adr/0001-first.md", "# 1. First\n\n## Status\n\nAccepted\n")
    commit(repo, "Initial work")
    git(repo, "remote", "add", "origin", f"{ORIGIN}.git")
    squash = commit(repo, "feat: adopt Postgres for storage (#5)")
    write(repo, "docs/adr/0002-pg.md", f"# 2. Postgres\n\nFrom commit {squash}.\n")
    commit(repo, "docs: record the Postgres decision")
    row = {
        "number": 5,
        "title": "Adopt Postgres for storage",
        "body": WHY,
        "url": f"{ORIGIN}/pull/5",
        "merged_at": "2026-03-04T10:00:00Z",
        "author": {"login": "ada"},
    }

    payload = adr_scan.scan(repo, "HEAD", 300, None, [row])

    assert payload["candidates"] == [] and payload["dropped"]["already_documented"] == 1


def test_a_covered_commit_never_hands_over_another_prs_url() -> None:
    pr = adr_scan._Pending({"signals": [], "reason": "x"}, (), (f"{ORIGIN}/pull/9",), 9)
    source = {"url": f"{ORIGIN}/commit/{'a' * 40}"}
    covered = adr_scan._Pending(
        {"signals": [], "reason": None, "source": source},
        ("a" * 40,),
        (source["url"], f"{ORIGIN}/pull/3"),
        3,
    )

    adr_scan._absorb(pr, covered)

    assert f"{ORIGIN}/pull/3" not in pr.urls and source["url"] in pr.urls


def test_work_trees_falls_back_when_git_has_no_z(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = new_repo(tmp_path / "main")
    commit(repo, "Initial work")
    real = adr_write.git_text

    def old_git(root: Path, *args: str, ok: tuple[int, ...] = (0,)) -> Any:
        if "-z" in args:
            return subprocess.CompletedProcess(args, 129, "", "error: unknown switch `z'")
        return real(root, *args, ok=ok)

    monkeypatch.setattr(adr_write, "git_text", old_git)

    assert adr_write.work_trees(repo) == [repo]


def test_an_id_field_drops_a_trailing_sentence_dot() -> None:
    entries = adr_log.split_decision_log(f"- id: D-7. Use Postgres\n  {WHY}\n")

    assert [entry.id for entry in entries] == ["D-7"]


def test_a_run_of_spaces_before_prose_is_rejected_quickly() -> None:
    start = time.perf_counter()
    found = adr_shape.FIXES_ONLY.search("Fixes #1" + " " * 50_000 + "x")

    assert found is None and time.perf_counter() - start < 0.5


def test_a_pr_url_with_a_unicode_blank_is_incomplete() -> None:
    dropped: dict[str, int] = {}
    row = {
        "number": 5,
        "title": "Adopt Postgres for storage",
        "body": WHY,
        "url": f"{ORIGIN}/pull /5",
        "merged_at": "2026-03-04T10:00:00Z",
        "author": {"login": "ada"},
    }

    assert adr_commits.select_prs([row], dropped) == [] and dropped["pr_incomplete"] == 1


# Round 9 review findings


def test_an_abbreviated_out_flag_is_refused(tmp_path: Path) -> None:
    repo = new_repo(tmp_path / "r")
    commit(repo, "Initial work")
    out = tmp_path / "abbr.json"

    code, payload = run_cli("scan", "--repo", str(repo), "--ou", str(out))

    assert code == 2 and payload["error"] == "config" and not out.exists()


@pytest.mark.parametrize(
    ("version", "refused"),
    [((2, 39, 3), True), ((2, 39, 4), False), ((2, 44, 1), False), ((2, 45, 0), True)],
)
def test_a_promisor_remote_alone_marks_a_partial_clone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, version: tuple[int, int, int], refused: bool
) -> None:
    repo = new_repo(tmp_path / "r")
    commit(repo, "Initial work")
    git(repo, "config", "remote.origin.url", "https://example.invalid/o/r.git")
    git(repo, "config", "remote.origin.promisor", "true")
    monkeypatch.setattr(bootstrap_adr, "_git_version", lambda _root: version)

    if refused:
        with pytest.raises(adr_scan.ConfigError, match="partial clone"):
            bootstrap_adr._refuse_lazy_fetch(repo)
    else:
        bootstrap_adr._refuse_lazy_fetch(repo)


def test_a_promisor_set_to_false_is_not_a_partial_clone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = new_repo(tmp_path / "r")
    commit(repo, "Initial work")
    git(repo, "config", "remote.origin.promisor", "false")
    monkeypatch.setattr(bootstrap_adr, "_git_version", lambda _root: (2, 30, 0))

    bootstrap_adr._refuse_lazy_fetch(repo)


def test_a_long_author_name_keeps_its_date() -> None:
    name = b"a" * 4100
    raw = b"tree " + b"0" * 40 + b"\nauthor " + name + b" <a@b> 1700000000 +0000\n\nAdopt Rust\n"

    record = adr_commits.parse_commit_object("1" * 40, raw)

    assert (
        record.date.startswith("2023-11-14") and len(record.author) <= adr_commits.MAX_SUBJECT_CHARS
    )


def test_a_dotted_id_cited_as_a_file_name_is_named() -> None:
    existing = adr_docs.ExistingAdrs([("a.md", "See auth.session.md for the decision.")])

    assert existing.names_id("auth.session") and existing.names_id("auth")
