"""Tests for the linked-worktree git mount in run_workflow_local_test.py (#6070).

act copies a linked worktree into its job container, where the ``.git`` file
names a gitdir that does not exist. The runner mounts a throwaway, writable
copy of the common git dir at the same path, so ``git rev-parse`` and
``git fetch`` work in the container without touching the host repository.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_VALIDATION_DIR = str(REPO_ROOT / "scripts" / "validation")
if _VALIDATION_DIR not in sys.path:
    sys.path.insert(0, _VALIDATION_DIR)

import pytest
import run_workflow_local_test as w

WF = ".github/workflows/x.yml"


@pytest.fixture
def trusted(monkeypatch):
    """Make git report the common dir the fake worktree's own pointers name."""

    def report(repo_root):
        return w._worktree_common_dir(Path(w._read_worktree_gitdir(repo_root))).resolve()

    monkeypatch.setattr(w, "_host_common_dir", report)


def _linked_worktree(tmp_path: Path, *, commondir: str | None = "../..") -> tuple[Path, Path, Path]:
    common = tmp_path / "main" / ".git"
    gitdir = common / "worktrees" / "feat"
    gitdir.mkdir(parents=True)
    (common / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (common / "objects" / "ab").mkdir(parents=True)
    (common / "objects" / "ab" / "cdef").write_text("obj", encoding="utf-8")
    (gitdir / "HEAD").write_text("ref: refs/heads/feat\n", encoding="utf-8")
    if commondir is not None:
        (gitdir / "commondir").write_text(commondir + "\n", encoding="utf-8")
    worktree = tmp_path / "wt"
    worktree.mkdir()
    (worktree / ".git").write_text(f"gitdir: {gitdir}\n", encoding="utf-8")
    return worktree, gitdir, common


def _mounted_copy(args: list[str]) -> Path:
    spec = args[1].removeprefix("-v ").strip("'")
    return Path(spec.rsplit(":", 1)[0])


def test_common_dir_follows_relative_commondir_file(tmp_path):
    _, gitdir, common = _linked_worktree(tmp_path)
    assert w._worktree_common_dir(gitdir) == common.resolve()


def test_common_dir_without_commondir_file_is_the_gitdir(tmp_path):
    _, gitdir, _ = _linked_worktree(tmp_path, commondir=None)
    assert w._worktree_common_dir(gitdir) == gitdir


def test_common_dir_with_blank_commondir_file_is_the_gitdir(tmp_path):
    _, gitdir, _ = _linked_worktree(tmp_path, commondir="")
    assert w._worktree_common_dir(gitdir) == gitdir


def test_mount_yields_nothing_for_normal_checkout(tmp_path):
    (tmp_path / ".git").mkdir()
    with w._worktree_git_mount(tmp_path) as args:
        assert args == []


def test_mount_yields_nothing_when_git_is_missing(tmp_path):
    with w._worktree_git_mount(tmp_path) as args:
        assert args == []


def test_mount_yields_nothing_for_unrecognised_layout(trusted, tmp_path):
    worktree, _, _ = _linked_worktree(tmp_path, commondir=None)
    with w._worktree_git_mount(worktree) as args:
        assert args == []


def test_mount_binds_a_copy_at_the_common_dir_path(trusted, tmp_path):
    worktree, _, common = _linked_worktree(tmp_path)
    with w._worktree_git_mount(worktree) as args:
        copy = _mounted_copy(args)
        assert args[0] == "--container-options"
        assert args[1].endswith(f":{common.resolve()}")
        assert copy != common.resolve()
        assert (copy / "HEAD").read_text(encoding="utf-8") == "ref: refs/heads/main\n"
        assert (copy / "worktrees" / "feat" / "commondir").is_file()
        assert (copy / "objects" / "ab" / "cdef").read_text(encoding="utf-8") == "obj"


def test_mounted_copy_is_writable_and_isolated_from_the_host(trusted, tmp_path):
    worktree, _, common = _linked_worktree(tmp_path)
    with w._worktree_git_mount(worktree) as args:
        copy = _mounted_copy(args)
        assert os.access(copy, os.W_OK)
        assert os.stat(copy / "HEAD").st_mode & 0o666 == 0o666
        (copy / "HEAD").write_text("changed\n", encoding="utf-8")
        (copy / "objects" / "ab" / "new").write_text("n", encoding="utf-8")
    assert (common / "HEAD").read_text(encoding="utf-8") == "ref: refs/heads/main\n"
    assert not (common / "objects" / "ab" / "new").exists()


def test_mounted_copy_is_removed_after_the_stage(trusted, tmp_path):
    worktree, _, _ = _linked_worktree(tmp_path)
    with w._worktree_git_mount(worktree) as args:
        copy = _mounted_copy(args)
        assert copy.is_dir()
    assert not copy.exists()


def test_mount_path_with_spaces_is_quoted(trusted, tmp_path):
    spaced = tmp_path / "my repo"
    spaced.mkdir()
    worktree, _, common = _linked_worktree(spaced)
    with w._worktree_git_mount(worktree) as args:
        assert args[1].startswith("-v '")
        assert args[1].endswith(f":{common.resolve()}'")


def test_link_or_copy_falls_back_to_copy_when_link_fails(monkeypatch, tmp_path):
    src = tmp_path / "src"
    src.write_text("x", encoding="utf-8")
    dst = tmp_path / "dst"

    def refuse(_src, _dst):
        raise OSError("cross-device")

    monkeypatch.setattr(w.os, "link", refuse)
    w._link_or_copy(str(src), str(dst))
    assert dst.read_text(encoding="utf-8") == "x"


def test_full_stage_passes_the_mount_before_the_workflow_flag(trusted, monkeypatch, tmp_path):
    worktree, _, common = _linked_worktree(tmp_path)
    calls: list[list[str]] = []

    def fake_run(cmd, *, timeout, cwd=None, env=None):
        calls.append(list(cmd))
        return 0, "", ""

    monkeypatch.setattr(w, "_run", fake_run)
    res = w._act_full_stage([WF], worktree)

    assert res.ok is True
    assert len(calls) == 1
    cmd = calls[0]
    assert cmd[:2] == ["gh", "act"]
    assert cmd[2] == "--container-options"
    assert cmd[3].endswith(f":{common.resolve()}")
    assert cmd[4:] == ["-W", WF]


def test_dry_run_stage_never_copies_git_metadata(monkeypatch, tmp_path):
    worktree, _, _ = _linked_worktree(tmp_path)
    calls: list[list[str]] = []

    def fake_run(cmd, *, timeout, cwd=None, env=None):
        calls.append(list(cmd))
        return 0, "", ""

    def boom(_repo_root):
        raise AssertionError("dry run must not copy git metadata")

    monkeypatch.setattr(w, "_run", fake_run)
    monkeypatch.setattr(w, "_worktree_git_mount", boom)
    w._act_dryrun_stage([WF], worktree)

    assert calls == [["gh", "act", "-n", "-W", WF]]


def test_full_stage_adds_no_mount_for_normal_checkout(monkeypatch, tmp_path):
    (tmp_path / ".git").mkdir()
    calls: list[list[str]] = []

    def fake_run(cmd, *, timeout, cwd=None, env=None):
        calls.append(list(cmd))
        return 0, "", ""

    monkeypatch.setattr(w, "_run", fake_run)
    w._act_full_stage([WF], tmp_path)

    assert calls == [["gh", "act", "-W", WF]]


def test_mount_copy_matches_a_real_linked_worktree(tmp_path):
    main = tmp_path / "main"
    main.mkdir()
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@example.com"]
    subprocess.run([*git, "init", "-q", str(main)], check=True)
    subprocess.run([*git, "-C", str(main), "commit", "-q", "--allow-empty", "-m", "x"], check=True)
    worktree = tmp_path / "wt"
    subprocess.run(
        [*git, "-C", str(main), "worktree", "add", "-q", "-b", "b", str(worktree)], check=True
    )

    with w._worktree_git_mount(worktree) as args:
        copy = _mounted_copy(args)
        assert args[1].endswith(f":{(main / '.git').resolve()}")
        head = subprocess.run(
            ["git", "--git-dir", str(copy / "worktrees" / "wt"), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    expected = subprocess.run(
        ["git", "-C", str(worktree), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert head == expected


def test_crafted_commondir_outside_the_reported_common_dir_is_refused(monkeypatch, tmp_path):
    worktree, gitdir, _ = _linked_worktree(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    (elsewhere / "worktrees").mkdir(parents=True)
    (gitdir / "commondir").write_text(str(elsewhere) + "\n", encoding="utf-8")
    monkeypatch.setattr(w, "_host_common_dir", lambda _root: (tmp_path / "main" / ".git").resolve())

    with pytest.raises(w.UntrustedGitDirError, match="does not match"):
        with w._worktree_git_mount(worktree):
            pass


def test_unresolvable_host_common_dir_is_refused(monkeypatch, tmp_path):
    worktree, _, _ = _linked_worktree(tmp_path)
    monkeypatch.setattr(w, "_host_common_dir", lambda _root: None)

    with pytest.raises(w.UntrustedGitDirError, match="unresolved"):
        with w._worktree_git_mount(worktree):
            pass


def test_full_stage_fails_with_the_refusal_and_never_runs_act(monkeypatch, tmp_path):
    worktree, gitdir, _ = _linked_worktree(tmp_path)
    (gitdir / "commondir").write_text(str(tmp_path) + "\n", encoding="utf-8")
    monkeypatch.setattr(w, "_host_common_dir", lambda _root: None)

    def no_act(*_a, **_k):
        raise AssertionError("act must not run")

    monkeypatch.setattr(w, "_run", no_act)
    res = w._act_full_stage([WF], worktree)

    assert res.ok is False
    assert "refusing to mount" in res.detail


def test_host_common_dir_reads_git_and_strips_git_env(monkeypatch, tmp_path):
    seen = {}

    def fake_run(cmd, *, timeout, cwd=None, env=None):
        seen["env"] = env
        return 0, f"{tmp_path}\n", ""

    monkeypatch.setenv("GIT_DIR", "/wrong")
    monkeypatch.setattr(w, "_run", fake_run)

    assert w._host_common_dir(tmp_path) == tmp_path.resolve()
    assert "GIT_DIR" not in seen["env"]


def test_host_common_dir_is_none_when_git_fails(monkeypatch, tmp_path):
    monkeypatch.setattr(w, "_run", lambda *_a, **_k: (128, "", "fatal"))
    assert w._host_common_dir(tmp_path) is None


def test_real_worktree_passes_the_trust_check(tmp_path):
    main = tmp_path / "main"
    main.mkdir()
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@example.com"]
    subprocess.run([*git, "init", "-q", str(main)], check=True)
    subprocess.run([*git, "-C", str(main), "commit", "-q", "--allow-empty", "-m", "x"], check=True)
    worktree = tmp_path / "wt"
    subprocess.run(
        [*git, "-C", str(main), "worktree", "add", "-q", "-b", "b", str(worktree)], check=True
    )
    with w._worktree_git_mount(worktree) as args:
        assert args[0] == "--container-options"
