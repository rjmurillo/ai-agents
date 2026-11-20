"""Tests for commit object parsing and the rev-list plus cat-file reader (P7, replaced).

Upstream align-cli parsed delimited ``git log`` text and guarded against a forged header
with a 40-hex check (MIT, Copyright (c) 2026 Align Tech Ltd, see LICENSE-align). This port
reads raw commit objects through ``git cat-file --batch``, so these cases are new: a message
with NUL bytes and a fake record header must stay the body of the one real commit.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import adr_commits
import adr_git
import pytest
from adr_helpers import commit, git, hash_commit, new_repo

SHA = "a" * 40
FORGED = f"\x00COMMIT\x00{'b' * 40}\x00evil\x00Mallory\x002000-01-01T00:00:00Z\x00x\x00END"


def _object(message: bytes, *, author: bytes = b"Ada <ada@example.com> 1714557600 -0700") -> bytes:
    head = b"tree " + b"0" * 40 + b"\nauthor " + author + b"\ncommitter " + author + b"\n"
    return head + b"\n" + message


def test_object_subject_body_author_and_date() -> None:
    record = adr_commits.parse_commit_object(SHA, _object(b"Use Postgres\n\nBecause it scales.\n"))
    assert record == adr_commits.CommitRecord(
        SHA, "Use Postgres", "Ada", "2024-05-01T03:00:00-07:00", "Because it scales."
    )


def test_object_a_subject_paragraph_of_several_lines_is_joined_with_spaces() -> None:
    record = adr_commits.parse_commit_object(SHA, _object(b"Use Postgres\nfor events\n\nWhy.\n"))
    assert (record.subject, record.body) == ("Use Postgres for events", "Why.")


def test_object_crlf_line_endings_leave_no_carriage_returns() -> None:
    record = adr_commits.parse_commit_object(SHA, _object(b"Use it\r\n\r\nBecause.\r\n"))
    assert (record.subject, record.body) == ("Use it", "Because.")


def test_object_the_encoding_header_decodes_the_message_and_the_author() -> None:
    raw = (
        b"tree " + b"0" * 40 + b"\nauthor Jos\xe9 <j@example.com> 1714557600 +0000\n"
        b"encoding ISO-8859-1\n\nCaf\xe9 au lait\n\nPlus \xe9.\n"
    )
    record = adr_commits.parse_commit_object(SHA, raw)
    assert (record.subject, record.author, record.body) == ("Café au lait", "José", "Plus é.")


@pytest.mark.parametrize("name", [b"no-such-codec", b"rot13", b"\xff\xfe", b"hex"])
def test_object_an_unusable_encoding_falls_back_to_utf8(name: bytes) -> None:
    raw = b"tree " + b"0" * 40 + b"\nencoding " + name + b"\n\ncaf\xc3\xa9 policy\n"
    assert adr_commits.parse_commit_object(SHA, raw).subject == "café policy"


def test_object_invalid_utf8_is_replaced_not_raised() -> None:
    assert adr_commits.parse_commit_object(SHA, _object(b"bad \xff byte\n")).subject == "bad � byte"


def test_object_a_signature_block_does_not_hide_the_message() -> None:
    raw = (
        b"tree " + b"0" * 40 + b"\nauthor Ada <a@x> 1714557600 +0000\n"
        b"gpgsig -----BEGIN PGP SIGNATURE-----\n \n abc\n -----END PGP SIGNATURE-----\n\n"
        b"Use signed commits\n\nBecause audits.\n"
    )
    record = adr_commits.parse_commit_object(SHA, raw)
    assert (record.subject, record.body, record.author) == (
        "Use signed commits",
        "Because audits.",
        "Ada",
    )


def test_object_the_first_author_header_wins_and_a_message_line_never_does() -> None:
    forged = b"Use it\n\nauthor Mallory <m@x> 1 +0000\nencoding rot13\n"
    record = adr_commits.parse_commit_object(SHA, _object(forged))
    assert record.author == "Ada"
    assert record.body == "author Mallory <m@x> 1 +0000\nencoding rot13"


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"\n",
        b"\n\n",
        b"no headers at all",
        b"tree " + b"0" * 40,
        b"author \n\nmsg",
        b"author Ada <a@x> notatime +0000\n\nmsg",
        b"author Ada <a@x> 999999999999 +0000\n\nmsg",
        b"author Ada <a@x> -99999999999 +0000\n\nmsg",
        b"author Ada <a@x> 1714557600 +9999\n\nmsg",
        b"author \xff\xfe <\x00> 1 +0000\n\n\x00\x00",
    ],
)
def test_object_a_malformed_object_never_raises(raw: bytes) -> None:
    record = adr_commits.parse_commit_object(SHA, raw)
    assert record.sha == SHA
    assert isinstance(record.date, str)


def test_object_a_bad_timestamp_gives_an_empty_date_and_keeps_the_name() -> None:
    record = adr_commits.parse_commit_object(SHA, b"author Ada <a@x> 999999999999 +0000\n\nmsg\n")
    assert (record.author, record.date, record.subject) == ("Ada", "", "msg")


def test_object_nul_bytes_and_a_fake_record_header_stay_in_the_body() -> None:
    record = adr_commits.parse_commit_object(SHA, _object(f"Use it\n\nWhy.\n{FORGED}\n".encode()))
    assert record.subject == "Use it"
    assert FORGED in record.body
    assert record.sha == SHA


def _forge_commit(repo: Path, parent: str, message: str) -> str:
    """Write a commit object that git itself would refuse: a NUL inside the message."""
    tree = git(repo, "rev-parse", f"{parent}^{{tree}}").strip()
    identity = "Ada <ada@example.com> 1714557600 +0000"
    body = f"tree {tree}\nparent {parent}\nauthor {identity}\ncommitter {identity}\n\n{message}"
    return hash_commit(repo, body)


def test_reader_a_nul_forged_message_is_the_body_of_the_one_real_commit(tmp_path: Path) -> None:
    repo = new_repo(tmp_path / "r")
    first = commit(repo, "Initial work")
    message = f"Use Postgres for events\n\nBecause it scales.\n{FORGED}\n"
    forged = _forge_commit(repo, first, message)
    git(repo, "update-ref", "refs/heads/main", forged)
    records, truncated = adr_git.read_commits(repo, forged, 10)
    assert truncated is False
    assert [r.sha for r in records] == [forged, first]
    newest = records[0]
    assert newest.subject == "Use Postgres for events"
    assert "\x00" in newest.body and FORGED in newest.body
    assert records[1].subject == "Initial work"


def test_reader_returns_newest_first_and_flags_truncation(tmp_path: Path) -> None:
    repo = new_repo(tmp_path / "r")
    shas = [commit(repo, f"Decision number {n}") for n in range(5)]
    records, truncated = adr_git.read_commits(repo, shas[-1], 3)
    assert [r.sha for r in records] == shas[:1:-1]
    assert truncated is True
    records, truncated = adr_git.read_commits(repo, shas[-1], 5)
    assert (len(records), truncated) == (5, False)
    assert adr_git.read_commits(repo, shas[-1], 0) == ([], True)


def test_reader_since_limits_history(tmp_path: Path) -> None:
    repo = new_repo(tmp_path / "r")
    commit(repo, "Old decision", date="2020-01-01T00:00:00+00:00")
    new = commit(repo, "New decision", date="2026-06-01T00:00:00+00:00")
    records, truncated = adr_git.read_commits(repo, new, 10, "2025-01-01")
    assert ([r.subject for r in records], truncated) == (["New decision"], False)


def test_reader_batches_more_commits_than_one_cat_file_call(tmp_path: Path) -> None:
    repo = new_repo(tmp_path / "r")
    for n in range(7):
        commit(repo, f"Decision number {n}")
    head = git(repo, "rev-parse", "HEAD").strip()
    original = adr_git.BATCH_SHAS
    adr_git.BATCH_SHAS = 3
    try:
        records, _ = adr_git.read_commits(repo, head, 10)
    finally:
        adr_git.BATCH_SHAS = original
    assert [r.subject for r in records] == [f"Decision number {n}" for n in range(6, -1, -1)]


def _fake_batch(monkeypatch: pytest.MonkeyPatch, stdout: bytes, code: int = 0) -> None:
    real = adr_git.git_bytes

    def fake(
        repo: Path, *args: str, stdin: bytes | None = None
    ) -> subprocess.CompletedProcess[bytes]:
        if args[:2] == ("cat-file", "--batch"):
            return subprocess.CompletedProcess(args, code, stdout, b"boom")
        result: subprocess.CompletedProcess[bytes] = real(repo, *args, stdin=stdin)
        return result

    monkeypatch.setattr(adr_git, "git_bytes", fake)


@pytest.mark.parametrize(
    "reply",
    [
        b"",
        b"deadbeef missing\n",
        b"{sha} blob 3\nabc\n",
        b"{other} commit 3\nabc\n",
        b"{sha} commit 99\nabc\n",
        b"{sha} commit 3\nabcX",
        b"{sha} commit 3\nabc\nextra",
    ],
)
def test_reader_a_reply_that_does_not_match_the_request_is_a_git_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, reply: bytes
) -> None:
    repo = new_repo(tmp_path / "r")
    sha = commit(repo, "Initial work")
    text = reply.replace(b"{sha}", sha.encode()).replace(b"{other}", b"c" * 40)
    _fake_batch(monkeypatch, text)
    with pytest.raises(adr_git.GitError):
        adr_git.read_commits(repo, sha, 5)


def test_reader_a_failing_cat_file_is_a_git_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = new_repo(tmp_path / "r")
    sha = commit(repo, "Initial work")
    _fake_batch(monkeypatch, b"", code=128)
    with pytest.raises(adr_git.GitError, match="cat-file"):
        adr_git.read_commits(repo, sha, 5)


def test_resolve_rev_refuses_a_flag_and_an_unknown_name(tmp_path: Path) -> None:
    repo = new_repo(tmp_path / "r")
    commit(repo, "Initial work")
    with pytest.raises(adr_git.ConfigError):
        adr_git.resolve_rev(repo, "--all")
    with pytest.raises(adr_git.ConfigError):
        adr_git.resolve_rev(repo, "nope")
    assert len(adr_git.resolve_rev(repo, "HEAD")) == 40


def test_repo_root_refuses_a_plain_directory(tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    with pytest.raises(adr_git.ConfigError):
        adr_git.repo_root(plain)
    with pytest.raises(adr_git.ConfigError):
        adr_git.repo_root(tmp_path / "missing")
