"""Tests for adr_scan: which commits, pull requests and log entries are proposed (P1-P10, P12).

Ports the list cases of align-cli tests/adr-command.test.ts and the suppression cases of
tests/adr-writer.test.ts (MIT, Copyright (c) 2026 Align Tech Ltd, see LICENSE-align): a fix
commit is not proposed, a decision an ADR already links to is left out, and the link is compared
whole. Upstream seeds graph rows. Here the same inputs are commits, so each one needs a body
that states a reason. The other cases are new: each fix from the port plan, section 3, has one
that fails on upstream's rule, and so do E1 (decision-log entries) and E3 (breaking changes).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import adr_scan
import pytest
from adr_helpers import commit, git, hash_commit, new_repo, write

WHY = "Because the team already runs it in production and a second system needs a second on-call."


def _scan(repo: Path, prs: list[Any] | None = None, **kw: Any) -> dict[str, Any]:
    args = {"rev": "HEAD", "max_commits": 300, "since": None, **kw}
    result: dict[str, Any] = adr_scan.scan(
        repo, args["rev"], args["max_commits"], args["since"], prs
    )
    return result


def _ids(payload: dict[str, Any]) -> list[str]:
    return [item["id"] for item in payload["candidates"]]


def _titles(payload: dict[str, Any]) -> list[str]:
    return [item["title"] for item in payload["candidates"]]


def _pr(number: int = 12, **over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "number": number,
        "title": "Adopt Postgres instead of MySQL",
        "body": f"We move to Postgres. {WHY}",
        "url": f"https://github.com/o/r/pull/{number}",
        "merged_at": "2026-03-04T10:00:00Z",
        "author": {"login": "ada", "is_bot": False},
    }
    return {**base, **over}


def test_a_decision_with_a_stated_reason_is_proposed_and_a_fix_is_not(tmp_path: Path) -> None:
    repo = new_repo(tmp_path / "r")
    commit(repo, "Encode TRUE as FF- instead of 01-\n\nBecause FF- is what the runtime emits.\n")
    commit(repo, "fix: handle the empty queue\n\nBecause the worker crashed on empty input.\n")
    commit(repo, "chore: bump the lockfile for the weekly dependency refresh")
    payload = _scan(repo)
    assert _titles(payload) == ["Encode TRUE as FF- instead of 01-"]
    (item,) = payload["candidates"]
    assert item["kind"] == "commit" and item["id"].startswith("c-") and len(item["id"]) == 9
    assert item["reason"] == "Because FF- is what the runtime emits."
    assert item["date"] == "2026-01-02" and item["signals"] == []
    assert (
        payload["dropped"]["housekeeping"] == 1 and payload["dropped"]["not_decision_shaped"] == 1
    )
    assert payload["dropped"]["no_rationale"] == 0


def test_a_decision_title_with_no_stated_reason_is_dropped_and_counted(tmp_path: Path) -> None:
    repo = new_repo(tmp_path / "r")
    commit(repo, "Adopt Postgres for the event store")
    payload = _scan(repo)
    assert payload["candidates"] == []
    assert payload["dropped"]["no_rationale"] == 1


def test_a_title_that_states_a_rule_passes_the_rationale_gate_alone(tmp_path: Path) -> None:
    repo = new_repo(tmp_path / "r")
    commit(repo, "Switch to a hand-written parser instead of ANTLR")
    (item,) = _scan(repo)["candidates"]
    assert item["reason"] is None


def test_a_scoped_commit_with_a_decision_wording_is_kept(tmp_path: Path) -> None:
    # Upstream's `^\w+\([^)]*\):` dropped every scoped commit except feat(...).
    repo = new_repo(tmp_path / "r")
    commit(repo, f"arch(core): adopt event sourcing instead of CRUD\n\n{WHY}\n")
    commit(repo, f"fix(core): adopt a retry policy instead of none\n\n{WHY}\n")
    assert _titles(_scan(repo)) == ["arch(core): adopt event sourcing instead of CRUD"]


def test_the_commit_filters_see_a_merge_commits_promoted_subject(tmp_path: Path) -> None:
    repo = new_repo(tmp_path / "r")
    base = commit(repo, "Initial work")
    git(repo, "checkout", "-q", "-b", "topic")
    commit(repo, "wip on the topic", rel="t.txt")
    git(repo, "checkout", "-q", "main")
    git(
        repo, "merge", "--no-ff", "-q", "topic", "-m",
        f"Merge pull request #5 from o/topic\n\nAdopt Postgres instead of MySQL\n\n{WHY}\n",
    )  # fmt: skip
    payload = _scan(repo)
    (item,) = payload["candidates"]
    assert item["title"] == "Adopt Postgres instead of MySQL"
    assert item["source"]["pr_number"] == 5 and base != item["source"]["sha"]


def test_the_reason_leaves_out_a_trailer_under_it(tmp_path: Path) -> None:
    repo = new_repo(tmp_path / "r")
    reason = "We cap the pool at 12 because the gateway rejects more than twelve concurrent calls"
    commit(
        repo, f"Adopt a worker pool cap\n\n{reason}\n\nClaude-Session: https://claude.ai/code/s_1\n"
    )
    (item,) = _scan(repo)["candidates"]
    assert item["reason"] == reason and "Claude-Session" in item["excerpt"]


@pytest.mark.parametrize(
    "message",
    [
        "feat!: drop the v1 API",
        "feat(api)!: remove the legacy endpoints",
        "refactor(core)!: rename the public client",
        "feat: remove the v1 API\n\nBREAKING CHANGE: clients must send the new header.",
        "feat: remove the v1 API\n\nBREAKING-CHANGE: clients must send the new header.\n\nRefs: 12",
        "feat: remove the v1 API\n\nBREAKING CHANGE: send the header.\n\nCo-Authored-By: A <a@x>",
    ],
)
def test_e3_a_breaking_commit_is_kept_without_a_stated_rationale(
    tmp_path: Path, message: str
) -> None:
    repo = new_repo(tmp_path / "r")
    commit(repo, message)
    (item,) = _scan(repo)["candidates"]
    assert item["signals"] == ["breaking-change"]


@pytest.mark.parametrize(
    "message",
    [
        "feat: remove the v1 API entirely\n\nThis is not a BREAKING CHANGE: clients are fine.",
        "feat: remove the v1 API entirely\n\nThe BREAKING CHANGE: is below.\n\nMore prose.",
        "feat: drop the v1 API entirely",
        "chore!: drop support for the old toolchain version",
        "Remove the exclamation! from the log line",
    ],
)
def test_e3_a_commit_that_is_not_breaking_is_not_kept_by_the_signal(
    tmp_path: Path, message: str
) -> None:
    repo = new_repo(tmp_path / "r")
    commit(repo, message)
    assert _scan(repo)["candidates"] == []


def test_a_breaking_commit_with_a_reason_keeps_its_reason_and_signal(tmp_path: Path) -> None:
    repo = new_repo(tmp_path / "r")
    commit(repo, f"feat!: adopt the v2 wire format\n\n{WHY}\n")
    (item,) = _scan(repo)["candidates"]
    assert item["signals"] == ["breaking-change"] and item["reason"]


def test_max_commits_marks_the_result_truncated(tmp_path: Path) -> None:
    repo = new_repo(tmp_path / "r")
    for n in range(4):
        commit(repo, f"Adopt option number {n} instead of the old one\n\n{WHY}\n")
    capped = _scan(repo, max_commits=3)
    assert capped["truncated"] is True and capped["examined"]["commits"] == 3
    assert len(capped["candidates"]) == 3
    full = _scan(repo, max_commits=4)
    assert full["truncated"] is False and len(full["candidates"]) == 4


def test_since_and_rev_limit_the_history_read(tmp_path: Path) -> None:
    repo = new_repo(tmp_path / "r")
    old = commit(
        repo, f"Adopt the old way instead of none\n\n{WHY}\n", date="2020-01-01T00:00:00+00:00"
    )
    commit(
        repo, f"Adopt the new way instead of the old\n\n{WHY}\n", date="2026-06-01T00:00:00+00:00"
    )
    assert len(_scan(repo, since="2025-01-01")["candidates"]) == 1
    assert len(_scan(repo, rev=old)["candidates"]) == 1
    assert _scan(repo, rev=old)["head"] == old


@pytest.mark.parametrize(
    ("adr_text", "hidden"),
    [
        ("Decided in commit {sha}.", True),
        ("See {sha7} for the change.", True),
        ("See {sha9} for the change.", True),
        ("See ({sha7}).", True),
        ("See {sha6} for the change.", False),
        ("See x{sha7}y for the change.", False),
        ("See {sha7}0123 for the change.", False),
        ("Nothing relevant here.", False),
    ],
)
def test_an_adr_naming_the_commit_by_full_or_short_sha_hides_it(
    tmp_path: Path, adr_text: str, hidden: bool
) -> None:
    repo = new_repo(tmp_path / "r")
    sha = commit(repo, f"Adopt Postgres instead of MySQL\n\n{WHY}\n")
    text = adr_text.format(sha=sha, sha7=sha[:7], sha9=sha[:9], sha6=sha[:6])
    write(repo, "docs/adr/0001-a.md", f"# 1. A\n\n{text}\n")
    assert (_scan(repo)["candidates"] == []) is hidden


def test_an_adr_in_mdx_or_adoc_hides_a_decision_too(tmp_path: Path) -> None:
    repo = new_repo(tmp_path / "r")
    first = commit(repo, f"Adopt Postgres instead of MySQL\n\n{WHY}\n")
    second = commit(repo, f"Adopt Redis instead of Memcached\n\n{WHY}\n")
    write(repo, "docs/adr/0001-a.mdx", f"# 1. A\n\n{first[:8]}\n")
    write(repo, "docs/adr/0002-b.adoc", f"= 2. B\n\n{second}\n")
    assert _scan(repo)["candidates"] == []


def test_an_adr_naming_the_pull_request_number_hides_the_squash_commit(tmp_path: Path) -> None:
    repo = new_repo(tmp_path / "r")
    commit(repo, f"Adopt Postgres instead of MySQL (#42)\n\n{WHY}\n")
    commit(repo, f"Adopt Redis instead of Memcached (#7)\n\n{WHY}\n")
    write(repo, "docs/adr/0001-a.md", "# 1. A\n\nDecided in #42 and discussed in a#7 and in /#7.\n")
    assert _titles(_scan(repo)) == ["Adopt Redis instead of Memcached (#7)"]


def test_a_url_in_an_adr_is_compared_whole(tmp_path: Path) -> None:
    # issues/123 must not hide issues/12, and a link inside markdown or angle brackets counts.
    repo = new_repo(tmp_path / "r")
    commit(repo, "Initial work")
    write(
        repo,
        "docs/adr/0001-a.md",
        "Decided in https://github.com/o/r/pull/123.\nSee [it](https://github.com/o/r/pull/9) "
        "and <https://github.com/o/r/pull/10>\n",
    )
    prs = [_pr(12), _pr(123), _pr(9), _pr(10)]
    payload = _scan(repo, prs)
    assert _ids(payload) == ["pr-12"]
    assert payload["dropped"]["already_documented"] == 3


def test_a_git_scheme_link_in_an_adr_counts_as_a_link(tmp_path: Path) -> None:
    repo = new_repo(tmp_path / "r")
    commit(repo, "Initial work")
    write(repo, "docs/adr/0001-a.md", "Decided in git://example.com/o/r/pull/5.\n")
    assert _ids(_scan(repo, [_pr(5, url="https://example.com/o/r/pull/5")])) == ["pr-5"]


def test_with_no_adr_folder_nothing_is_suppressed(tmp_path: Path) -> None:
    repo = new_repo(tmp_path / "r")
    sha = commit(repo, f"Adopt Postgres instead of MySQL\n\n{WHY}\n")
    write(repo, "notes/0001-a.md", f"# 1. A\n\n{sha}\n")
    assert len(_scan(repo)["candidates"]) == 1


def test_pull_request_selection_keeps_merged_non_bot_reasoned_decisions(tmp_path: Path) -> None:
    repo = new_repo(tmp_path / "r")
    commit(repo, "Initial work")
    prs = [
        _pr(1),
        _pr(2, merged_at=None),
        _pr(3, author={"login": "dependabot[bot]"}),
        _pr(4, author={"login": "renovate", "type": "Bot"}),
        _pr(5, title="Bump lodash from 4.17.20 to 4.17.21"),
        _pr(6, body="Adds a thing."),
        _pr(7, title="fix: typo in the docs for the first paragraph"),
        _pr(8, url=None),
        _pr(9, title=""),
        _pr(10, mergedAt="2026-02-30T00:00:00Z", merged_at=None),
        {"number": 11, "title": "Adopt X instead of Y", "body": WHY, "html_url": "https://h/p/11",
         "mergedAt": "2026-03-04T10:00:00Z", "user": {"login": "ada", "type": "User"},
         "mergeCommit": {"oid": "A" * 40}},
    ]  # fmt: skip
    payload = _scan(repo, prs)
    assert _ids(payload) == ["pr-1", "pr-11"]
    by_id = {item["id"]: item for item in payload["candidates"]}
    assert by_id["pr-1"]["kind"] == "pr" and by_id["pr-1"]["date"] == "2026-03-04"
    assert by_id["pr-1"]["source"] == {
        "number": 1,
        "url": "https://github.com/o/r/pull/1",
        "sha": None,
    }
    assert by_id["pr-11"]["source"]["sha"] == "a" * 40
    dropped = payload["dropped"]
    assert (dropped["pr_bot"], dropped["pr_housekeeping"], dropped["pr_no_reason"]) == (2, 1, 1)
    assert dropped["pr_incomplete"] == 4 and dropped["pr_not_decision_shaped"] == 1
    assert payload["examined"]["prs"] == 11


def test_a_pull_request_export_item_that_is_not_an_object_counts_as_incomplete(
    tmp_path: Path,
) -> None:
    repo = new_repo(tmp_path / "r")
    commit(repo, "Initial work")
    payload = _scan(repo, [3, "x", None, _pr(1)])
    assert _ids(payload) == ["pr-1"] and payload["dropped"]["pr_incomplete"] == 3


def test_p10_a_commit_that_a_kept_pull_request_replaced_is_dropped(tmp_path: Path) -> None:
    repo = new_repo(tmp_path / "r")
    squash = commit(repo, f"Adopt Postgres instead of MySQL (#12)\n\n{WHY}\n")
    unrelated = commit(repo, f"Adopt Redis instead of Memcached (#77)\n\n{WHY}\n")
    other = commit(repo, f"Adopt Kafka instead of RabbitMQ\n\n{WHY}\n")
    payload = _scan(repo, [_pr(12, merge_commit_sha=squash), _pr(30, merge_commit_sha=other)])
    commits = [item for item in payload["candidates"] if item["kind"] == "commit"]
    assert [item["id"] for item in commits] == [f"c-{unrelated[:7]}"]
    assert sorted(_ids(payload)) == sorted(["pr-12", "pr-30", f"c-{unrelated[:7]}"])
    assert payload["dropped"]["covered_by_pr"] == 2


def test_p10_a_pull_request_with_no_reason_covers_nothing(tmp_path: Path) -> None:
    repo = new_repo(tmp_path / "r")
    commit(repo, f"Adopt Postgres instead of MySQL (#12)\n\n{WHY}\n")
    payload = _scan(repo, [_pr(12, body="Adds a thing.")])
    assert [item["kind"] for item in payload["candidates"]] == ["commit"]


def test_a_rerun_after_an_adr_names_each_decision_proposes_none_of_them(tmp_path: Path) -> None:
    repo = new_repo(tmp_path / "r")
    squash = commit(repo, f"Adopt Postgres instead of MySQL (#12)\n\n{WHY}\n")
    plain = commit(repo, f"Adopt Redis instead of Memcached\n\n{WHY}\n")
    write(repo, "DECISIONS.md", f"## D17 - Use pnpm everywhere\n\nWe use pnpm because {WHY}\n")
    prs = [_pr(12, merge_commit_sha=squash)]
    first = _scan(repo, prs)
    assert sorted(_ids(first)) == sorted(["pr-12", f"c-{plain[:7]}", "log-D17"])
    # Name only the pull request URL, the plain commit's short sha and the log id.
    write(
        repo,
        "docs/adr/0001-a.md",
        f"# 1. A\n\nhttps://github.com/o/r/pull/12 {plain[:8]} D17\n",
    )
    second = _scan(repo, prs)
    assert second["candidates"] == []
    assert second["dropped"]["covered_by_pr"] == 1  # the squash commit stays covered


def test_the_scan_result_names_its_repository_head_and_adr_folders(tmp_path: Path) -> None:
    repo = new_repo(tmp_path / "r")
    head = commit(repo, "Initial work")
    write(repo, "docs/adr/0001-a.md", "# 1. A\n")
    payload = _scan(repo)
    assert payload["repo"] == str(repo) and payload["head"] == head
    assert payload["adr_folders"] == ["docs/adr"]
    assert payload["examined"] == {
        "commits": 1,
        "prs": 0,
        "adr_files": 1,
        "adr_files_skipped": 0,
        "log_files": 0,
        "log_files_skipped": 0,
    }
    assert payload["shallow"] is False and payload["walk_truncated"] is False
    assert set(payload["dropped"]) == set(adr_scan.DROP_KEYS)


def test_a_commit_message_with_control_bytes_leaves_none_in_the_excerpt(tmp_path: Path) -> None:
    repo = new_repo(tmp_path / "r")
    first = commit(repo, "Initial work")
    tree = git(repo, "rev-parse", f"{first}^{{tree}}").strip()
    ident = "Ada <a@x> 1714557600 +0000"
    message = "Adopt Postgres instead of MySQL\n\nBecause it is\x00safe \x1b[31mred\x1b[0m here.\n"
    raw = f"tree {tree}\nparent {first}\nauthor {ident}\ncommitter {ident}\n\n{message}"
    sha = hash_commit(repo, raw)
    git(repo, "update-ref", "refs/heads/main", sha)
    (item,) = _scan(repo)["candidates"]
    assert "\x00" not in item["excerpt"] and "\x1b" not in item["excerpt"]
    assert item["date"] == "2024-05-01"


@pytest.mark.parametrize(
    ("remote", "commit_url"),
    [
        ("https://github.com/o/r.git", "https://github.com/o/r/commit/{sha}"),
        ("git@github.com:o/r.git", "https://github.com/o/r/commit/{sha}"),
        ("ssh://git@github.com:22/o/r", "https://github.com/o/r/commit/{sha}"),
        ("https://gitlab.com/g/sub/r.git", "https://gitlab.com/g/sub/r/-/commit/{sha}"),
        ("https://ghp_SECRET:x-oauth@github.com/o/r.git", "https://github.com/o/r/commit/{sha}"),
        ("https://example.com/o/r.git", None),
        ("/srv/git/r.git", None),
        ("file:///srv/git/r.git", None),
    ],
)
def test_the_commit_url_comes_from_the_origin_remote_without_credentials(
    tmp_path: Path, remote: str, commit_url: str | None
) -> None:
    repo = new_repo(tmp_path / "r")
    sha = commit(repo, f"Adopt Postgres instead of MySQL (#9)\n\n{WHY}\n")
    git(repo, "remote", "add", "origin", remote)
    (item,) = _scan(repo)["candidates"]
    assert item["source"]["url"] == (commit_url.format(sha=sha) if commit_url else None)
    assert "SECRET" not in str(item) and "x-oauth" not in str(item)
    expected_pull = (
        "https://github.com/o/r/pull/9" if "github.com/o/r" in (commit_url or "") else None
    )
    assert item["source"]["pr_url"] == expected_pull


def test_a_repo_with_no_origin_is_normal(tmp_path: Path) -> None:
    repo = new_repo(tmp_path / "r")
    commit(repo, f"Adopt Postgres instead of MySQL\n\n{WHY}\n")
    (item,) = _scan(repo)["candidates"]
    assert item["source"]["url"] is None


def test_scan_writes_nothing_in_the_repository(tmp_path: Path) -> None:
    repo = new_repo(tmp_path / "r")
    commit(repo, f"Adopt Postgres instead of MySQL\n\n{WHY}\n")
    write(repo, "docs/adr/0001-a.md", "# 1. A\n")
    git(repo, "add", "-A")
    before = git(repo, "status", "--porcelain=v1", "-uall")
    _scan(repo)
    assert git(repo, "status", "--porcelain=v1", "-uall") == before


def test_an_adr_in_any_located_folder_hides_a_decision_not_only_the_output_one(
    tmp_path: Path,
) -> None:
    repo = new_repo(tmp_path / "r")
    first = commit(repo, f"Adopt Postgres instead of MySQL\n\n{WHY}\n")
    second = commit(repo, f"Adopt Redis instead of Memcached\n\n{WHY}\n")
    write(repo, "docs/adr/0001-a.md", f"# 1. A\n\nSee {first[:8]}.\n")
    write(repo, "docs/decisions/0001-b.md", f"# 1. B\n\nSee {second[:8]}.\n")
    payload = _scan(repo)
    assert payload["candidates"] == []
    assert payload["adr_folders"] == ["docs/adr", "docs/decisions"]
    assert payload["dropped"]["already_documented"] == 2


def test_a_pull_request_body_with_crlf_line_endings_gives_the_same_reason(tmp_path: Path) -> None:
    repo = new_repo(tmp_path / "r")
    commit(repo, "Initial work")
    lf = f"We move to Postgres.\n\n{WHY}\n"
    payload = _scan(repo, [_pr(1, body=lf), _pr(2, body=lf.replace("\n", "\r\n"))])
    one, two = (item for item in payload["candidates"])
    assert one["reason"] == two["reason"] and one["reason"]
    assert "\r" not in two["excerpt"]


def test_e1_a_decision_log_entry_with_an_id_and_no_adr_is_a_candidate(tmp_path: Path) -> None:
    repo = new_repo(tmp_path / "r")
    commit(repo, "Initial work")
    write(
        repo,
        "DECISIONS.md",
        f"## D17 - Use pnpm everywhere\n\nWe use pnpm because {WHY}\nDecided: 2026-03-04\n\n"
        "## Misc notes without an id\n\nThis section has no id but is long enough to count.\n",
    )
    payload = _scan(repo)
    (item,) = payload["candidates"]
    assert (item["id"], item["kind"], item["title"]) == (
        "log-D17",
        "decision-log",
        "D17 - Use pnpm everywhere",
    )
    assert item["source"] == {"file": "DECISIONS.md", "entry_id": "D17"}
    assert item["date"] == "2026-03-04" and item["reason"] and item["signals"] == []
    assert payload["dropped"]["log_no_id"] == 1


def test_e1_an_adr_that_names_the_id_hides_the_entry_but_only_as_a_whole_word(
    tmp_path: Path,
) -> None:
    repo = new_repo(tmp_path / "r")
    commit(repo, "Initial work")
    write(repo, "DECISIONS.md", "D17: Use pnpm everywhere\nD18: Use uv for Python tooling\n")
    write(repo, "docs/adr/0001-a.md", "# 1. A\n\nThis follows D170, and also D18.\n")
    payload = _scan(repo)
    assert _ids(payload) == ["log-D17"]
    assert payload["dropped"]["already_documented"] == 1


def test_e1_an_entry_id_that_repeats_gets_a_distinct_candidate_id(tmp_path: Path) -> None:
    repo = new_repo(tmp_path / "r")
    commit(repo, "Initial work")
    write(repo, "DECISIONS.md", "D1: Use pnpm everywhere\n")
    write(repo, "docs/DECISIONS.md", "D1: Use uv for Python tooling\n")
    assert _ids(_scan(repo)) == ["log-D1", "log-D1.2"]
