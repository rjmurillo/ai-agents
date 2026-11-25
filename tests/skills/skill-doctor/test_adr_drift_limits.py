"""adr_drift.py limits: wide number gaps, refused folders, the size cap, and comment parsing."""

from __future__ import annotations

import time

import adr_checks
import adr_drift
import adr_text
import pytest
from adr_drift_helpers import kinds, run_cli, scan, seeded_repo, symlink_or_skip


def test_a_wide_number_gap_is_counted_without_listing_every_number(tmp_path, capsys):
    repo = seeded_repo(
        tmp_path / "repo",
        {"docs/adr/0001-a.md": "# 1. A\n", "docs/adr/999999-b.md": "# 999999. B\n"},
    )

    started = time.monotonic()
    result = scan(capsys, repo)
    elapsed = time.monotonic() - started

    (gap,) = kinds(result, "adr-number-gap")
    assert gap["evidence"]["missing_count"] == 999_997
    assert gap["evidence"]["missing"] == list(range(2, 52))
    assert gap["evidence"]["truncated"] is True
    assert elapsed < 10


def test_a_name_with_more_than_six_digits_is_unparseable_not_numbered(tmp_path, capsys):
    repo = seeded_repo(
        tmp_path / "repo",
        {"docs/adr/0001-a.md": "# 1. A\n", "docs/adr/1700000000-notes.md": "# Notes\n"},
    )

    result = scan(capsys, repo)

    assert [f["evidence"]["path"] for f in kinds(result, "adr-unparseable-name")] == [
        "docs/adr/1700000000-notes.md"
    ]
    assert kinds(result, "adr-number-gap") == []


def test_the_bootstrap_only_folder_docs_adrs_is_found(tmp_path, capsys):
    repo = seeded_repo(tmp_path / "repo", {"docs/adrs/0001-use-uv.md": "# 1. Use uv\n"})

    result = scan(capsys, repo)

    assert kinds(result, "no-adr-directory") == []
    assert [d["path"] for d in result["locate"]["adr_dirs"]] == ["docs/adrs"]


def test_a_refused_folder_suppresses_the_create_a_folder_fix(tmp_path, capsys):
    outside = tmp_path / "shared-adrs"
    outside.mkdir()
    (outside / "0001-a.md").write_text("# 1. A\n", encoding="utf-8")
    repo = seeded_repo(tmp_path / "repo", {"README.md": "x\n"})
    (repo / "docs").mkdir()
    symlink_or_skip(repo / "docs" / "adr", outside)

    out = tmp_path / "out" / "scan.json"
    code, stdout, err = run_cli(capsys, "scan", "--repo", str(repo), "--out", str(out))

    assert code == 0, err
    assert "rejected: 1" in stdout
    result = scan(capsys, repo, name="again.json")
    assert kinds(result, "no-adr-directory") == []
    assert result["locate"]["rejected"] == [
        {"path": "docs/adr", "reason": "resolves outside the repository"}
    ]


def test_a_repo_with_no_folder_and_nothing_refused_still_gets_the_create_fix(tmp_path, capsys):
    repo = seeded_repo(tmp_path / "repo", {"README.md": "x\n"})

    result = scan(capsys, repo)

    assert len(kinds(result, "no-adr-directory")) == 1


def test_a_result_over_the_size_cap_exits_2_and_writes_nothing(tmp_path, capsys, monkeypatch):
    repo = seeded_repo(tmp_path / "repo")
    monkeypatch.setattr(adr_drift, "SCAN_MAX_BYTES", 10)
    out = tmp_path / "out" / "scan.json"

    code, _, err = run_cli(capsys, "scan", "--repo", str(repo), "--out", str(out))

    assert code == 2
    assert "over the 10-byte limit" in err and "--since" in err
    assert not out.exists()


def test_the_writer_and_the_reader_share_one_size_limit():
    import adr_corpus
    import report_adr

    assert adr_drift.SCAN_MAX_BYTES == report_adr.MAX_FILE_BYTES == adr_corpus.SCAN_MAX_BYTES


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("accepted # note", "accepted"),
        ("accepted\t# note", "accepted"),
        ("'quoted' # note", "quoted"),
        ("a#b", "a#b"),
        ("#leading", "#leading"),
        ("plain", "plain"),
        ("", ""),
    ],
)
def test_strip_comment_drops_a_comment_after_whitespace_only(raw, expected):
    assert adr_text._strip_comment(raw) == expected


def test_strip_comment_is_linear_on_a_long_blank_run():
    value = "x" + " " * 200_000 + "y"

    started = time.monotonic()
    adr_text._strip_comment(value)

    assert time.monotonic() - started < 2


def test_an_adr_dir_naming_a_missing_folder_still_gets_the_create_fix(tmp_path, capsys):
    repo = seeded_repo(tmp_path / "repo", {".adr-dir": "doc/adr\n"})

    result = scan(capsys, repo)

    assert len(kinds(result, "no-adr-directory")) == 1
    assert [r["path"] for r in result["locate"]["rejected"]] == [".adr-dir"]


@pytest.mark.parametrize(
    "line",
    [
        "[" * 200_000,
        "a" * 200_000,
        "[x](a" * 40_000,
        '[x](a "' * 30_000,
    ],
    ids=["brackets", "path-run", "open-links", "open-titles"],
)
def test_link_and_path_parsing_is_linear_on_a_hostile_line(line):
    started = time.monotonic()
    adr_checks._refs(line, include_paths=True)
    adr_checks._targets(line)

    assert time.monotonic() - started < 2


@pytest.mark.parametrize(
    ("text", "paths"),
    [
        ("see docs/adr/0003-z.md, 0004.md", ["docs/adr/0003-z.md", "0004.md"]),
        ("a.md.x b/c.md", ["a.md", "b/c.md"]),
        ("..md .md", ["..md"]),
        ("x.mdx", ["x.md"]),
        ("no paths here", []),
    ],
)
def test_md_paths_match_the_pattern_they_replace(text, paths):
    import re

    assert adr_checks._md_paths(text) == paths == re.findall(r"[\w./-]+\.md", text)


@pytest.mark.parametrize(
    ("line", "targets"),
    [
        ('see [ADR 1](ADR-001-x.md) and [two](./0002-y.md "t")', ["ADR-001-x.md", "./0002-y.md"]),
        ("[a [b](x.md)", ["x.md"]),
        ("[x](<a.md>)", ["a.md"]),
        ("[x]( a.md )", ["a.md"]),
        ("`[x](a.md)` in code", []),
    ],
)
def test_inline_links_keep_their_targets(line, targets):
    assert adr_checks._targets(line) == targets
