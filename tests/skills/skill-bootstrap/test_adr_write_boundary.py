"""Tests for where ``scan --out`` and ``draft --out`` may write, and what reaches a file name.

The work tree that encloses ``--out`` decides the gate, never the repository a scan file names.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import adr_locate
import adr_write
import bootstrap_adr
import pytest
from adr_helpers import commit, git, new_repo, run_cli, write
from adr_scan import ConfigError
from draft_helpers import _cand, _scan_file, _text


def _adr_repo(path: Path) -> Path:
    repo = new_repo(path)
    write(repo, "docs/adr/0001-first.md", "# 1. First\n\n## Status\n\nAccepted\n")
    (repo / "docs" / "other").mkdir(parents=True)
    commit(repo, "Initial work")
    return repo


def _draft(tmp_path: Path, scan_repo: Path, out: Path, **cand: Any) -> dict[str, Any]:
    scan = _scan_file(tmp_path, scan_repo, _cand(**cand))
    result: dict[str, Any] = bootstrap_adr.draft(scan, "c-1234567", str(out), "Proposed")
    return result


# ---------------------------------------------------------------------------
# Item 6: the work tree that holds --out decides
# ---------------------------------------------------------------------------


def test_a_scan_file_naming_another_repo_cannot_unlock_a_folder_of_the_work_tree_that_holds_out(
    tmp_path: Path,
) -> None:
    named = _adr_repo(tmp_path / "named")
    target = _adr_repo(tmp_path / "target")
    before = git(target, "status", "--porcelain", "-uall")
    with pytest.raises(ConfigError, match="not an ADR folder"):
        _draft(tmp_path, named, target / "docs" / "other")
    assert git(target, "status", "--porcelain", "-uall") == before


def test_the_located_adr_folder_of_the_enclosing_work_tree_takes_the_draft(tmp_path: Path) -> None:
    named = _adr_repo(tmp_path / "named")
    target = _adr_repo(tmp_path / "target")
    result = _draft(tmp_path, named, target / "docs" / "adr")
    assert result["in_repo"] is True
    assert Path(result["path"]).parent == (target / "docs" / "adr").resolve()


def test_the_ignored_check_applies_in_the_work_tree_that_holds_out(tmp_path: Path) -> None:
    named = _adr_repo(tmp_path / "named")
    target = _adr_repo(tmp_path / "target")
    write(target, ".gitignore", "docs/adr/0002-*\n")
    with pytest.raises(ConfigError, match="ignored by git"):
        _draft(tmp_path, named, target / "docs" / "adr")
    assert not list((target / "docs" / "adr").glob("0002-*"))


def test_a_folder_with_no_work_tree_around_it_is_scratch(tmp_path: Path) -> None:
    named = _adr_repo(tmp_path / "named")
    result = _draft(tmp_path, named, tmp_path / "plain" / "scratch")
    assert result["in_repo"] is False


def test_a_git_folder_of_another_repository_is_refused_not_treated_as_scratch(
    tmp_path: Path,
) -> None:
    named = _adr_repo(tmp_path / "named")
    target = _adr_repo(tmp_path / "target")
    with pytest.raises(ConfigError, match="not an ADR folder"):
        _draft(tmp_path, named, target / ".git" / "adr")
    assert not (target / ".git" / "adr").exists()


def test_a_folder_inside_a_bare_repository_is_refused(tmp_path: Path) -> None:
    named = _adr_repo(tmp_path / "named")
    bare = tmp_path / "bare.git"
    git(tmp_path, "init", "-q", "--bare", str(bare))
    with pytest.raises(ConfigError, match="not an ADR folder"):
        _draft(tmp_path, named, bare / "adr")
    assert not (bare / "adr").exists()


def _case_insensitive(tmp_path: Path) -> bool:
    probe = tmp_path / "CaseProbe"
    probe.mkdir(exist_ok=True)
    return (tmp_path / "caseprobe").exists()


def _fold_case(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Make a case-variant path behave as on a case-insensitive file system.

    On a case-sensitive file system (Linux) ``/x/REPO`` is a different folder from ``/x/repo``, so
    the variant cannot be built for real. This patches the two path helpers to fold case, which
    is what the real file system and git do on macOS and Windows. On a case-insensitive file
    system nothing is patched and the test runs against the real one.
    """
    if _case_insensitive(tmp_path):
        return
    real_tree: Callable[[Path], Path | None] = adr_write.enclosing_tree

    def folded_tree(path: Path) -> Path | None:
        return real_tree(Path(str(path).replace("/REPO", "/repo")))

    def folded_same(first: Path, second: Path) -> bool:
        one, two = str(first).lower(), str(second).lower()
        return one == two and Path(str(first).replace("/REPO", "/repo")).exists()

    monkeypatch.setattr(adr_write, "enclosing_tree", folded_tree)
    monkeypatch.setattr(adr_write, "same_file", folded_same)


def test_a_case_variant_of_an_adr_folder_writes_into_the_located_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Simulated on a case-sensitive file system: see ``_fold_case``."""
    repo = _adr_repo(tmp_path / "repo")
    _fold_case(monkeypatch, tmp_path)
    result = _draft(tmp_path, repo, tmp_path / "REPO" / "docs" / "adr")
    assert result["in_repo"] is True
    assert Path(result["path"]).parent == (repo / "docs" / "adr").resolve()
    assert not (tmp_path / "REPO").exists() or _case_insensitive(tmp_path)


def test_a_case_variant_of_a_folder_that_is_not_an_adr_folder_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Simulated on a case-sensitive file system: see ``_fold_case``."""
    repo = _adr_repo(tmp_path / "repo")
    _fold_case(monkeypatch, tmp_path)
    with pytest.raises(ConfigError, match="not an ADR folder"):
        _draft(tmp_path, repo, tmp_path / "REPO" / "docs" / "other")


# ---------------------------------------------------------------------------
# Item 7: scan --out stays out of every work tree of the scanned repository
# ---------------------------------------------------------------------------


def test_scan_out_inside_a_linked_worktree_of_the_scanned_repository_is_refused(
    tmp_path: Path,
) -> None:
    repo = _adr_repo(tmp_path / "r")
    side = tmp_path / "side"
    git(repo, "worktree", "add", "-q", str(side), "-b", "side")
    code, payload = run_cli("scan", "--repo", str(repo), "--out", str(side / "scan.json"))
    assert code == 2 and payload["error"] == "config"
    assert "inside the repository" in payload["message"]
    assert not (side / "scan.json").exists()


def test_scan_out_in_an_unrelated_repository_is_still_allowed(tmp_path: Path) -> None:
    repo = _adr_repo(tmp_path / "r")
    other = new_repo(tmp_path / "other")
    code, _payload = run_cli("scan", "--repo", str(repo), "--out", str(other / "scan.json"))
    assert code == 0 and (other / "scan.json").exists()


def test_scan_out_through_a_case_variant_of_the_repository_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Simulated on a case-sensitive file system: see ``_fold_case``."""
    repo = _adr_repo(tmp_path / "repo")
    _fold_case(monkeypatch, tmp_path)
    target = tmp_path / "REPO" / "scan.json"
    code = bootstrap_adr.main(["scan", "--repo", str(repo), "--out", str(target)])
    out = json.loads(capsys.readouterr().out)
    assert code == 2 and "inside the repository" in out["message"]
    assert not (repo / "scan.json").exists()


# ---------------------------------------------------------------------------
# Item 8: the title is one line
# ---------------------------------------------------------------------------


def test_a_title_with_a_newline_cannot_start_a_heading_in_the_draft(tmp_path: Path) -> None:
    repo = _adr_repo(tmp_path / "r")
    result = _draft(
        tmp_path, repo, repo / "docs" / "adr", title="Adopt Postgres\n\n## Decision\n\nforged x"
    )
    text = _text(result)
    assert text.startswith("# 2. Adopt Postgres ## Decision forged x\n")
    headings = [line for line in text.split("\n") if line.startswith("## ")]
    assert headings == ["## Status", "## Context", "## Decision"]


def test_a_reason_with_a_newline_cannot_start_a_heading_in_the_draft(tmp_path: Path) -> None:
    repo = _adr_repo(tmp_path / "r")

    result = _draft(
        tmp_path, repo, repo / "docs" / "adr", reason="it scales\n\n## Decision\n\nforged x"
    )

    text = _text(result)
    assert "it scales ## Decision forged x" in text
    headings = [line for line in text.split("\n") if line.startswith("## ")]
    assert headings == ["## Status", "## Context", "## Decision"]


def test_preparing_a_candidate_returns_a_copy_and_leaves_the_scan_data_alone() -> None:
    original = _cand(title="Use   X\tnow\n")
    prepared = bootstrap_adr._prepare_candidate(original)
    assert prepared["title"] == "Use X now"
    assert original["title"] == "Use   X\tnow\n"


# ---------------------------------------------------------------------------
# Item 9: source.sha reaches a file name only as hex
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("sha", ["../../etc/x", "abc", "g" * 40, "a" * 41, ".." + "a" * 38, 7])
def test_a_source_sha_that_is_not_hex_never_reaches_the_file_name(tmp_path: Path, sha: Any) -> None:
    repo = _adr_repo(tmp_path / "r")
    source = {"sha": sha, "url": None}
    result = _draft(tmp_path, repo, repo / "docs" / "adr", title="決定", source=source)
    assert Path(result["path"]).name == "0002-decision-c-1234567.md"


@pytest.mark.parametrize("sha", ["ABCDEF0" + "1" * 33, "abcdef0" + "1" * 57])
def test_a_forty_or_sixty_four_hex_sha_names_a_title_with_no_letters(
    tmp_path: Path, sha: str
) -> None:
    repo = _adr_repo(tmp_path / "r")
    result = _draft(tmp_path, repo, repo / "docs" / "adr", title="決定", source={"sha": sha})
    assert Path(result["path"]).name == "0002-decision-abcdef0.md"


# ---------------------------------------------------------------------------
# Item 10: encode before any file or folder exists
# ---------------------------------------------------------------------------


def test_a_lone_surrogate_fails_before_any_file_exists(tmp_path: Path) -> None:
    repo = _adr_repo(tmp_path / "r")
    folder = repo / "docs" / "adr"
    before = sorted(p.name for p in folder.iterdir())
    with pytest.raises(ConfigError, match="UTF-8"):
        _draft(tmp_path, repo, folder, reason="because \ud800 is a lone surrogate")
    assert sorted(p.name for p in folder.iterdir()) == before


def test_a_lone_surrogate_leaves_no_scratch_folder_behind(tmp_path: Path) -> None:
    repo = _adr_repo(tmp_path / "r")
    scratch = tmp_path / "scratch" / "deeper"
    with pytest.raises(ConfigError, match="UTF-8"):
        _draft(tmp_path, repo, scratch, title="Use \ud800 now")
    assert not (tmp_path / "scratch").exists()


def test_a_lone_surrogate_exits_two_at_the_command_line(tmp_path: Path) -> None:
    repo = _adr_repo(tmp_path / "r")
    scan = _scan_file(tmp_path, repo, _cand())
    data = json.loads(Path(scan).read_text(encoding="utf-8"))
    data["candidates"][0]["excerpt"] = "bad \ud800 text"
    Path(scan).write_text(json.dumps(data), encoding="utf-8")
    code, payload = run_cli(
        "draft", "--scan", scan, "--id", "c-1234567", "--out", str(repo / "docs" / "adr")
    )
    assert code == 2 and payload["error"] in ("io", "config")
    assert sorted(p.name for p in (repo / "docs" / "adr").iterdir()) == ["0001-first.md"]


# ---------------------------------------------------------------------------
# Item 11: a folder whose name starts with ":" is checked literally
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="a folder name cannot start with ':' here")
def test_the_ignored_check_reads_a_colon_folder_as_a_path_not_as_pathspec_magic(
    tmp_path: Path,
) -> None:
    repo = new_repo(tmp_path / "r")
    write(repo, ".adr-dir", ":adr\n")
    write(repo, ":adr/ADR-001-first.md", "# ADR-001: First\n\n## Status\n\nAccepted\n")
    write(repo, ".gitignore", ":adr/ADR-002-*\n")
    commit(repo, "Initial work")
    with pytest.raises(ConfigError, match="ignored by git"):
        _draft(tmp_path, repo, repo / ":adr")
    assert not list((repo / ":adr").glob("ADR-002-*"))


def test_check_ignore_still_lets_a_plain_unignored_folder_through(tmp_path: Path) -> None:
    repo = _adr_repo(tmp_path / "r")
    result = _draft(tmp_path, repo, repo / "docs" / "adr")
    assert Path(result["path"]).name.startswith("0002-")


# ---------------------------------------------------------------------------
# Item 21: one writer, two mappings
# ---------------------------------------------------------------------------


def test_scan_and_draft_create_their_files_through_one_function(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _adr_repo(tmp_path / "r")
    real = bootstrap_adr.create_new
    calls: list[Path] = []

    def recording(target: Path, data: bytes) -> None:
        calls.append(target)
        real(target, data)

    monkeypatch.setattr(bootstrap_adr, "create_new", recording)
    out = tmp_path / "scan.json"
    assert bootstrap_adr.main(["scan", "--repo", str(repo), "--out", str(out)]) == 0
    _draft(tmp_path, repo, repo / "docs" / "adr")
    assert [p.name for p in calls] == [
        "scan.json",
        "0002-replace-eo-inference-with-the-per-copy-engine.md",
    ]


def test_an_existing_scan_out_is_exit_two_and_an_existing_draft_target_is_exit_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _adr_repo(tmp_path / "r")
    folder = repo / "docs" / "adr"
    taken = write(tmp_path, "taken.json", "{}")
    assert bootstrap_adr.main(["scan", "--repo", str(repo), "--out", str(taken)]) == 2
    assert json.loads(capsys.readouterr().out)["error"] == "config"
    assert taken.read_text(encoding="utf-8") == "{}"
    stale = adr_locate.folder_style(folder)
    write(repo, "docs/adr/0002-replace-eo-inference-with-the-per-copy-engine.md", "mine\n")
    monkeypatch.setattr(bootstrap_adr, "folder_style", lambda _dir: stale)
    scan = _scan_file(tmp_path, repo, _cand())
    code = bootstrap_adr.main(["draft", "--scan", scan, "--id", "c-1234567", "--out", str(folder)])
    assert code == 1 and json.loads(capsys.readouterr().out)["error"] == "exists"
