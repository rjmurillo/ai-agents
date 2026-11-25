"""adr_drift.py scan: rename targets for duplicate numbers, numbers shared by two folders."""

from __future__ import annotations

import errno
from pathlib import Path

import adr_history
from adr_drift_helpers import adr_path, adr_text, commit, kinds, scan, seeded_repo


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
