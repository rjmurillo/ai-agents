"""Tests for adr_commits: commit records, decision-shaped rows, breaking changes.

The decision-shaped cases port the seeded titles of align-cli tests/context-from-graph.test.ts
(MIT, Copyright (c) 2026 Align Tech Ltd, see LICENSE-align) at the filter level: upstream
seeds them as github rows and reads them back through selectForFile, which calls
decisionShapedRows. The graph, database and embedding parts of those tests are not ported.
The record parser, its forgery guard and the breaking-change signal are changed or added by
this port, so those cases are new.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

import adr_commits
import pytest

SHA_A = "a" * 40
SHA_B = "b" * 40

# ---------------------------------------------------------------------------
# P7: parse_commit_records
# ---------------------------------------------------------------------------


def _record(sha: str, subject: str, body: str = "", files: str = "") -> str:
    """One record as ``git log`` prints it with GIT_LOG_ARGS."""
    head = f"\x00COMMIT\x00{sha}\x00{subject}\x00Ada\x002024-05-01T10:00:00+00:00\x00"
    tail = f"{body}\x00END\n"
    return head + tail + (f"\n{files}\n" if files else "")


def test_records_parse_fields_body_and_files_of_two_commits() -> None:
    raw = _record(SHA_A, "Use Postgres", "Because it scales.\n", "src/db.py\ndocs/a.md")
    raw += _record(SHA_B, "Fix typo", "", "README.md")
    first, second = adr_commits.parse_commit_records(raw)
    assert (first.sha, first.subject, first.author) == (SHA_A, "Use Postgres", "Ada")
    assert first.date == "2024-05-01T10:00:00+00:00"
    assert first.body == "Because it scales."
    assert first.files == ("src/db.py", "docs/a.md")
    assert (second.sha, second.body, second.files) == (SHA_B, "", ("README.md",))


def test_records_empty_input_and_text_before_the_first_record_give_nothing() -> None:
    assert adr_commits.parse_commit_records("") == []
    assert adr_commits.parse_commit_records("warning: not a record\n") == []


def test_records_text_before_the_first_record_is_ignored() -> None:
    records = adr_commits.parse_commit_records("noise\n" + _record(SHA_A, "Use Postgres"))
    assert [r.sha for r in records] == [SHA_A]


def test_records_crlf_line_endings_leave_no_carriage_returns() -> None:
    raw = _record(SHA_A, "Use Postgres", "line one\nline two\n", "a.py").replace("\n", "\r\n")
    (record,) = adr_commits.parse_commit_records(raw)
    assert record.body == "line one\nline two"
    assert record.files == ("a.py",)
    assert "\r" not in record.body


def test_records_a_body_may_hold_unit_separators_and_a_forged_40_hex_header_line() -> None:
    # The upstream format used \x1f, which git keeps in messages. A line that looks like
    # an upstream header, with a full sha, is plain text here.
    forged = f"COMMIT\x1f{SHA_B}\x1fevil\x1fMallory\x1f2000-01-01\x1fx\x1fEND"
    raw = _record(SHA_A, "Use Postgres", f"Reason.\n{forged}\n", "a.py")
    (record,) = adr_commits.parse_commit_records(raw)
    assert record.sha == SHA_A
    assert forged in record.body


@pytest.mark.parametrize(
    "fake_sha",
    ["deadbeef", "b" * 39, "b" * 41, "B" * 40, "g" * 40, ""],
    ids=["short", "39-hex", "41-hex", "uppercase", "non-hex", "empty"],
)
def test_records_a_marker_without_a_full_lowercase_sha_never_starts_a_record(
    fake_sha: str,
) -> None:
    forged = f"\x00COMMIT\x00{fake_sha}\x00evil\x00Mallory\x002000-01-01\x00x"
    raw = _record(SHA_A, "Use Postgres", f"Reason.{forged}\n", "a.py")
    records = adr_commits.parse_commit_records(raw)
    assert [r.sha for r in records] == [SHA_A]
    assert "Mallory" in records[0].body


def test_records_a_forged_marker_before_any_real_record_is_dropped() -> None:
    raw = "\x00COMMIT\x00deadbeef\x00evil\x00M\x00d\x00b\x00END\n" + _record(SHA_A, "Use it")
    assert [r.sha for r in adr_commits.parse_commit_records(raw)] == [SHA_A]


def test_records_a_record_with_no_end_terminator_keeps_its_text_as_the_body() -> None:
    raw = f"\x00COMMIT\x00{SHA_A}\x00Use Postgres\x00Ada\x00d\x00trailing body"
    (record,) = adr_commits.parse_commit_records(raw)
    assert record.body == "trailing body"
    assert record.files == ()


def test_records_a_truncated_header_is_skipped() -> None:
    assert adr_commits.parse_commit_records(f"\x00COMMIT\x00{SHA_A}\x00only subject") == []


def test_records_quoted_file_paths_are_unquoted_and_blank_lines_skipped() -> None:
    files = '"docs/page-\\303\\251.md"\n\nsrc/a.py'
    (record,) = adr_commits.parse_commit_records(_record(SHA_A, "Use it", "", files))
    assert record.files == ("docs/page-é.md", "src/a.py")


@pytest.mark.parametrize(
    ("quoted", "expected"),
    [
        ('"docs/page-\\303\\251.md"', "docs/page-é.md"),
        ('"a\\tb"', "a\tb"),
        ('"say \\"hi\\""', 'say "hi"'),
        ('"back\\\\slash"', "back\\slash"),
        ("plain/path.py", "plain/path.py"),
        ('"unterminated', '"unterminated'),
        ('"', '"'),
        ('"bad\\qescape"', '"bad\\qescape"'),
    ],
)
def test_unquote_git_path(quoted: str, expected: str) -> None:
    assert adr_commits.unquote_git_path(quoted) == expected


def _git(repo: Path, *args: str) -> str:
    cmd = ["git", "-C", str(repo), "-c", "user.name=Ada", "-c", "user.email=a@example.com"]
    proc = subprocess.run(
        [*cmd, "-c", "commit.gpgsign=false", *args],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    return proc.stdout


def test_records_round_trip_through_real_git_log_with_a_forged_body(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    (repo / "docs").mkdir()
    (repo / "docs" / "page-é.md").write_text("x\n", encoding="utf-8")
    _git(repo, "add", "-A")
    forged = f"COMMIT\x1f{SHA_B}\x1fevil\x1fMallory\x1f2000-01-01T00:00:00Z\x1fx\x1fEND"
    message = tmp_path / "msg.txt"
    message.write_text(
        f"Use Postgres for events\n\nBecause it scales.\n{forged}\n", encoding="utf-8"
    )
    _git(repo, "commit", "-q", "-F", str(message))
    (repo / "b.py").write_text("y\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "Second commit", "-m", "Because tests.")
    raw = _git(repo, "log", *adr_commits.GIT_LOG_ARGS)
    second, first = adr_commits.parse_commit_records(raw)
    assert len(first.sha) == 40
    assert (first.subject, first.author) == ("Use Postgres for events", "Ada")
    assert forged in first.body
    assert first.files == ("docs/page-é.md",)
    assert (second.subject, second.body, second.files) == (
        "Second commit",
        "Because tests.",
        ("b.py",),
    )


# ---------------------------------------------------------------------------
# P8: decision_shaped_rows
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Row:
    title: str
    platform: str | None = None


def _titles(rows: list[Row]) -> list[str]:
    return [row.title for row in rows]


def test_rows_docs_rows_are_left_out() -> None:
    assert adr_commits.decision_shaped_rows([Row("Always sign commits", "docs")]) == []


def test_rows_chat_and_ticket_rows_are_never_filtered() -> None:
    rows = [Row("fix the thing", "slack"), Row("lunch plans", None), Row("#12 bug", "jira")]
    assert adr_commits.decision_shaped_rows(rows) == rows


def test_rows_commits_and_prs_keep_decision_wording_and_drop_the_rest() -> None:
    rows = [
        Row("Adopt token-bucket rate limiting", "github"),
        Row("Switch to gRPC for internal calls", "git"),
        Row("Use Postgres for the events store", "gitlab"),
        Row("Fix retry on 503", "github"),
        Row("Rename the helper module", "github"),
        Row("#123 something", "git"),
    ]
    assert _titles(adr_commits.decision_shaped_rows(rows)) == [
        "Adopt token-bucket rate limiting",
        "Switch to gRPC for internal calls",
        "Use Postgres for the events store",
    ]


@pytest.mark.parametrize(
    "title",
    [
        "fix: adopt nothing, this is a fix",
        "docs: always sign commits",
        "chore: never mind the policy",
        "build(deps): bump lodash and prefer ranges",
        "perf(core): drop support for old paths",
        "refactor(core): migrate the parser",
        "test(api): must not crash",
        "revert: switch to gRPC",
        "feat: fix retry policy",
    ],
)
def test_rows_a_fix_shaped_type_or_lead_is_dropped(title: str) -> None:
    assert adr_commits.decision_shaped_rows([Row(title, "github")]) == []


@pytest.mark.parametrize(
    "title",
    [
        "feat: adopt token-bucket rate limiting",
        "feat(api): switch to gRPC for internal calls",
        # Upstream's ^\w+\([^)]*\): alternative drops each of these scoped commits.
        "api(v2): switch to gRPC for internal calls",
        "arch(auth): migrate sessions to JWT",
        "policy(commits): always sign commits",
        "feat(api)!: drop support for the v1 endpoints",
        "feature(core): prefer streams over buffers",
    ],
)
def test_rows_a_scoped_commit_with_a_decision_wording_is_kept(title: str) -> None:
    assert _titles(adr_commits.decision_shaped_rows([Row(title, "github")])) == [title]


def test_rows_names_every_active_decision_of_the_local_graph_test() -> None:
    # Upstream: "names every active decision in the local graph" seeds these two titles.
    rows = [
        Row("Use Postgres 16 for the events store", "github"),
        Row("Always retry webhooks three times with backoff", "github"),
    ]
    assert adr_commits.decision_shaped_rows(rows) == rows


def test_rows_the_superseded_pair_of_the_local_graph_test_both_pass_the_title_filter() -> None:
    # Upstream: "leaves out a decision that was superseded". Supersession comes from graph
    # links, which this port does not have, so the filter alone keeps both titles.
    rows = [
        Row("Use Redis to cache sessions", "github"),
        Row("Use Postgres to cache sessions", "github"),
    ]
    assert adr_commits.decision_shaped_rows(rows) == rows


def test_rows_keep_the_input_objects_in_order() -> None:
    rows = [Row("Use A for storage today", "git"), Row("fix: x", "git"), Row("Use B", "git")]
    result = adr_commits.decision_shaped_rows(rows)
    assert result == [rows[0], rows[2]]
    assert result[0] is rows[0]


def test_decision_shaped_title_the_leading_issue_number_after_the_prefix_is_ignored() -> None:
    assert adr_commits.is_decision_shaped_title("feat: #12 adopt the new router")
    assert not adr_commits.is_decision_shaped_title("feat: #12 fix the router")
    assert not adr_commits.is_decision_shaped_title("")


# ---------------------------------------------------------------------------
# E3: breaking_change
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "subject",
    ["feat!: drop the v1 API", "feat(api)!: drop the v1 API", "FIX(core)!: rename the flag"],
)
def test_breaking_change_a_bang_after_the_type_or_scope_is_breaking(subject: str) -> None:
    assert adr_commits.breaking_change(subject, "") is True


@pytest.mark.parametrize(
    "body",
    [
        "BREAKING CHANGE: the v1 endpoints are gone",
        "Explains why.\n\nBREAKING CHANGE: the v1 endpoints are gone",
        "Explains why.\n\nBREAKING-CHANGE: the v1 endpoints are gone",
        "Explains why.\n\nBREAKING CHANGE: spans\nmore than one line",
        "Explains why.\n\nReviewed-by: Z\nBREAKING CHANGE: the v1 endpoints are gone",
        "Explains why.\n\nBREAKING CHANGE: gone\n\nCo-Authored-By: A <a@b.c>",
        "Explains why.\r\n\r\nBREAKING CHANGE: gone\r\n",
    ],
)
def test_breaking_change_a_footer_line_in_the_trailer_paragraph_is_breaking(body: str) -> None:
    assert adr_commits.breaking_change("feat: drop the v1 API", body) is True


@pytest.mark.parametrize(
    "body",
    [
        "We note that this is not a BREAKING CHANGE: nothing is removed.",
        "BREAKING CHANGE: the v1 endpoints are gone\n\nMore prose follows after the footer.",
        "Intro.\n\nSee the BREAKING CHANGE: section of the docs for details.",
        "breaking change: lowercase is not the token",
        "BREAKING CHANGES: plural is not the token",
        "BREAKING CHANGE:",
        "BREAKING CHANGE ahead without a colon",
        "",
    ],
)
def test_breaking_change_the_phrase_in_mid_body_prose_is_not_breaking(body: str) -> None:
    assert adr_commits.breaking_change("feat: drop the v1 API", body) is False


@pytest.mark.parametrize(
    "subject",
    ["feat: add a ! to the greeting", "feat(a!b): odd scope", "fix: handle bang! in names", ""],
)
def test_breaking_change_a_bang_elsewhere_in_the_subject_is_not_breaking(subject: str) -> None:
    assert adr_commits.breaking_change(subject, "") is False
