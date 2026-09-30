"""Tests for the linked-worktree git mount in run_workflow_local_test.py (#6070).

act copies a linked worktree into its job container, where the ``.git`` file
names a gitdir that does not exist. The runner mounts the common git dir
read-only so ``git rev-parse`` works inside the container.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_VALIDATION_DIR = str(REPO_ROOT / "scripts" / "validation")
if _VALIDATION_DIR not in sys.path:
    sys.path.insert(0, _VALIDATION_DIR)

import run_workflow_local_test as w

WF = ".github/workflows/x.yml"


def _linked_worktree(tmp_path: Path, *, commondir: str | None) -> tuple[Path, Path, Path]:
    common = tmp_path / "main" / ".git"
    gitdir = common / "worktrees" / "feat"
    gitdir.mkdir(parents=True)
    if commondir is not None:
        (gitdir / "commondir").write_text(commondir + "\n", encoding="utf-8")
    worktree = tmp_path / "wt"
    worktree.mkdir()
    (worktree / ".git").write_text(f"gitdir: {gitdir}\n", encoding="utf-8")
    return worktree, gitdir, common


def test_common_dir_follows_relative_commondir_file(tmp_path):
    _, gitdir, common = _linked_worktree(tmp_path, commondir="../..")
    assert w._worktree_common_dir(gitdir) == common.resolve()


def test_common_dir_without_commondir_file_is_the_gitdir(tmp_path):
    _, gitdir, _ = _linked_worktree(tmp_path, commondir=None)
    assert w._worktree_common_dir(gitdir) == gitdir


def test_common_dir_with_blank_commondir_file_is_the_gitdir(tmp_path):
    _, gitdir, _ = _linked_worktree(tmp_path, commondir="")
    assert w._worktree_common_dir(gitdir) == gitdir


def test_mount_args_empty_for_normal_checkout(tmp_path):
    (tmp_path / ".git").mkdir()
    assert w._worktree_mount_args(tmp_path) == []


def test_mount_args_empty_when_git_is_missing(tmp_path):
    assert w._worktree_mount_args(tmp_path) == []


def test_mount_args_mount_common_dir_read_only(tmp_path):
    worktree, _, common = _linked_worktree(tmp_path, commondir="../..")
    resolved = common.resolve()
    assert w._worktree_mount_args(worktree) == [
        "--container-options",
        f"-v {resolved}:{resolved}:ro",
    ]


def test_mount_args_quote_paths_with_spaces(tmp_path):
    spaced = tmp_path / "my repo"
    spaced.mkdir()
    worktree, _, common = _linked_worktree(spaced, commondir="../..")
    resolved = common.resolve()
    assert w._worktree_mount_args(worktree) == [
        "--container-options",
        f"-v '{resolved}:{resolved}:ro'",
    ]


def test_act_stage_passes_mount_before_workflow_flag(monkeypatch, tmp_path):
    worktree, _, common = _linked_worktree(tmp_path, commondir="../..")
    calls: list[list[str]] = []

    def fake_run(cmd, *, timeout, cwd=None, env=None):
        calls.append(list(cmd))
        return 0, "", ""

    monkeypatch.setattr(w, "_run", fake_run)
    res = w._act_full_stage([WF], worktree)

    resolved = common.resolve()
    assert res.ok is True
    assert calls == [
        ["gh", "act", "--container-options", f"-v {resolved}:{resolved}:ro", "-W", WF]
    ]


def test_act_stage_adds_no_mount_for_normal_checkout(monkeypatch, tmp_path):
    (tmp_path / ".git").mkdir()
    calls: list[list[str]] = []

    def fake_run(cmd, *, timeout, cwd=None, env=None):
        calls.append(list(cmd))
        return 0, "", ""

    monkeypatch.setattr(w, "_run", fake_run)
    w._act_dryrun_stage([WF], tmp_path)

    assert calls == [["gh", "act", "-n", "-W", WF]]


def test_mount_target_matches_a_real_linked_worktree(tmp_path):
    main = tmp_path / "main"
    main.mkdir()
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@example.com"]
    subprocess.run([*git, "init", "-q", str(main)], check=True)
    subprocess.run([*git, "-C", str(main), "commit", "-q", "--allow-empty", "-m", "x"], check=True)
    worktree = tmp_path / "wt"
    subprocess.run(
        [*git, "-C", str(main), "worktree", "add", "-q", "-b", "b", str(worktree)], check=True
    )

    args = w._worktree_mount_args(worktree)

    expected = (main / ".git").resolve()
    assert args == ["--container-options", f"-v {expected}:{expected}:ro"]
