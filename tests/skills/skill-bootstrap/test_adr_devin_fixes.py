"""Tests for the PR #7527 review findings: scan size, log twins, nested rationale, and inputs."""

from __future__ import annotations

import json
import os
import re
from hashlib import sha256
from pathlib import Path
from typing import Any

import adr_commits
import adr_locate
import adr_log
import adr_scan
import bootstrap_adr
import pytest
from adr_helpers import commit, git, new_repo, run_cli, write
from draft_helpers import _cand

WHY = "Because the team already runs it in production and a second system needs a second on-call."


def _scan(repo: Path) -> dict[str, Any]:
    payload: dict[str, Any] = adr_scan.scan(repo, "HEAD", 300, None, None)
    return payload


def test_draft_reads_a_scan_report_larger_than_the_pr_export_limit(tmp_path: Path) -> None:
    repo = new_repo(tmp_path / "r")
    filler = [_cand(id=f"c-{n:07d}", excerpt="x" * 1100) for n in range(16_000)]
    report = tmp_path / "scan.json"
    report.write_text(
        json.dumps({"repo": str(repo), "candidates": [*filler, _cand()]}), encoding="utf-8"
    )
    assert report.stat().st_size > bootstrap_adr.MAX_JSON_BYTES

    result = bootstrap_adr.draft(str(report), "c-1234567", str(tmp_path / "out"), "Proposed")

    assert Path(result["path"]).is_file()


def test_drafting_one_of_two_log_twins_keeps_the_other_a_candidate(tmp_path: Path) -> None:
    repo = new_repo(tmp_path / "r")
    write(repo, "docs/adr/0001-first.md", "# 1. First\n\n## Status\n\nAccepted\n")
    write(
        repo,
        "DECISIONS.md",
        f"## D-1 - Use pnpm everywhere\n\n{WHY}\n\n## D-1 - Pin Node to the LTS line\n\n{WHY}\n",
    )
    commit(repo, "Initial work")
    first = _scan(repo)
    keys = [c["source"]["entry_id"] for c in first["candidates"]]
    assert all(re.fullmatch(r"D-1--[0-9a-f]{8}", k) for k in keys) and len(set(keys)) == 2
    report = tmp_path / "scan.json"
    report.write_text(json.dumps(first), encoding="utf-8")
    pnpm = next(c["id"] for c in first["candidates"] if "pnpm" in c["title"])

    bootstrap_adr.draft(str(report), pnpm, str(repo / "docs" / "adr"), "Proposed")

    second = _scan(repo)
    assert [c["title"] for c in second["candidates"]] == ["D-1 - Pin Node to the LTS line"]


def test_a_unique_log_id_is_recorded_with_its_title_hash() -> None:
    entries = [
        ("DECISIONS.md", adr_log.LogEntry("D-7", "D-7 x", "D-7 x", "D-7 x\n\ntext here at length"))
    ]

    assert adr_log._entry_keys(entries) == [f"D-7--{sha256(b'D-7 x').hexdigest()[:8]}"]


def test_a_nested_rationale_heading_stays_with_its_decision() -> None:
    log = (
        "## D-10: Adopt Rust\n\n### Rationale\n\n"
        "Because the old runtime could not meet the latency target.\n\n"
        "## D-11: Keep Postgres\n\nWe keep it because the team knows it well.\n"
    )

    entries = adr_log.split_decision_log(log)

    assert [entry.id for entry in entries] == ["D-10", "D-11"]
    assert "latency target" in entries[0].text


def test_a_nested_rationale_reaches_the_candidate_reason(tmp_path: Path) -> None:
    repo = new_repo(tmp_path / "r")
    write(
        repo,
        "DECISIONS.md",
        "## D-10: Adopt Rust\n\n### Rationale\n\n"
        "We adopt Rust because the old runtime could not meet the latency target.\n",
    )
    commit(repo, "Initial work")

    (item,) = _scan(repo)["candidates"]

    assert item["reason"] is not None and "latency target" in item["reason"]


@pytest.mark.parametrize("since", ["not-a-date", "2 weeks ago", "yesterday"])
def test_a_since_that_is_not_iso_8601_exits_two(tmp_path: Path, since: str) -> None:
    repo = new_repo(tmp_path / "r")
    commit(repo, "Initial work")

    code, payload = run_cli(
        "scan", "--repo", str(repo), "--since", since, "--out", str(tmp_path / "s.json")
    )

    assert code == 2 and payload["error"] == "config"
    assert not (tmp_path / "s.json").exists()


def test_an_iso_since_is_accepted(tmp_path: Path) -> None:
    repo = new_repo(tmp_path / "r")
    commit(repo, "Initial work")

    code, _payload = run_cli(
        "scan", "--repo", str(repo), "--since", "2020-01-31", "--out", str(tmp_path / "s.json")
    )

    assert code == 0


@pytest.mark.parametrize(
    ("remote", "base"),
    [
        ("https://github.example.com:8443/o/r.git", "https://github.example.com:8443/o/r"),
        ("ssh://git@github.example.com:2222/o/r.git", "https://github.example.com/o/r"),
        ("https://github.com/o/r.git", "https://github.com/o/r"),
        ("https://github.example.com:443/o/r.git", "https://github.example.com/o/r"),
        ("http://github.example.com:8080/o/r.git", "https://github.example.com/o/r"),
    ],
)
def test_web_base_keeps_only_a_non_default_https_port(remote: str, base: str) -> None:
    found = adr_commits.web_base(remote)

    assert found is not None and found[1] == base


def test_a_breaking_pull_request_with_no_stated_reason_is_kept() -> None:
    dropped: dict[str, int] = {}
    row = {
        "number": 9,
        "title": "feat!: drop the v1 API",
        "body": "",
        "url": "https://github.com/o/r/pull/9",
        "merged_at": "2026-03-04T10:00:00Z",
        "author": {"login": "ada"},
    }

    rows = adr_commits.select_prs([row], dropped, "https://github.com/o/r")

    assert [r.number for r in rows] == [9]
    assert rows[0].reason is None


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="no symlinks")
def test_a_symlinked_docs_folder_outside_the_checkout_is_not_read(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    write(outside, "DECISIONS.md", f"## D-9 - Secret decision\n\n{WHY}\n")
    repo = new_repo(tmp_path / "r")
    try:
        (repo / "docs").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("cannot create a symlink here")

    assert adr_log.find_log_files(repo) == []


def _entry(ident: str, title: str) -> tuple[str, adr_log.LogEntry]:
    return "DECISIONS.md", adr_log.LogEntry(ident, title, title, f"{title}\n\n{WHY}")


def test_twin_keys_follow_the_title_not_the_position() -> None:
    first, second = _entry("D-1", "D-1 - Use pnpm"), _entry("D-1", "D-1 - Pin Node")

    forward = adr_log._entry_keys([first, second])
    backward = adr_log._entry_keys([second, first])

    assert forward == backward[::-1] and len(set(forward)) == 2


def test_twins_with_the_same_title_are_numbered_in_order() -> None:
    twin = _entry("D-1", "D-1 - Use pnpm")

    keys = adr_log._entry_keys([twin, twin, _entry("D-2", "D-2 - Other")])

    assert "--" in keys[0] and keys[1] == f"{keys[0]}-2"
    assert keys[2].startswith("D-2--")


def test_a_breaking_pr_with_no_reason_takes_the_reason_of_its_commit(tmp_path: Path) -> None:
    origin = "https://github.com/o/r"
    repo = new_repo(tmp_path / "r")
    write(repo, "docs/adr/0001-first.md", "# 1. First\n\n## Status\n\nAccepted\n")
    commit(repo, "Initial work")
    git(repo, "remote", "add", "origin", f"{origin}.git")
    squash = commit(repo, f"feat!: drop the v1 API (#9)\n\nWe drop it. {WHY}")
    row = {
        "number": 9,
        "title": "feat!: drop the v1 API",
        "body": "",
        "url": f"{origin}/pull/9",
        "merged_at": "2026-03-04T10:00:00Z",
        "author": {"login": "ada"},
        "merge_commit_sha": squash,
    }

    (item,) = adr_scan.scan(repo, "HEAD", 300, None, [row])["candidates"]

    assert item["id"] == "pr-9" and item["signals"] == ["breaking-change"]
    assert item["reason"] is not None and "second on-call" in item["reason"]


def test_a_scan_report_over_the_cap_exits_two_and_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = new_repo(tmp_path / "r")
    commit(repo, "Initial work")
    monkeypatch.setattr(bootstrap_adr, "MAX_SCAN_BYTES", 10)
    out = tmp_path / "s.json"

    code = bootstrap_adr.main(["scan", "--repo", str(repo), "--out", str(out)])

    assert code == 2 and not out.exists()


def test_an_iso_since_with_a_z_time_is_accepted(tmp_path: Path) -> None:
    repo = new_repo(tmp_path / "r")
    commit(repo, "Initial work")

    code, _payload = run_cli(
        "scan",
        "--repo",
        str(repo),
        "--since",
        "2020-01-31T00:00:00Z",
        "--out",
        str(tmp_path / "s.json"),
    )

    assert code == 0


def test_existing_adrs_are_read_newest_first_across_folders(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = new_repo(tmp_path / "r")
    write(repo, "docs/adr/0001-a.md", "# 1. A\n")
    write(repo, "docs/adr/0002-b.md", "# 2. B\n")
    write(repo, "docs/decisions/0003-c.md", "# 3. C\n")
    monkeypatch.setattr(adr_locate, "MAX_ADR_FILES", 1)
    folders = [("docs/adr", "test"), ("docs/decisions", "test")]

    read = [rel for rel, _text in adr_locate.read_adr_texts(repo, folders)]

    assert read == ["docs/decisions/0003-c.md"]


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="no symlinks")
def test_a_symlinked_docs_folder_inside_the_checkout_is_read(tmp_path: Path) -> None:
    repo = new_repo(tmp_path / "r")
    write(repo, "notes/DECISIONS.md", f"## D-9 - Kept decision\n\n{WHY}\n")
    try:
        (repo / "docs").symlink_to(repo / "notes", target_is_directory=True)
    except OSError:
        pytest.skip("cannot create a symlink here")

    assert adr_log.find_log_files(repo) == ["docs/DECISIONS.md"]
