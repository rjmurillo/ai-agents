"""adr_drift.py scan: rename targets for duplicate numbers, numbers shared by two folders."""

from __future__ import annotations

import errno
import os
from pathlib import Path

import adr_history
import pytest
from adr_drift_helpers import (
    adr_path,
    adr_text,
    commit,
    kinds,
    scan,
    seeded_repo,
    symlink_or_skip,
)


def _adr(number: int, *, supersedes: str = "[]", superseded_by: str = "null") -> str:
    return (
        adr_text(number)
        .replace("supersedes: []", f"supersedes: {supersedes}")
        .replace("superseded-by: null", f"superseded-by: {superseded_by}")
    )


def test_each_duplicate_rename_gets_its_own_free_number(tmp_path, capsys):
    adrs = {adr_path(n, slug): adr_text(n) for n in (1, 2) for slug in ("a", "b")}
    repo = seeded_repo(tmp_path / "repo", adrs)

    found = kinds(scan(capsys, repo), "adr-duplicate-number")

    targets = [r["number"] for f in found for r in f["evidence"]["renames"]]
    assert targets == ["003", "004"]
    assert "003" in found[0]["suggested_fix"] and "004" in found[1]["suggested_fix"]


def test_every_later_file_in_a_three_way_duplicate_gets_a_rename(tmp_path, capsys):
    adrs = {adr_path(1, slug): adr_text(1) for slug in ("a", "b", "c")}
    repo = seeded_repo(tmp_path / "repo", adrs)

    (found,) = kinds(scan(capsys, repo), "adr-duplicate-number")

    renamed = [r["path"].rsplit("/", 1)[-1] for r in found["evidence"]["renames"]]
    assert renamed == ["ADR-001-b.md", "ADR-001-c.md"]
    assert [r["number"] for r in found["evidence"]["renames"]] == ["002", "003"]
    assert "Keep" in found["suggested_fix"] and "ADR-001-a.md" in found["suggested_fix"]


def test_supersession_resolves_in_the_citing_folder(tmp_path, capsys):
    repo = seeded_repo(
        tmp_path / "repo",
        {
            "docs/adr/0001-a.md": _adr(1),
            "docs/adr/0002-b.md": _adr(2),
            "docs/rfcs/0001-a.md": _adr(1, superseded_by="ADR-002"),
            "docs/rfcs/0002-b.md": _adr(2, supersedes="[ADR-001]"),
        },
    )

    result = scan(capsys, repo)

    assert kinds(result, "adr-supersession-not-reciprocal") == []
    assert kinds(result, "adr-supersedes-missing-target") == []


def test_a_one_sided_edge_is_reported_on_the_record_in_its_own_folder(tmp_path, capsys):
    repo = seeded_repo(
        tmp_path / "repo",
        {
            "docs/adr/0001-a.md": _adr(1, superseded_by="ADR-002"),
            "docs/adr/0002-b.md": _adr(2, supersedes="[ADR-001]"),
            "docs/rfcs/0001-a.md": _adr(1),
            "docs/rfcs/0002-b.md": _adr(2, supersedes="[ADR-001]"),
        },
    )

    found = kinds(scan(capsys, repo), "adr-supersession-not-reciprocal")

    assert [f["evidence"]["path"] for f in found] == ["docs/rfcs/0001-a.md"]


def test_a_back_edge_must_resolve_to_the_citing_record(tmp_path, capsys):
    repo = seeded_repo(
        tmp_path / "repo",
        {
            "docs/adr/0003-x.md": _adr(3, supersedes="[ADR-007]"),
            "docs/rfcs/0003-y.md": _adr(3),
            "docs/rfcs/0007-z.md": _adr(7, superseded_by="ADR-003"),
        },
    )

    found = kinds(scan(capsys, repo), "adr-supersession-not-reciprocal")

    # From docs/rfcs, ADR-003 is 0003-y, so no edge in 0007-z can name docs/adr/0003-x:
    # that edge is not checked. 0007-z's own edge to 0003-y has no back-edge.
    assert [f["evidence"]["path"] for f in found] == ["docs/rfcs/0003-y.md"]
    assert "supersedes: ADR-7" in found[0]["suggested_fix"]


def test_an_edge_no_number_can_answer_is_not_reported(tmp_path, capsys):
    repo = seeded_repo(
        tmp_path / "repo",
        {
            "docs/adr/0003-x.md": _adr(3, supersedes="[ADR-007]"),
            "docs/rfcs/0003-y.md": _adr(3),
            "docs/rfcs/0007-z.md": _adr(7),
        },
    )

    # From docs/rfcs, ADR-3 is 0003-y, so no fix in 0007-z could name docs/adr/0003-x.
    assert kinds(scan(capsys, repo), "adr-supersession-not-reciprocal") == []


def test_applying_the_reciprocity_fix_clears_the_finding(tmp_path, capsys):
    files = {
        "docs/rfcs/0003-y.md": _adr(3),
        "docs/rfcs/0007-z.md": _adr(7, superseded_by="ADR-003"),
    }
    repo = seeded_repo(tmp_path / "repo", files)
    (before,) = kinds(scan(capsys, repo, name="before.json"), "adr-supersession-not-reciprocal")
    assert "supersedes: ADR-7" in before["suggested_fix"]

    commit(repo, {"docs/rfcs/0003-y.md": _adr(3, supersedes="[ADR-7]")}, "docs: apply the fix")

    assert kinds(scan(capsys, repo, name="after.json"), "adr-supersession-not-reciprocal") == []


def test_a_number_two_other_folders_hold_is_not_called_missing(tmp_path, capsys):
    repo = seeded_repo(
        tmp_path / "repo",
        {
            "docs/adr/0007-a.md": _adr(7),
            "docs/rfcs/0007-a.md": _adr(7),
            "adr/0003-c.md": _adr(3, supersedes="[ADR-007]"),
        },
    )

    assert kinds(scan(capsys, repo), "adr-supersedes-missing-target") == []


def test_history_names_every_folder_that_holds_the_number(tmp_path, capsys):
    repo = seeded_repo(
        tmp_path / "repo", {"docs/adr/0004-a.md": _adr(4), "docs/rfcs/0004-a.md": _adr(4)}
    )
    commit(repo, {"x.txt": "1"}, "refactor: replace ADR-004 with a queue")

    found = kinds(scan(capsys, repo), "adr-superseded-by-commit")

    assert sorted(f["evidence"]["adr"] for f in found) == [
        "docs/adr/0004-a.md",
        "docs/rfcs/0004-a.md",
    ]
    assert {f["severity"] for f in found} == {"low"}


def test_superseded_by_names_the_successor_not_a_candidate():
    assert adr_history.superseded_numbers("status: superseded-by: ADR-111") == set()
    assert adr_history.superseded_numbers("Superseded by ADR-9.") == set()
    assert adr_history.superseded_numbers("this supersedes ADR-9") == {9}
    assert adr_history.superseded_numbers("ADR-9 is deprecated") == {9}
    assert adr_history.superseded_numbers("ADR-40 supersedes ADR-12") == {12}
    assert adr_history.superseded_numbers("follow ADR-40, which replaces ADR-12") == {12}


@pytest.mark.parametrize(
    "text",
    [
        "ADR-40 superseded ADR-12",
        "ADR-40 replaced ADR-12",
        "ADR-40 replacing ADR-12",
        "ADR-40 and ADR-41 supersede ADR-12",
        "ADR-40: supersede ADR-12",
    ],
)
def test_any_active_form_names_the_successor_first(text):
    assert adr_history.superseded_numbers(text) == {12}


@pytest.mark.parametrize(
    "text",
    [
        "ADR-12 is superseded by ADR-40",
        "ADR-12 was replaced by ADR-40",
        "ADR-12 is deprecated in favor of ADR-40",
        "ADR-012 is now superseded by ADR-040.",
        "ADR-12 is superseded by the new ADR-40",
        "ADR-12 was deprecated in favor of the proposed ADR-40",
    ],
)
def test_the_passive_form_names_the_superseded_record(text):
    assert adr_history.superseded_numbers(text) == {12}


def _too_long(real, long: str):
    def probe(self: Path, **kwargs: object) -> bool:
        if long in str(self):
            raise OSError(errno.ENAMETOOLONG, "File name too long")
        return bool(real(self))

    return probe


def test_a_link_name_too_long_for_the_os_is_a_broken_link(tmp_path, capsys, monkeypatch):
    long = "a" * 300
    body = f"See [next](ADR-002-{long}.md)."
    repo = seeded_repo(tmp_path / "repo", {adr_path(1): adr_text(1, body=body)})
    monkeypatch.setattr(Path, "exists", _too_long(Path.exists, long))

    (found,) = kinds(scan(capsys, repo), "adr-broken-link")

    assert long in found["evidence"]["target"]


@pytest.mark.parametrize(
    "raw", [b"docs\x00adr\n", "docs/adr\r\n".encode("utf-16")], ids=["nul", "utf-16"]
)
def test_an_adr_dir_with_a_nul_byte_is_rejected_not_fatal(tmp_path, capsys, raw):
    repo = seeded_repo(tmp_path / "repo", {"docs/adr/0001-a.md": "# 1. A\n"})
    (repo / ".adr-dir").write_bytes(raw)

    result = scan(capsys, repo)

    assert [r["path"] for r in result["locate"]["rejected"]] == [".adr-dir"]


def _device_link(path: Path) -> None:
    device = Path("/dev/zero")
    if not device.exists():
        pytest.skip("no /dev/zero on this platform")
    symlink_or_skip(path, device)


def _fifo(path: Path) -> None:
    if not hasattr(os, "mkfifo"):
        pytest.skip("no FIFOs on this platform")
    os.mkfifo(path)


@pytest.mark.parametrize(
    ("make", "reason"),
    [
        (lambda repo: _device_link(repo / ".adr-dir"), "resolves outside the repository"),
        (lambda repo: _fifo(repo / ".adr-dir"), "is not a regular file"),
        (
            lambda repo: (repo / ".adr-dir").write_text("x" * 5000, encoding="utf-8"),
            "larger than 4096 bytes",
        ),
    ],
    ids=["device-symlink", "fifo", "oversize"],
)
def test_an_adr_dir_that_is_not_a_small_repo_file_is_refused_unread(tmp_path, capsys, make, reason):
    repo = seeded_repo(tmp_path / "repo", {"docs/adr/0001-a.md": "# 1. A\n"})
    try:
        make(repo)
    except OSError as exc:
        pytest.skip(f"special files unavailable: {exc}")

    result = scan(capsys, repo)

    assert {"path": ".adr-dir", "reason": reason} in result["locate"]["rejected"]


def test_an_adr_dir_name_too_long_for_the_os_is_rejected(tmp_path, capsys, monkeypatch):
    long = "d" * 300
    repo = seeded_repo(tmp_path / "repo", {".adr-dir": f"{long}\n"})
    monkeypatch.setattr(Path, "is_dir", _too_long(Path.is_dir, long))

    result = scan(capsys, repo)

    assert [r["path"] for r in result["locate"]["rejected"]] == [".adr-dir"]


def test_a_name_too_long_for_the_os_is_read_as_missing(tmp_path, capsys, monkeypatch):
    long = "a" * 300
    body = f"The code lives in `src/{long}/x.md`."
    repo = seeded_repo(tmp_path / "repo", {adr_path(1): adr_text(1, body=body), "src/k.py": "x"})
    real = Path.exists

    def exists(self: Path, **kwargs: object) -> bool:
        if long in str(self):
            raise OSError(errno.ENAMETOOLONG, "File name too long")
        return bool(real(self))

    monkeypatch.setattr(Path, "exists", exists)

    (found,) = kinds(scan(capsys, repo), "adr-cited-path-missing")

    assert found["evidence"]["cited"] == f"src/{long}/x.md"
