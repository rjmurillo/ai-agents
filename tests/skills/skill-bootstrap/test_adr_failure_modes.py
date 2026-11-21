"""Tests for how bootstrap_adr.py fails and what its payloads say it skipped."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import adr_locate
import adr_scan
import bootstrap_adr
import pytest
from adr_helpers import commit, git, new_repo, write
from draft_helpers import _cand, _scan_file


def _adr_repo(path: Path) -> Path:
    repo = new_repo(path)
    write(repo, "docs/adr/0001-first.md", "# 1. First\n\n## Status\n\nAccepted\n")
    commit(repo, "Initial work")
    return repo


def _run(argv: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, dict[str, Any]]:
    code = bootstrap_adr.main(argv)
    return code, json.loads(capsys.readouterr().out)


# ---------------------------------------------------------------------------
# Item 15: failures map to the documented exit codes
# ---------------------------------------------------------------------------


def test_a_scan_file_nested_past_the_recursion_limit_is_exit_two(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    deep = write(tmp_path, "deep.json", "[" * 200_000 + "]" * 200_000)
    code, payload = _run(
        ["draft", "--scan", str(deep), "--id", "c-1", "--out", str(tmp_path / "o")], capsys
    )
    assert code == 2 and payload["error"] == "config"


def test_a_prs_export_nested_past_the_recursion_limit_is_exit_two(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _adr_repo(tmp_path / "r")
    deep = write(tmp_path, "deep.json", "[" * 200_000 + "]" * 200_000)
    argv = ["scan", "--repo", str(repo), "--prs-json", str(deep), "--out", str(tmp_path / "s.json")]
    code, payload = _run(argv, capsys)
    assert code == 2 and payload["error"] == "config"
    assert not (tmp_path / "s.json").exists()


def test_a_path_with_a_nul_byte_is_exit_two_not_a_traceback(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _adr_repo(tmp_path / "r")
    code, payload = _run(["scan", "--repo", str(repo), "--out", "scan\x00.json"], capsys)
    assert code == 2 and payload["error"] == "config"


def test_a_unicode_error_is_exit_two_config(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def broken(args: Any) -> Any:
        raise UnicodeEncodeError("utf-8", "\ud800", 0, 1, "surrogates not allowed")

    monkeypatch.setitem(bootstrap_adr._HANDLERS, "locate", broken)
    code, payload = _run(["locate", "--repo", str(tmp_path)], capsys)
    assert code == 2 and payload["error"] == "config"


def test_an_unexpected_exception_prints_json_and_exits_two_as_internal(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def broken(args: Any) -> Any:
        raise RuntimeError("boom")

    monkeypatch.setitem(bootstrap_adr._HANDLERS, "locate", broken)
    code, payload = _run(["locate", "--repo", str(tmp_path)], capsys)
    assert code == 2 and payload["error"] == "internal"
    assert "RuntimeError" in payload["message"] and "boom" in payload["message"]


def test_exit_one_is_still_only_for_exists(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def broken(args: Any) -> Any:
        raise RuntimeError("boom")

    monkeypatch.setitem(bootstrap_adr._HANDLERS, "locate", broken)
    assert bootstrap_adr.main(["locate", "--repo", str(tmp_path)]) not in (0, 1, 3)


# ---------------------------------------------------------------------------
# Item 19: say what was skipped
# ---------------------------------------------------------------------------


def _deep(repo: Path, depth: int) -> None:
    (repo.joinpath(*[f"d{i}" for i in range(depth)])).mkdir(parents=True)


def test_locate_reports_a_walk_cut_at_the_depth_limit(tmp_path: Path) -> None:
    repo = new_repo(tmp_path / "r")
    _deep(repo, 10)
    commit(repo, "Initial work")
    assert adr_locate.locate(repo)["walk_truncated"] is True


def test_locate_reports_a_walk_cut_at_the_directory_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = new_repo(tmp_path / "r")
    for name in "abcdef":
        (repo / name).mkdir()
    commit(repo, "Initial work")
    monkeypatch.setattr(adr_locate, "_MAX_WALK_DIRS", 3)
    assert adr_locate.locate(repo)["walk_truncated"] is True


def test_locate_reports_a_complete_walk_as_not_truncated(tmp_path: Path) -> None:
    repo = new_repo(tmp_path / "r")
    _deep(repo, 3)
    commit(repo, "Initial work")
    assert adr_locate.locate(repo)["walk_truncated"] is False


def test_a_folder_found_without_a_walk_is_not_truncated(tmp_path: Path) -> None:
    assert adr_locate.locate(_adr_repo(tmp_path / "r"))["walk_truncated"] is False


def test_scan_carries_the_walk_flag(tmp_path: Path) -> None:
    repo = new_repo(tmp_path / "r")
    _deep(repo, 10)
    commit(repo, "Initial work")
    assert adr_scan.scan(repo, "HEAD", 10, None, None)["walk_truncated"] is True


def test_scan_reports_a_shallow_clone(tmp_path: Path) -> None:
    source = _adr_repo(tmp_path / "src")
    commit(source, "Second change to the source")
    clone = tmp_path / "clone"
    git(tmp_path, "clone", "-q", "--depth", "1", f"file://{source}", str(clone))
    assert adr_scan.scan(clone, "HEAD", 10, None, None)["shallow"] is True


def test_scan_reports_a_full_repository_as_not_shallow(tmp_path: Path) -> None:
    repo = _adr_repo(tmp_path / "r")
    assert adr_scan.scan(repo, "HEAD", 10, None, None)["shallow"] is False


def test_scan_counts_decision_log_files_and_the_ones_it_skipped(tmp_path: Path) -> None:
    repo = _adr_repo(tmp_path / "r")
    write(repo, "DECISIONS.md", "## D1 - Use pnpm\n\nBecause it is faster in CI runs.\n")
    write(repo, "docs/decisions.md", "x" * (adr_locate.MAX_READ_BYTES + 1))
    commit(repo, "Add the decision logs")
    examined = adr_scan.scan(repo, "HEAD", 10, None, None)["examined"]
    assert examined["log_files"] == 2 and examined["log_files_skipped"] == 1


def test_scan_counts_no_log_files_when_there_are_none(tmp_path: Path) -> None:
    examined = adr_scan.scan(_adr_repo(tmp_path / "r"), "HEAD", 10, None, None)["examined"]
    assert examined["log_files"] == 0 and examined["log_files_skipped"] == 0


# ---------------------------------------------------------------------------
# Item 20: a collision leaves the draft on disk, and says so
# ---------------------------------------------------------------------------


def _racing(monkeypatch: pytest.MonkeyPatch) -> None:
    real = adr_locate.folder_style

    def racing(directory: Path) -> Any:
        style = real(directory)
        (directory / "0002-written-by-someone-else.md").write_text("theirs\n", encoding="utf-8")
        return style

    monkeypatch.setattr(bootstrap_adr, "folder_style", racing)


def test_a_collision_exits_one_names_the_twin_and_leaves_the_draft_on_disk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _adr_repo(tmp_path / "r")
    folder = repo / "docs" / "adr"
    _racing(monkeypatch)
    scan = _scan_file(tmp_path, repo, _cand())
    code, payload = _run(
        ["draft", "--scan", scan, "--id", "c-1234567", "--out", str(folder)], capsys
    )
    draft = Path(payload["path"])
    assert code == 1 and payload["error"] == "exists"
    assert payload["others"] == ["0002-written-by-someone-else.md"]
    assert draft.is_file() and draft.parent == folder.resolve()


def test_the_collision_message_says_where_the_draft_is_and_what_to_do(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _adr_repo(tmp_path / "r")
    _racing(monkeypatch)
    scan = _scan_file(tmp_path, repo, _cand())
    _code, payload = _run(
        ["draft", "--scan", scan, "--id", "c-1234567", "--out", str(repo / "docs" / "adr")], capsys
    )
    message = payload["message"]
    assert f"draft was written to {payload['path']}" in message
    assert "another ADR has number 2" in message
    assert "renumber or remove one" in message


def test_the_help_and_the_reference_state_that_a_collision_leaves_the_draft(
    capsys: pytest.CaptureFixture[str],
) -> None:
    epilog = bootstrap_adr._HELP_EPILOG
    assert "draft stays on disk" in epilog
    reference = (
        Path(bootstrap_adr.__file__).resolve().parent.parent / "references" / "scripts.md"
    ).read_text(encoding="utf-8")
    assert "leaves the draft on disk" in reference
