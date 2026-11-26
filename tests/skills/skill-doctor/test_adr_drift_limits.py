"""adr_drift.py limits: wide number gaps, refused folders, the size cap, and comment parsing."""

from __future__ import annotations

import re
import time
from types import SimpleNamespace

import adr_checks
import adr_corpus
import adr_drift
import adr_history
import adr_text
import pytest
from adr_drift_helpers import kinds, run_cli, scan, seeded_repo, symlink_or_skip

# About 40x the slowest measured case (0.26 s), so a loaded CI runner does not fail a
# linear pattern, while a quadratic one on 200,000 characters still takes minutes.
LINEAR_SECONDS = 10


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
    import report_adr

    assert adr_drift.SCAN_MAX_BYTES == report_adr.MAX_FILE_BYTES == adr_text.SCAN_MAX_BYTES


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

    assert time.monotonic() - started < LINEAR_SECONDS


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

    assert time.monotonic() - started < LINEAR_SECONDS


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


def test_an_adr_dir_naming_an_outside_folder_suppresses_the_create_fix(tmp_path, capsys):
    (tmp_path / "elsewhere").mkdir()
    (tmp_path / "elsewhere" / "0001-a.md").write_text("# 1. A\n", encoding="utf-8")
    repo = seeded_repo(tmp_path / "repo", {".adr-dir": "../elsewhere\n"})

    result = scan(capsys, repo)

    assert kinds(result, "no-adr-directory") == []
    assert [r["path"] for r in result["locate"]["rejected"]] == [".adr-dir"]


def test_a_folder_whose_adrs_all_resolve_outside_it_suppresses_the_create_fix(tmp_path, capsys):
    outside = tmp_path / "shared" / "0001-x.md"
    outside.parent.mkdir()
    outside.write_text("# 1. X\n", encoding="utf-8")
    repo = seeded_repo(tmp_path / "repo", {"README.md": "x\n"})
    (repo / "docs" / "adr").mkdir(parents=True)
    symlink_or_skip(repo / "docs" / "adr" / "0001-x.md", outside)

    result = scan(capsys, repo)

    assert kinds(result, "no-adr-directory") == []
    assert result["locate"]["rejected"] == [
        {"path": "docs/adr/0001-x.md", "reason": "resolves outside the folder"}
    ]


@pytest.mark.parametrize(
    ("pattern", "line"),
    [
        (adr_checks.ADR_REF, "ADR-" + "0" * 200_000 + "x"),
        (adr_checks.SUPERSEDED_BY_TEXT, "supersed" * 25_000),
        (adr_history.VERB_THEN_ADR, "drop" * 12_500),
        (adr_history.ADR_THEN_VERB, "ADR-" + "0" * 200_000 + "x"),
    ],
    ids=["adr-ref", "superseded-by", "verb-then-adr", "adr-then-verb"],
)
def test_adr_reference_patterns_are_linear_on_a_hostile_line(pattern, line):
    started = time.monotonic()
    pattern.findall(line)

    assert time.monotonic() - started < LINEAR_SECONDS


def test_a_status_row_above_a_long_blank_line_is_linear():
    # 50,000 blanks: the old two-run separator pattern took about 28 s here.
    lines = ["| Status | Accepted |", " " * 50_000 + "x"]

    started = time.monotonic()
    status = adr_text.doc_status({}, lines, 0)

    assert time.monotonic() - started < LINEAR_SECONDS
    assert status == "accepted"


def test_h1_and_h2_parsing_is_linear_on_a_hostile_line():
    doc = SimpleNamespace(lines=["## a" + " " * 20_000 + "b"], body_start=0)

    started = time.monotonic()
    adr_text.h1_number("# ADR-" + "0" * 200_000 + "x")
    headings = list(adr_corpus._h2_headings(doc))

    assert time.monotonic() - started < LINEAR_SECONDS
    assert headings == ["a" + " " * 20_000 + "b"]


@pytest.mark.parametrize(
    ("line", "heading"),
    [
        ("## Status", "Status"),
        ("## Status ##  ", "Status"),
        ("## C# notes", "C# notes"),
        ("##   ", None),
        ("### Deeper", None),
    ],
)
def test_h2_headings_drop_closing_marks_and_blanks(line, heading):
    doc = SimpleNamespace(lines=[line], body_start=0)

    assert list(adr_corpus._h2_headings(doc)) == ([heading] if heading else [])


@pytest.mark.parametrize(
    ("text", "numbers"),
    [
        ("see ADR-007 and ADR-12", [7, 12]),
        ("ADR-000000012", [12]),
        ("ADR-1234567 has seven digits", []),
        ("xADR-1", []),
    ],
)
def test_adr_references_read_one_to_six_digits(text, numbers):
    assert adr_checks._refs(text, include_paths=False) == numbers


def test_a_link_title_with_brackets_keeps_its_target():
    assert adr_checks._targets('[x](a.md "see [1]")') == ["a.md"]


def test_a_huge_bare_number_in_frontmatter_is_ignored_not_fatal(tmp_path, capsys):
    huge = "9" * 5_000
    text = f"---\nstatus: accepted\nsuperseded-by: {huge}\n---\n\n# 1. A\n"
    repo = seeded_repo(tmp_path / "repo", {"docs/adr/0001-a.md": text})
    out = tmp_path / "out" / "scan.json"

    code, _, err = run_cli(capsys, "scan", "--repo", str(repo), "--out", str(out))

    assert code == 0, err
    assert out.is_file()


@pytest.mark.parametrize(
    ("value", "numbers"),
    [("12", [12]), ("000012", [12]), ("1234567", []), ("9" * 5_000, [])],
)
def test_frontmatter_bare_numbers_read_one_to_six_digits(value, numbers):
    assert adr_checks._frontmatter_numbers(value) == numbers
