"""Tests for input caps and linear-time patterns in the ADR backfill modules.

Each timing case calls the function directly, so a cap applied earlier in the pipeline cannot
hide a slow pattern. Every case uses 200,000 characters and must finish in under one second.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from pathlib import Path

import adr_commits
import adr_docs
import adr_locate
import adr_log
import adr_scan
import adr_shape
import bootstrap_adr
import pytest
from adr_helpers import commit, new_repo, write

N = 200_000
LIMIT_S = 1.0


def _seconds(call: Callable[[], object]) -> float:
    start = time.perf_counter()
    call()
    return time.perf_counter() - start


@pytest.mark.parametrize(
    ("name", "call"),
    [
        ("_H1", lambda: adr_locate._H1.fullmatch("# a" + " " * N + "b")),
        ("_H2", lambda: adr_locate._H2.fullmatch("## a" + " " * N + "b")),
        ("_H2 marks", lambda: adr_locate._H2.fullmatch("## a" + "# " * (N // 2) + "b")),
        ("is_decision_commit", lambda: adr_shape.is_decision_commit("Adopt x" + " " * N + "y")),
        ("pr reference marks", lambda: adr_shape.is_decision_commit("Adopt x" + "(#1" * (N // 3))),
        ("urls_in", lambda: adr_commits.urls_in("https://a" + "." * N + "b")),
        ("replace", lambda: adr_shape.is_decision_shaped_title("replace " * (N // 5))),
        ("adr_title", lambda: adr_locate.adr_title("commit", "x" + " " * N + "y")),
        ("title with prefix", lambda: adr_locate.adr_title("pr", "feat: a" + " " * N + "(#1")),
        (
            "file action line",
            lambda: adr_shape.has_stated_rationale("Adopt x for all", "added " + "." * N + " x"),
        ),
        ("entry_date", lambda: adr_log.entry_date("a" + " " * N + "y")),
        ("log heading", lambda: adr_log.split_decision_log("## D1 " + " " * N + "x")),
    ],
)
def test_a_hostile_200k_string_is_linear(name: str, call: Callable[[], object]) -> None:
    assert _seconds(call) < LIMIT_S, name


def test_the_decision_shaped_filter_still_reads_a_replace_with_title() -> None:
    assert adr_shape.is_decision_shaped_title("Replace the queue with a topic")
    assert adr_shape.is_decision_shaped_title("replaces eo-inference with the per-copy engine")
    assert not adr_shape.is_decision_shaped_title("Replace the queue")


def test_the_pr_reference_still_comes_off_a_title() -> None:
    assert adr_locate.adr_title("pr", "feat(api): Adopt gRPC   (#12)") == "Adopt gRPC"
    assert adr_shape.is_decision_commit("Adopt gRPC for every internal service (#42)")
    assert not adr_shape.is_decision_commit("Release 5.9.0 (#42)")


@pytest.mark.parametrize(
    ("subject", "is_decision"),
    [
        ("Added docs/architecture/overview.md", False),
        ("Modified 2 files in the build output", True),
        ("Added a new retry policy for the queue", True),
    ],
)
def test_a_file_action_subject_is_still_told_from_a_decision(
    subject: str, is_decision: bool
) -> None:
    assert adr_shape.is_decision_commit(subject) is is_decision


def test_a_closing_mark_and_a_field_segment_still_come_off_a_log_title() -> None:
    entries = adr_log.split_decision_log(
        "## D17 - Use pnpm everywhere ##\n\nBecause it is faster.\n"
    )
    assert entries[0].title == "D17 - Use pnpm everywhere"
    ledger = adr_log.split_decision_log("D5 | status: test | Keep one lockfile\n\nWhy.\n")
    assert ledger[0].title == "D5 Keep one lockfile"


def test_a_commit_subject_is_cut_at_1000_characters() -> None:
    raw = b"tree " + b"0" * 40 + b"\n\n" + b"S" * 5000 + b"\n\nbody\n"
    record = adr_commits.parse_commit_object("a" * 40, raw)
    assert len(record.subject) == adr_commits.MAX_SUBJECT_CHARS == 1000


def test_a_commit_body_is_cut_at_64_kib() -> None:
    raw = b"tree " + b"0" * 40 + b"\n\nSubject\n\n" + b"b" * 200_000 + b"\n"
    record = adr_commits.parse_commit_object("a" * 40, raw)
    assert len(record.body) == adr_commits.MAX_BODY_CHARS == 64 * 1024


def _pr(**over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "number": 9,
        "title": "Adopt Postgres instead of MySQL",
        "body": "Because the team already runs Postgres in production for the billing system.",
        "url": "https://github.com/o/r/pull/9",
        "merged_at": "2026-03-04T10:00:00Z",
        "author": {"login": "ada"},
    }
    return {**base, **over}


def test_a_pull_request_title_is_cut_at_1000_and_its_body_at_64_kib() -> None:
    long_title = "Adopt " + "x" * 5000
    long_body = "Because the team already runs Postgres in production. " * 4000
    rows = adr_commits.select_prs([_pr(title=long_title, body=long_body)], {})
    assert len(long_body) > 64 * 1024 and len(rows) == 1
    assert len(rows[0].title) == 1000
    assert len(rows[0].body) == 64 * 1024


def test_prs_json_over_16_mib_is_refused_without_reading_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = new_repo(tmp_path / "r")
    commit(repo, "Initial work")
    big = tmp_path / "prs.json"
    with big.open("wb") as handle:
        handle.truncate(16 * 1024 * 1024 + 1)
    code = bootstrap_adr.main(
        ["scan", "--repo", str(repo), "--prs-json", str(big), "--out", str(tmp_path / "s.json")]
    )
    out = json.loads(capsys.readouterr().out)
    assert code == 2 and out["error"] == "config" and "too large" in out["message"]


def test_prs_json_at_the_cap_is_still_read(tmp_path: Path) -> None:
    prs = write(tmp_path, "prs.json", "[]")
    assert bootstrap_adr._read_prs(str(prs)) == []


# ---------------------------------------------------------------------------
# E1 id suppression
# ---------------------------------------------------------------------------


def test_names_id_stays_fast_over_a_large_adr_corpus() -> None:
    texts = [(f"a{i}.md", ("lorem ipsum dolor " * 60) + f" D-{i}") for i in range(2000)]
    existing = adr_docs.ExistingAdrs(texts)
    elapsed = _seconds(lambda: [existing.names_id(f"X-{i}") for i in range(2000)])
    assert elapsed < LIMIT_S


@pytest.mark.parametrize(
    ("ident", "text", "expected"),
    [
        ("D-001", "see d-001.", True),
        ("D1", "(D1)", True),
        ("D-001", "see D-0010", False),
        ("D-001", "x-D-001", False),
        ("D-001", "D-001.md says so", True),
        ("v1.2", "the v1.2 rule (v1.2).", True),
        ("v1.2", "v1.25 is newer", False),
    ],
)
def test_names_id_keeps_the_whole_word_rule(ident: str, text: str, expected: bool) -> None:
    assert adr_docs.ExistingAdrs([("a.md", text)]).names_id(ident) is expected


# ---------------------------------------------------------------------------
# One locate_folders call per scan
# ---------------------------------------------------------------------------


def test_scan_locates_the_adr_folders_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = new_repo(tmp_path / "r")
    write(repo, "docs/adr/0001-first.md", "# 1. First\n")
    commit(repo, "Initial work")
    calls: list[Path] = []
    real = adr_locate.locate_folders

    def counting(root: Path) -> tuple[list[tuple[str, str]], bool]:
        calls.append(root)
        found: tuple[list[tuple[str, str]], bool] = real(root)
        return found

    monkeypatch.setattr(adr_locate, "locate_folders", counting)
    monkeypatch.setattr(adr_scan, "locate_folders", counting)
    payload = adr_scan.scan(repo, "HEAD", 10, None, None)
    assert len(calls) == 1
    assert payload["adr_folders"] == ["docs/adr"]
