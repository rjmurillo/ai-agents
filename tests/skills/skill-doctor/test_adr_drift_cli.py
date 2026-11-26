"""adr_drift.py locate, exit codes, read-only scan, no network, and --help."""

from __future__ import annotations

import hashlib
import json
import shutil
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any

import adr_drift
import adr_git
import pytest
from adr_drift_helpers import (
    ADR_DIR,
    adr_path,
    adr_text,
    commit,
    git,
    init_repo,
    kinds,
    run_cli,
    scan,
    seeded_repo,
    symlink_or_skip,
)

SCRIPT = Path(__file__).resolve().parents[3] / "src/claude/skills/skill-doctor/scripts/adr_drift.py"
KNOWN = [
    ".project-toolkit/architecture",
    "docs/adr",
    "docs/architecture",
    "docs/decisions",
    "architecture/decisions",
    "doc/adr",
]


def _locate(capsys: pytest.CaptureFixture[str], repo: Path) -> dict[str, Any]:
    code, out, err = run_cli(capsys, "locate", "--repo", str(repo))
    assert code == 0, err
    located: dict[str, Any] = json.loads(out)
    return located


@pytest.mark.parametrize("folder", KNOWN)
def test_locate_finds_each_known_folder(tmp_path, capsys, folder):
    repo = seeded_repo(tmp_path / "repo", {f"{folder}/ADR-001-first.md": adr_text(1)})

    located = _locate(capsys, repo)

    assert [d["path"] for d in located["adr_dirs"]] == [folder]
    assert located["primary"] == folder and located["next_number"] == 2


def test_locate_reads_the_adr_tools_marker_and_it_is_authoritative(tmp_path, capsys):
    repo = seeded_repo(
        tmp_path / "repo",
        {
            ".adr-dir": "records\n",
            "records/0001-first.md": "# 1. First\n",
            "docs/adr/ADR-001-x.md": adr_text(1),
        },
    )

    located = _locate(capsys, repo)

    assert [d["path"] for d in located["adr_dirs"]] == ["records"]
    assert located["markers"] == [".adr-dir"] and located["primary"] == "records"


def test_locate_ignores_a_marker_that_points_outside_the_repo(tmp_path, capsys):
    repo = seeded_repo(
        tmp_path / "repo", {".adr-dir": "../elsewhere\n", "docs/adr/ADR-001-x.md": adr_text(1)}
    )

    assert _locate(capsys, repo)["primary"] == "docs/adr"


def test_locate_skips_a_known_folder_symlinked_outside_the_repo(tmp_path, capsys):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "ADR-007-x.md").write_text(adr_text(7), encoding="utf-8")
    repo = seeded_repo(tmp_path / "repo")
    (repo / "docs").mkdir(exist_ok=True)
    symlink_or_skip(repo / "docs" / "decisions", outside)

    paths = [d["path"] for d in _locate(capsys, repo)["adr_dirs"]]

    assert "docs/decisions" not in paths


def test_locate_reports_adr_tools_naming(tmp_path, capsys):
    repo = seeded_repo(
        tmp_path / "repo",
        {
            "doc/adr/0001-first.md": "# 1. First\n\n## Status\n\nAccepted\n",
            "doc/adr/0007-last.md": "# 7. Last\n\n## Status\n\nAccepted\n\n## Context\n",
        },
    )

    entry = _locate(capsys, repo)["adr_dirs"][0]

    assert (
        entry["convention"],
        entry["prefix"],
        entry["width"],
        entry["h1_form"],
        entry["count"],
    ) == (
        "NNNN",
        "",
        4,
        "number-dot",
        2,
    )


def test_locate_with_no_folder_has_null_primary_and_next_one(tmp_path, capsys):
    repo = init_repo(tmp_path / "repo")
    commit(repo, {"README.md": "x"}, "docs: readme")

    located = _locate(capsys, repo)

    assert located["adr_dirs"] == [] and located["primary"] is None
    assert located["next_number"] == 1 and located["template_headings"] == []


def test_locate_primary_is_null_with_two_folders(tmp_path, capsys):
    repo = seeded_repo(
        tmp_path / "repo",
        {"docs/adr/ADR-001-a.md": adr_text(1), "docs/decisions/ADR-002-b.md": adr_text(2)},
    )

    located = _locate(capsys, repo)

    assert len(located["adr_dirs"]) == 2 and located["primary"] is None
    assert located["next_number"] == 3


def test_locate_template_headings_come_from_the_newest_adr(tmp_path, capsys):
    repo = seeded_repo(tmp_path / "repo", {adr_path(1): adr_text(1), adr_path(2): adr_text(2)})

    assert _locate(capsys, repo)["template_headings"] == ["Status", "Context", "Decision"]


def test_locate_from_a_subdirectory_resolves_the_repo_root(tmp_path, capsys):
    repo = seeded_repo(tmp_path / "repo")
    (repo / "sub").mkdir()

    assert _locate(capsys, repo / "sub")["primary"] == ADR_DIR


def test_repo_root_of_a_subdirectory_is_the_top_level(tmp_path):
    repo = seeded_repo(tmp_path / "repo")
    (repo / "deep" / "er").mkdir(parents=True)

    assert adr_drift.repo_root(str(repo / "deep" / "er")) == repo.resolve()


def test_repo_root_follows_a_symlink_to_the_repository(tmp_path):
    repo = seeded_repo(tmp_path / "repo")
    link = tmp_path / "link"
    symlink_or_skip(link, repo)

    assert adr_drift.repo_root(str(link)) == repo.resolve()


def _core_worktree_sibling(tmp_path: Path) -> Path:
    repo = seeded_repo(tmp_path / "repo")
    (tmp_path / "elsewhere").mkdir()
    git(repo, "config", "core.worktree", str(tmp_path / "elsewhere"))
    return repo


def _core_worktree_parent(tmp_path: Path) -> Path:
    repo = seeded_repo(tmp_path / "repo")
    git(repo, "config", "core.worktree", str(tmp_path))
    return repo


def _core_worktree_root(tmp_path: Path) -> Path:
    repo = seeded_repo(tmp_path / "repo")
    git(repo, "config", "core.worktree", "/")
    return repo


def _core_worktree_parent_repo(tmp_path: Path) -> Path:
    outer = init_repo(tmp_path / "outer")
    repo = seeded_repo(outer / "repo")
    git(repo, "config", "core.worktree", str(outer))
    return repo


def _core_worktree_through_gitdir_file(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    git(tmp_path, "init", "-q", "-b", "main", "--separate-git-dir", str(tmp_path / "gd"), "repo")
    assert (repo / ".git").is_file()
    subprocess.run(
        ["git", f"--git-dir={tmp_path / 'gd'}", "config", "core.worktree", str(tmp_path)],
        check=True,
    )
    return repo


@pytest.mark.parametrize(
    "build",
    [
        _core_worktree_sibling,
        _core_worktree_parent,
        _core_worktree_root,
        _core_worktree_parent_repo,
        _core_worktree_through_gitdir_file,
    ],
)
@pytest.mark.parametrize("command", ["locate", "scan"])
def test_a_core_worktree_that_is_not_the_named_repository_is_refused(
    tmp_path, capsys, command, build
):
    repo = build(tmp_path)
    extra = ["--out", str(tmp_path / "o.json")] if command == "scan" else []

    code, out, err = run_cli(capsys, command, "--repo", str(repo), *extra)

    assert code == 2 and out == "" and "git top level outside itself" in err
    assert not (tmp_path / "o.json").exists()


def test_a_bare_repository_is_refused(tmp_path, capsys):
    git(tmp_path, "init", "-q", "--bare", "bare.git")

    code, out, err = run_cli(capsys, "locate", "--repo", str(tmp_path / "bare.git"))

    assert code == 2 and out == "" and "not a git repository" in err


def test_a_folder_with_no_git_entry_anywhere_above_it_is_refused(tmp_path, monkeypatch):
    plain = tmp_path / "plain"
    plain.mkdir()
    monkeypatch.setattr(adr_drift, "run_git", lambda *args, **kwargs: str(plain))

    with pytest.raises(adr_drift.ExitError) as caught:
        adr_drift.repo_root(str(plain))

    assert caught.value.code == 2 and "no .git entry" in str(caught.value)


def test_repo_root_accepts_a_linked_worktree_and_its_subfolder(tmp_path):
    repo = seeded_repo(tmp_path / "repo")
    linked = tmp_path / "linked"
    git(repo, "worktree", "add", "-q", "-b", "side", str(linked))
    (linked / "deep").mkdir()

    assert (linked / ".git").is_file()
    assert adr_drift.repo_root(str(linked)) == linked.resolve()
    assert adr_drift.repo_root(str(linked / "deep")) == linked.resolve()


def test_repo_root_accepts_a_submodule_with_its_relative_core_worktree(tmp_path):
    inner = seeded_repo(tmp_path / "inner")
    repo = seeded_repo(tmp_path / "repo")
    git(repo, "-c", "protocol.file.allow=always", "submodule", "add", "-q", str(inner), "sub")
    sub = repo / "sub"
    (sub / "deep").mkdir()

    assert (sub / ".git").is_file()
    assert adr_drift.repo_root(str(sub)) == sub.resolve()
    assert adr_drift.repo_root(str(sub / "deep")) == sub.resolve()


def _digest(repo: Path) -> dict[str, str]:
    return {
        str(p.relative_to(repo)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(repo.rglob("*"))
        if p.is_file() and ".git" not in p.relative_to(repo).parts[:1]
    }


def test_scan_is_read_only_even_with_a_dirty_tree(tmp_path, capsys):
    repo = seeded_repo(tmp_path / "repo")
    commit(repo, {"a.txt": "a"}, "feat: adopt a")
    (repo / "dirty.txt").write_text("untracked", encoding="utf-8")
    (repo / adr_path(1)).write_text(adr_text(1, body="edited"), encoding="utf-8")
    before = (_digest(repo), git(repo, "status", "--porcelain"))

    scan(capsys, repo, name="again.json")

    assert (_digest(repo), git(repo, "status", "--porcelain")) == before


def test_scan_refuses_an_output_inside_the_repository(tmp_path, capsys):
    repo = seeded_repo(tmp_path / "repo")

    code, _, err = run_cli(capsys, "scan", "--repo", str(repo), "--out", str(repo / "scan.json"))

    assert code == 2 and "inside the repository" in err
    assert not (repo / "scan.json").exists()


def test_scan_makes_no_network_connection(tmp_path, capsys, monkeypatch):
    repo = seeded_repo(tmp_path / "repo")
    commit(repo, {"a.txt": "1"}, "feat: adopt a thing (#3)")

    def refuse(*_args, **_kwargs):
        raise AssertionError("scan opened a network connection")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)

    result = scan(capsys, repo)

    assert result["examined"] == 2


def test_exit_0_for_a_clean_scan_with_findings(tmp_path, capsys):
    repo = seeded_repo(tmp_path / "repo", {adr_path(1): adr_text(1), adr_path(4): adr_text(4)})

    code, out, _ = run_cli(capsys, "scan", "--repo", str(repo), "--out", str(tmp_path / "o.json"))

    assert code == 0 and "finding(s)" in out


def test_exit_2_for_a_directory_that_is_not_a_git_repository(tmp_path, capsys):
    plain = tmp_path / "plain"
    plain.mkdir()

    scan_code = run_cli(capsys, "scan", "--repo", str(plain), "--out", str(tmp_path / "o.json"))[0]
    locate_code = run_cli(capsys, "locate", "--repo", str(plain))[0]
    missing_code = run_cli(capsys, "locate", "--repo", str(tmp_path / "absent"))[0]

    assert (scan_code, locate_code, missing_code) == (2, 2, 2)


def test_exit_2_for_bad_max_commits_and_missing_arguments(tmp_path, capsys):
    repo = seeded_repo(tmp_path / "repo")

    zero = run_cli(
        capsys, "scan", "--repo", str(repo), "--out", str(tmp_path / "o.json"), "--max-commits", "0"
    )
    with pytest.raises(SystemExit) as no_out:
        adr_drift.main(["scan", "--repo", str(repo)])
    with pytest.raises(SystemExit) as no_command:
        adr_drift.main([])

    assert zero[0] == 2 and no_out.value.code == 2 and no_command.value.code == 2


def test_exit_3_when_a_git_command_fails_or_git_is_missing(tmp_path, capsys, monkeypatch):
    repo = seeded_repo(tmp_path / "repo")
    args = ["scan", "--repo", str(repo), "--out", str(tmp_path / "o.json")]

    def fail(*_args, **_kwargs):
        raise adr_git.GitError("git log exited 128: boom")

    monkeypatch.setattr(adr_drift, "read_commits", fail)
    failed = run_cli(capsys, *args)
    monkeypatch.undo()
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    missing = run_cli(capsys, *args)

    assert failed[0] == 3 and "boom" in failed[2]
    assert missing[0] == 3 and "git is not on PATH" in missing[2]


@pytest.mark.parametrize(("command", "flag"), [("locate", "--repo"), ("scan", "--max-commits")])
def test_every_subcommand_has_help(command, flag):
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), command, "--help"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    assert proc.returncode == 0 and "usage:" in proc.stdout and flag in proc.stdout


def _process(*argv: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *argv],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def test_the_script_runs_as_a_process_and_scan_exit_codes_match_main(tmp_path):
    repo = seeded_repo(tmp_path / "repo")
    located = _process("locate", "--repo", str(repo))
    bad = _process("scan", "--repo", str(tmp_path), "--out", str(tmp_path / "o.json"))

    assert located.returncode == 0 and json.loads(located.stdout)["primary"] == ADR_DIR
    assert bad.returncode == 2 and bad.stderr.startswith("error:")


@pytest.mark.parametrize(
    "argv",
    [
        ["draft", "--scan", "x.json", "--id", "a", "--out", "d"],
        ["scan", "--repo", ".", "--out", "o.json", "--prs-json", "prs.json"],
        ["scan", "--repo", ".", "--out", "o.json", "--with-align"],
    ],
    ids=["draft", "prs-json", "with-align"],
)
def test_removed_subcommand_and_flags_exit_2(capsys, argv):
    with pytest.raises(SystemExit) as raised:
        adr_drift.main(argv)

    err = capsys.readouterr().err

    assert raised.value.code == 2
    assert "invalid choice" in err or "unrecognized arguments" in err


def test_scan_result_carries_no_decision_align_or_pr_keys(tmp_path, capsys):
    repo = seeded_repo(tmp_path / "repo")
    commit(repo, {"a.txt": "a"}, "feat: switch to uv instead of pip")

    result = scan(capsys, repo)

    assert not {"align", "prs_json", "suppressed"} & set(result)
    assert not kinds(result, "undocumented-decision")
    assert all("fix" not in finding for finding in result["findings"])
