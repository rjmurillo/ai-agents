"""Tests for CodeRabbit pass 5 on PR #7527, group C2: the CLI, the reference, and the scan."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import adr_locate
import adr_scan
import adr_write
import bootstrap_adr
import pytest
from adr_helpers import commit, git, new_repo, write
from draft_helpers import _cand, _scan_file, _text

WHY = "Because the team already runs it in production and needs one fewer system."


def _reference() -> str:
    skill = Path(bootstrap_adr.__file__).resolve().parent.parent
    return (skill / "references" / "scripts.md").read_text(encoding="utf-8")


def _decision_repo(tmp_path: Path) -> Path:
    repo = new_repo(tmp_path / "r")
    write(repo, "docs/adr/0001-first.md", "# 1. First\n\n## Status\n\nAccepted\n")
    commit(repo, f"Adopt Postgres instead of MySQL\n\n{WHY}\n")
    return repo


def _main(capsys: pytest.CaptureFixture[str], *args: str) -> tuple[int, dict[str, Any]]:
    code = bootstrap_adr.main(list(args))
    payload: dict[str, Any] = json.loads(capsys.readouterr().out)
    return code, payload


# --- C21: an empty or bare partial clone filter marks a partial clone on older git ---


@pytest.mark.parametrize("bare_key", [False, True])
def test_an_empty_partial_clone_filter_marks_a_partial_clone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, bare_key: bool
) -> None:
    repo = new_repo(tmp_path / "r")
    commit(repo, "Initial work")
    if bare_key:
        config = repo / ".git" / "config"
        config.write_text(
            config.read_text(encoding="utf-8") + '[remote "origin"]\n\tpartialclonefilter\n',
            encoding="utf-8",
        )
    else:
        git(repo, "config", "remote.origin.partialclonefilter", "")
    monkeypatch.setattr(bootstrap_adr, "_git_version", lambda _root: (2, 37, 0))

    with pytest.raises(adr_scan.ConfigError, match="partial clone"):
        bootstrap_adr._refuse_lazy_fetch(repo)


def test_a_full_clone_with_a_remote_is_still_scanned_on_older_git(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = new_repo(tmp_path / "r")
    commit(repo, "Initial work")
    git(repo, "remote", "add", "origin", "https://example.invalid/o/r.git")
    monkeypatch.setattr(bootstrap_adr, "_git_version", lambda _root: (2, 37, 0))

    bootstrap_adr._refuse_lazy_fetch(repo)


def test_an_empty_filter_on_a_fixed_git_is_not_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = new_repo(tmp_path / "r")
    commit(repo, "Initial work")
    git(repo, "config", "remote.origin.partialclonefilter", "")
    monkeypatch.setattr(bootstrap_adr, "_git_version", lambda _root: (2, 45, 1))

    bootstrap_adr._refuse_lazy_fetch(repo)


# --- C26: an offset with 60 or more minutes is refused ---


@pytest.mark.parametrize("since", ["2026-01-31T08:00:00+01:99", "2026-01-31T08:00+0160"])
def test_an_offset_git_would_ignore_is_refused(since: str) -> None:
    with pytest.raises(adr_scan.ConfigError, match="ISO 8601"):
        bootstrap_adr._check_since(since)


@pytest.mark.parametrize("since", ["2026-01-31T08:00:00+01:59", "2026-01-31T08:00:00-05:00"])
def test_a_valid_offset_passes_unchanged(since: str) -> None:
    assert bootstrap_adr._check_since(since) == since


def test_a_bare_date_still_means_local_midnight() -> None:
    assert bootstrap_adr._check_since("2026-01-31") == "2026-01-31T00:00:00"


# --- C27: scan publishes and reports the path the second check returned ---


@pytest.mark.skipif(os.name == "nt", reason="needs a folder symlink")
def test_scan_writes_and_reports_the_path_the_second_check_resolved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _decision_repo(tmp_path)
    (tmp_path / "out").mkdir()
    other = tmp_path / "other"
    other.mkdir()
    real = adr_scan.scan

    def swapping(*args: Any) -> dict[str, Any]:
        result: dict[str, Any] = real(*args)
        (tmp_path / "out").rename(tmp_path / "out-old")
        (tmp_path / "out").symlink_to(other, target_is_directory=True)
        return result

    monkeypatch.setattr(bootstrap_adr, "scan", swapping)
    out = tmp_path / "out" / "scan.json"
    code, payload = _main(capsys, "scan", "--repo", str(repo), "--out", str(out))

    assert code == 0
    assert payload["out"] == str((other / "scan.json").resolve())
    assert Path(payload["out"]).is_file() and "leftover" not in payload


# --- C28: a title that is empty once cleaned is refused before any folder exists ---


def test_a_title_of_only_control_characters_is_refused(tmp_path: Path) -> None:
    repo = _decision_repo(tmp_path)
    scan = _scan_file(tmp_path, repo, _cand(title="\x00\x01"))
    out = tmp_path / "plain" / "scratch"

    with pytest.raises(adr_scan.ConfigError, match="no title"):
        bootstrap_adr.draft(scan, "c-1234567", str(out), "Proposed")
    assert not (tmp_path / "plain").exists()


def test_a_title_with_a_removable_control_character_still_drafts(tmp_path: Path) -> None:
    repo = _decision_repo(tmp_path)
    scan = _scan_file(tmp_path, repo, _cand(title="Use\x00 Postgres"))
    result = bootstrap_adr.draft(scan, "c-1234567", str(tmp_path / "scratch"), "Proposed")

    assert "Use Postgres" in _text(result)


# --- C212: a draft the scanner cannot read back is refused ---


def _draft_with_excerpt(tmp_path: Path, folder: str, excerpt: str) -> dict[str, Any]:
    repo = tmp_path / "named"
    scan = _scan_file(tmp_path, repo, _cand(excerpt=excerpt))
    result: dict[str, Any] = bootstrap_adr.draft(
        scan, "c-1234567", str(tmp_path / folder), "Proposed"
    )
    return result


def test_a_draft_over_the_read_cap_is_refused_and_one_at_the_cap_is_written(
    tmp_path: Path,
) -> None:
    base = Path(_draft_with_excerpt(tmp_path, "a", "x")["path"]).stat().st_size
    fits = "x" * (adr_locate.MAX_READ_BYTES - base + 1)

    at_cap = Path(_draft_with_excerpt(tmp_path, "b", fits)["path"])
    assert at_cap.stat().st_size == adr_locate.MAX_READ_BYTES
    assert adr_locate.read_bounded(at_cap) is not None
    with pytest.raises(adr_scan.ConfigError, match="over 1 MiB"):
        _draft_with_excerpt(tmp_path, "c", fits + "x")
    assert not (tmp_path / "c").exists()


# --- C25: a long target name still fits beside its temporary file ---


def test_a_target_name_near_the_limit_is_published(tmp_path: Path) -> None:
    name = "a" * 247 + ".md"
    try:
        (tmp_path / "probe").mkdir()
        (tmp_path / "probe" / name).write_bytes(b"")
    except OSError:
        pytest.skip("this filesystem refuses a 250-byte name")
    target = tmp_path / "out" / name

    assert adr_write.create_new(target, b"body") is None
    assert target.read_bytes() == b"body" and os.listdir(target.parent) == [name]


# --- C22, C23, C24, C213, C214: the reference says what the CLI does ---


def test_the_reference_gives_proposed_as_the_default_status(tmp_path: Path) -> None:
    text = _reference()
    assert "status `Proposed`, published" not in text
    assert "status `Proposed` by default" in text
    repo = _decision_repo(tmp_path)
    scan = _scan_file(tmp_path, repo, _cand())
    result = bootstrap_adr.draft(scan, "c-1234567", str(tmp_path / "s"), "Rejected")
    assert result["status"] == "Rejected" and "Rejected" in _text(result)


def test_the_reference_promises_atomic_publication_only_with_hard_links() -> None:
    text = _reference()
    assert "never seen half-written" not in text
    assert "hard-linked into place publishes atomically" in text
    assert "a reader can see it empty or partial" in text


def test_the_reference_names_config_for_an_unreadable_input_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    text = _reference()
    assert "reports `config` when it cannot open or read its `--scan` or `--prs-json`" in text
    assert "report `io` with exit 2" in text
    missing = str(tmp_path / "missing.json")
    code, payload = _main(capsys, "draft", "--scan", missing, "--id", "x", "--out", "o")
    assert (code, payload["error"]) == (2, "config")


def test_the_reference_splits_the_out_rules_of_scan_and_draft(tmp_path: Path) -> None:
    text = _reference()
    assert "or into a place git reports no work tree for" not in text
    assert "a refused `scan --out` (inside any work tree of the repository, a directory" in text
    assert "is a scratch folder and takes the draft" in text
    repo = _decision_repo(tmp_path)
    (tmp_path / "existing").mkdir()
    scan = _scan_file(tmp_path, repo, _cand())
    result = bootstrap_adr.draft(scan, "c-1234567", str(tmp_path / "existing"), "Proposed")
    assert result["in_repo"] is False
    (tmp_path / "file").write_text("x", encoding="utf-8")
    with pytest.raises(adr_scan.ConfigError, match="not"):
        bootstrap_adr.draft(scan, "c-1234567", str(tmp_path / "file"), "Proposed")


def test_the_reference_states_the_output_folder_trust_assumption() -> None:
    text = _reference()
    assert "The `--out` folder and its parents must not change during a run" in text
    assert "its folder must not change during a run" in (bootstrap_adr.__doc__ or "")
