"""adr_drift.py filesystem edges: symlinks, unreadable paths, rejections, atomic output."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import adr_drift
import pytest
from adr_drift_helpers import (
    ADR_DIR,
    adr_path,
    adr_text,
    commit,
    run_cli,
    scan,
    seeded_repo,
    symlink_or_skip,
)

CANNOT_CHMOD = sys.platform == "win32" or (hasattr(os, "geteuid") and os.geteuid() == 0)
needs_chmod = pytest.mark.skipif(CANNOT_CHMOD, reason="chmod 000 is not enforced here")


def _locate(capsys, repo: Path) -> dict[str, Any]:
    code, out, err = run_cli(capsys, "locate", "--repo", str(repo))
    assert code == 0, err
    result: dict[str, Any] = json.loads(out)
    return result


def test_a_symlinked_adr_file_that_leaves_the_folder_is_rejected_not_read(tmp_path, capsys):
    repo = seeded_repo(tmp_path / "repo")
    outside = tmp_path / "outside" / "ADR-050-escape.md"
    outside.parent.mkdir()
    outside.write_text(adr_text(50), encoding="utf-8")
    symlink_or_skip(repo / ADR_DIR / "ADR-050-escape.md", outside)

    result = scan(capsys, repo)

    entry = result["locate"]["adr_dirs"][0]
    assert entry["count"] == 1
    rejected = result["locate"]["rejected"]
    assert [r["path"] for r in rejected] == [f"{ADR_DIR}/ADR-050-escape.md"]
    assert "outside the folder" in rejected[0]["reason"]


def test_a_symlinked_adr_file_that_stays_inside_the_folder_is_kept(tmp_path, capsys):
    repo = seeded_repo(tmp_path / "repo")
    symlink_or_skip(
        repo / ADR_DIR / "ADR-002-alias.md", repo / ADR_DIR / adr_path(1).split("/")[-1]
    )

    result = scan(capsys, repo)

    assert result["locate"]["adr_dirs"][0]["count"] == 2
    assert result["locate"]["rejected"] == []


def test_a_known_folder_name_that_aliases_another_is_read_once_under_its_real_path(
    tmp_path, capsys
):
    """`docs/adr -> decisions`: one folder, one copy of each finding, no false history hit."""
    record = "docs/decisions/ADR-001-x.md"
    repo = seeded_repo(
        tmp_path / "repo", {record: adr_text(1, body="See [gone](ADR-009-missing.md).")}
    )
    symlink_or_skip(repo / "docs/adr", Path("decisions"))
    commit(repo, {record: adr_text(1, body="See [gone](ADR-009-missing.md). Edited.")}, "x")
    commit(repo, {"src/new.py": "x = 1\n"}, "refactor: supersede ADR-001 with a queue")

    result = scan(capsys, repo)

    assert [d["path"] for d in result["locate"]["adr_dirs"]] == ["docs/decisions"]
    assert result["locate"]["primary"] == "docs/decisions"
    broken = [f["evidence"]["path"] for f in result["findings"] if f["kind"] == "adr-broken-link"]
    assert broken == [record]
    assert all("docs/adr/" not in json.dumps(f) for f in result["findings"])


def test_a_clean_repository_has_no_read_errors_and_no_rejections(tmp_path, capsys):
    repo = seeded_repo(tmp_path / "repo")

    result = scan(capsys, repo)

    assert result["read_errors"] == [] and result["locate"]["rejected"] == []


@needs_chmod
def test_an_unreadable_adr_file_is_a_read_error_and_the_scan_continues(tmp_path, capsys):
    repo = seeded_repo(tmp_path / "repo", {adr_path(1): adr_text(1), adr_path(2): adr_text(2)})
    locked = repo / adr_path(2)
    locked.chmod(0)
    try:
        result = scan(capsys, repo)
    finally:
        locked.chmod(0o644)

    assert [e["path"] for e in result["read_errors"]] == [adr_path(2)]
    assert result["read_errors"][0]["error"]


@needs_chmod
def test_an_unlistable_folder_is_a_read_error_and_not_a_missing_directory(tmp_path, capsys):
    repo = seeded_repo(tmp_path / "repo")
    folder = repo / ADR_DIR
    folder.chmod(0)
    try:
        result = scan(capsys, repo)
    finally:
        folder.chmod(0o755)

    assert [e["path"] for e in result["read_errors"]] == [ADR_DIR]
    assert not [f for f in result["findings"] if f["kind"] == "no-adr-directory"]


def test_marker_pointing_outside_the_repo_is_rejected_with_a_reason(tmp_path, capsys):
    repo = seeded_repo(tmp_path / "repo")
    (tmp_path / "elsewhere").mkdir()
    (repo / ".adr-dir").write_text("../elsewhere\n", encoding="utf-8")

    rejected = _locate(capsys, repo)["rejected"]

    assert [r["path"] for r in rejected] == [".adr-dir"]
    assert "outside the repository" in rejected[0]["reason"]


def test_marker_pointing_at_a_missing_folder_is_rejected_and_known_folders_still_count(
    tmp_path, capsys
):
    repo = seeded_repo(tmp_path / "repo")
    (repo / ".adr-dir").write_text("docs/nowhere\n", encoding="utf-8")

    result = _locate(capsys, repo)

    assert "missing" in result["rejected"][0]["reason"]
    assert result["primary"] == ADR_DIR


def test_known_folder_symlinked_outside_or_dangling_is_rejected(tmp_path, capsys):
    repo = seeded_repo(tmp_path / "repo")
    outside = tmp_path / "outside"
    outside.mkdir()
    (repo / "docs").mkdir()
    symlink_or_skip(repo / "docs" / "adr", outside)
    symlink_or_skip(repo / "docs" / "decisions", tmp_path / "gone")

    rejected = {r["path"]: r["reason"] for r in _locate(capsys, repo)["rejected"]}

    assert "outside the repository" in rejected["docs/adr"]
    assert "missing" in rejected["docs/decisions"]


def test_a_missing_marker_and_missing_known_folders_are_not_rejections(tmp_path, capsys):
    repo = seeded_repo(tmp_path / "repo")

    assert _locate(capsys, repo)["rejected"] == []


def test_the_summary_line_reports_truncation_and_the_read_error_count(tmp_path, capsys):
    repo = seeded_repo(tmp_path / "repo")
    commit(repo, {"a.txt": "a"}, "feat: add a")
    out = tmp_path / "o.json"

    code, stdout, _ = run_cli(
        capsys, "scan", "--repo", str(repo), "--out", str(out), "--max-commits", "1"
    )

    assert code == 0
    assert "truncated: true" in stdout and "read_errors: 0" in stdout
    assert "1 commit(s) examined" in stdout


def test_a_failed_replace_leaves_no_output_and_no_temp_file(tmp_path, capsys, monkeypatch):
    repo = seeded_repo(tmp_path / "repo")
    out = tmp_path / "out" / "scan.json"

    def refuse(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr(adr_drift.os, "replace", refuse)

    code, _, err = run_cli(capsys, "scan", "--repo", str(repo), "--out", str(out))

    assert code == 2 and "cannot write" in err
    assert not out.exists() and list(out.parent.iterdir()) == []


def test_a_successful_scan_replaces_an_existing_file_whole_and_leaves_no_temp(tmp_path, capsys):
    repo = seeded_repo(tmp_path / "repo")
    out = tmp_path / "out" / "scan.json"
    out.parent.mkdir()
    out.write_text("stale", encoding="utf-8")

    scan(capsys, repo)

    assert json.loads(out.read_text(encoding="utf-8"))["schema_version"] == 1
    assert [p.name for p in out.parent.iterdir()] == ["scan.json"]


@pytest.mark.parametrize("name", ["2024-01-15-use-uv.md", "20200925-use-uv.md"])
def test_date_prefixed_notes_are_not_numbered_and_not_unparseable(tmp_path, capsys, name):
    repo = seeded_repo(tmp_path / "repo")
    commit(repo, {f"{ADR_DIR}/{name}": "# note\n"}, "docs: dated note")

    result = scan(capsys, repo)

    assert result["locate"]["adr_dirs"][0]["count"] == 1
    assert not [
        f
        for f in result["findings"]
        if f["kind"] in {"adr-unparseable-name", "adr-duplicate-number"}
    ]


@pytest.mark.parametrize(
    "name", ["adr-log.md", "ADR-INDEX.md", "README.md", "index.md", "template.md"]
)
def test_index_log_readme_and_template_names_are_not_unparseable(tmp_path, capsys, name):
    repo = seeded_repo(tmp_path / "repo")
    commit(repo, {f"{ADR_DIR}/{name}": "# list\n"}, "docs: index")

    assert not [f for f in scan(capsys, repo)["findings"] if f["kind"] == "adr-unparseable-name"]


def test_a_record_like_name_with_no_number_is_still_unparseable(tmp_path, capsys):
    repo = seeded_repo(tmp_path / "repo")
    commit(repo, {f"{ADR_DIR}/adr-draft-x.md": "# x\n"}, "docs: draft")

    assert [f for f in scan(capsys, repo)["findings"] if f["kind"] == "adr-unparseable-name"]


def _refuse_is_file(monkeypatch, name: str) -> None:
    """Make `Path.is_file` raise for one name, as Python before 3.14 does on EACCES."""
    real = Path.is_file

    def is_file(self: Path, **kwargs: Any) -> bool:
        if self.name == name:
            raise PermissionError(13, "Permission denied", str(self))
        return real(self, **kwargs)

    monkeypatch.setattr(Path, "is_file", is_file)


def test_an_entry_that_cannot_be_statted_is_a_read_error_and_the_scan_continues(
    tmp_path, capsys, monkeypatch
):
    repo = seeded_repo(tmp_path / "repo")
    (repo / ADR_DIR / "ADR-002-locked.md").write_text(adr_text(2), encoding="utf-8")
    _refuse_is_file(monkeypatch, "ADR-002-locked.md")

    result = scan(capsys, repo)

    assert result["locate"]["adr_dirs"][0]["count"] == 1
    errors = result["read_errors"]
    assert [e["path"] for e in errors] == [f"{ADR_DIR}/ADR-002-locked.md"]
    assert "Permission denied" in errors[0]["error"]


def test_an_unread_format_entry_that_cannot_be_statted_is_a_read_error(
    tmp_path, capsys, monkeypatch
):
    repo = seeded_repo(tmp_path / "repo")
    (repo / ADR_DIR / "ADR-002-locked.mdx").write_text(adr_text(2), encoding="utf-8")
    _refuse_is_file(monkeypatch, "ADR-002-locked.mdx")

    result = scan(capsys, repo)

    assert [e["path"] for e in result["read_errors"]] == [f"{ADR_DIR}/ADR-002-locked.mdx"]
    assert result["locate"]["rejected"] == []


def test_a_marker_that_cannot_be_statted_is_a_read_error_and_known_folders_still_count(
    tmp_path, capsys, monkeypatch
):
    repo = seeded_repo(tmp_path / "repo")
    (repo / ".adr-dir").write_text("docs/adr\n", encoding="utf-8")
    _refuse_is_file(monkeypatch, ".adr-dir")

    located = _locate(capsys, repo)

    assert [e["path"] for e in located["read_errors"]] == [".adr-dir"]
    assert located["rejected"] == []
    assert [d["path"] for d in located["adr_dirs"]] == [ADR_DIR]
