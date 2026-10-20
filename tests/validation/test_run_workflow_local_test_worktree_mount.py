"""Tests for the linked-worktree git mount in run_workflow_local_test.py (#6070).

act copies a linked worktree into its job container, where the ``.git`` file
names a gitdir that does not exist. The runner mounts a throwaway, writable
copy of the common git dir at the same path, so ``git rev-parse`` and
``git fetch`` work in the container without touching the host repository.
"""

from __future__ import annotations

import os
import shlex
import shutil
import socket
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
    (gitdir / "gitdir").write_text(f"{worktree / '.git'}\n", encoding="utf-8")
    return worktree, gitdir, common


def _mounted_copy(args: list[str]) -> Path:
    spec = shlex.split(args[1])[1]
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


def test_mount_yields_nothing_for_unrecognised_layout(trusted, tmp_path):
    worktree, _, _ = _linked_worktree(tmp_path, commondir=None)
    with w._worktree_git_mount(worktree) as args:
        assert args == []


def test_mount_binds_a_copy_at_the_common_dir_path(trusted, tmp_path):
    worktree, _, common = _linked_worktree(tmp_path)
    with w._worktree_git_mount(worktree) as args:
        copy = _mounted_copy(args)
        assert args[0] == "--container-options"
        assert shlex.split(args[1])[1].endswith(f":{common.resolve()}")
        assert copy != common.resolve()
        assert (copy / "HEAD").read_text(encoding="utf-8") == "ref: refs/heads/main\n"
        assert (copy / "worktrees" / "feat" / "commondir").is_file()
        assert (copy / "objects" / "info" / "alternates").is_file()


def test_mounted_copy_is_writable_and_isolated_from_the_host(trusted, tmp_path):
    worktree, _, common = _linked_worktree(tmp_path)
    with w._worktree_git_mount(worktree) as args:
        copy = _mounted_copy(args)
        assert os.access(copy, os.W_OK)
        assert os.stat(copy / "HEAD").st_mode & 0o666 == 0o666
        (copy / "HEAD").write_text("changed\n", encoding="utf-8")
        (copy / "objects" / "new").write_text("n", encoding="utf-8")
    assert (common / "HEAD").read_text(encoding="utf-8") == "ref: refs/heads/main\n"
    assert not (common / "objects" / "new").exists()


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
        assert f":{common.resolve()}'" in args[1]
        assert shlex.split(args[1])[1].endswith(f":{common.resolve()}")


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
    assert shlex.split(cmd[3])[1].endswith(f":{common.resolve()}")
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
        assert shlex.split(args[1])[1].endswith(f":{(main / '.git').resolve()}")
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


def test_host_common_dir_that_disagrees_with_the_pointer_is_refused(monkeypatch, tmp_path):
    worktree, _, _ = _linked_worktree(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.setattr(w, "_host_common_dir", lambda _root: elsewhere.resolve())

    with pytest.raises(w.UntrustedGitDirError, match="does not match"):
        with w._worktree_git_mount(worktree):
            pass


def test_crafted_commondir_is_an_unrecognised_layout_and_mounts_nothing(trusted, tmp_path):
    worktree, gitdir, _ = _linked_worktree(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    (elsewhere / "worktrees").mkdir(parents=True)
    (gitdir / "commondir").write_text(str(elsewhere) + "\n", encoding="utf-8")

    with w._worktree_git_mount(worktree) as args:
        assert args == []


def test_unrecognised_layout_without_a_backlink_still_yields_no_mount(trusted, tmp_path):
    worktree, gitdir, _ = _linked_worktree(tmp_path, commondir=None)
    (gitdir / "gitdir").unlink()

    with w._worktree_git_mount(worktree) as args:
        assert args == []


def test_relative_backlink_resolves_against_the_admin_dir(trusted, tmp_path):
    worktree, gitdir, _ = _linked_worktree(tmp_path)
    (gitdir / "gitdir").write_text(
        os.path.relpath(worktree / ".git", gitdir) + "\n", encoding="utf-8"
    )

    with w._worktree_git_mount(worktree) as args:
        assert args[0] == "--container-options"


def test_full_stage_fails_with_the_refusal_and_never_runs_act(monkeypatch, tmp_path):
    worktree, _, _ = _linked_worktree(tmp_path)
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


def test_objects_are_shared_read_only_and_never_linked(trusted, tmp_path):
    worktree, _, common = _linked_worktree(tmp_path)
    obj = common / "objects" / "ab" / "cdef"
    obj.chmod(0o444)
    with w._worktree_git_mount(worktree) as args:
        copy = _mounted_copy(args)
        mounts = shlex.split(args[1])
        assert f"{common.resolve() / 'objects'}:{w._HOST_OBJECTS_MOUNT}:ro" in mounts
        alternates = (copy / "objects" / "info" / "alternates").read_text(encoding="utf-8")
        assert alternates.strip() == w._HOST_OBJECTS_MOUNT
        assert not (copy / "objects" / "ab").exists()
    assert os.stat(obj).st_mode & 0o777 == 0o444


def test_hooks_are_not_copied(trusted, tmp_path):
    worktree, _, common = _linked_worktree(tmp_path)
    (common / "hooks").mkdir()
    (common / "hooks" / "pre-push").write_text("#!/bin/sh\n", encoding="utf-8")
    with w._worktree_git_mount(worktree) as args:
        assert not (_mounted_copy(args) / "hooks").exists()


def test_forged_backlink_is_refused(trusted, tmp_path):
    worktree, gitdir, _ = _linked_worktree(tmp_path)
    (gitdir / "gitdir").write_text(str(tmp_path / "other" / ".git") + "\n", encoding="utf-8")

    with pytest.raises(w.UntrustedGitDirError, match="does not point back"):
        with w._worktree_git_mount(worktree):
            pass


def test_missing_backlink_is_refused(trusted, tmp_path):
    worktree, gitdir, _ = _linked_worktree(tmp_path)
    (gitdir / "gitdir").unlink()

    with pytest.raises(w.UntrustedGitDirError, match="does not point back"):
        with w._worktree_git_mount(worktree):
            pass


def test_remove_copy_retries_after_making_the_tree_writable(tmp_path):
    root = tmp_path / "copy"
    locked = root / "objects" / "ab"
    locked.mkdir(parents=True)
    (locked / "obj").write_text("x", encoding="utf-8")
    locked.chmod(0o500)
    root.chmod(0o500)

    assert w._remove_copy(root) is None
    assert not root.exists()


def test_remove_copy_reports_the_leftover_path_without_raising(monkeypatch, tmp_path):
    root = tmp_path / "copy"
    root.mkdir()

    def refuse(_path):
        raise PermissionError("root-owned")

    monkeypatch.setattr(w.shutil, "rmtree", refuse)
    message = w._remove_copy(root)

    assert message is not None
    assert str(root) in message
    assert "root-owned" in message


def test_cleanup_failure_after_a_clean_stage_is_a_failed_stage_naming_the_path(
    trusted, monkeypatch, tmp_path
):
    worktree, _, _ = _linked_worktree(tmp_path)
    monkeypatch.setattr(w, "_run", lambda *_a, **_k: (0, "", ""))
    real_remove = w._remove_copy

    def fake_remove(root):
        real_remove(root)
        return f"leftover {root}"

    monkeypatch.setattr(w, "_remove_copy", fake_remove)

    res = w._act_full_stage([WF], worktree)

    assert res.ok is False
    assert "leftover" in res.detail
    assert "act-gitdir-" in res.detail


def test_cleanup_failure_does_not_mask_a_body_exception(trusted, monkeypatch, tmp_path, capsys):
    worktree, _, _ = _linked_worktree(tmp_path)
    real_remove = w._remove_copy

    def fake_remove(root):
        real_remove(root)
        return f"leftover {root}"

    monkeypatch.setattr(w, "_remove_copy", fake_remove)

    with pytest.raises(ValueError, match="boom"):
        with w._worktree_git_mount(worktree):
            raise ValueError("boom")

    assert "WARNING: leftover" in capsys.readouterr().err


@pytest.mark.skipif(
    os.name == "nt" or not hasattr(os, "mkfifo") or not hasattr(socket, "AF_UNIX"),
    reason="needs POSIX FIFOs and Unix sockets",
)
def test_sockets_and_fifos_in_the_git_dir_are_skipped(trusted, monkeypatch, tmp_path):
    worktree, _, common = _linked_worktree(tmp_path)
    os.mkfifo(common / "fsmonitor.fifo")
    # AF_UNIX paths top out near 108 bytes; bind by a relative name from inside the dir.
    monkeypatch.chdir(common)
    with socket.socket(socket.AF_UNIX) as sock:
        sock.bind("fsmonitor.sock")
        monkeypatch.chdir(tmp_path)
        with w._worktree_git_mount(worktree) as args:
            copy = _mounted_copy(args)
            assert not (copy / "fsmonitor.fifo").exists()
            assert not (copy / "fsmonitor.sock").exists()
            assert (copy / "HEAD").is_file()


def test_special_file_check_ignores_a_missing_path(tmp_path):
    assert w._is_special_file(tmp_path / "missing") is False


def test_copy_error_becomes_a_failed_stage_and_removes_the_copy(trusted, monkeypatch, tmp_path):
    worktree, _, _ = _linked_worktree(tmp_path)
    seen = {}

    def broken(src, dst, **_kw):
        seen["dst"] = dst
        raise shutil.Error("cannot copy")

    monkeypatch.setattr(w.shutil, "copytree", broken)
    monkeypatch.setattr(w, "_run", lambda *_a, **_k: pytest.fail("act must not run"))
    res = w._act_full_stage([WF], worktree)

    assert res.ok is False
    assert "could not copy the git metadata" in res.detail
    assert not Path(seen["dst"]).parent.exists()


def test_colon_in_the_common_dir_is_refused_up_front(monkeypatch, tmp_path):
    worktree, gitdir, common = _linked_worktree(tmp_path / "a:b")
    monkeypatch.setattr(w, "_host_common_dir", lambda _root: common.resolve())

    with pytest.raises(w.GitMountError, match="move the repository"):
        with w._worktree_git_mount(worktree):
            pass


def test_colon_in_the_temp_root_is_refused(trusted, monkeypatch, tmp_path):
    worktree, _, _ = _linked_worktree(tmp_path)
    weird = tmp_path / "t:mp"
    weird.mkdir()
    monkeypatch.setattr(w.tempfile, "tempdir", str(weird))

    with pytest.raises(w.GitMountError, match="set TMPDIR"):
        with w._worktree_git_mount(worktree):
            pass
    assert list(weird.iterdir()) == []


def test_windows_yields_no_mount_instead_of_rejecting_drive_paths(monkeypatch, tmp_path):
    worktree, _, _ = _linked_worktree(tmp_path)
    monkeypatch.setattr(w, "_is_windows", lambda: True)
    monkeypatch.setattr(w, "_host_common_dir", lambda _root: pytest.fail("no git call on Windows"))

    with w._worktree_git_mount(worktree) as args:
        assert args == []


def test_is_windows_reads_os_name(monkeypatch):
    monkeypatch.setattr(w.os, "name", "nt")
    assert w._is_windows() is True
    monkeypatch.setattr(w.os, "name", "posix")
    assert w._is_windows() is False


def test_host_common_dir_resolves_a_relative_answer_from_older_git(monkeypatch, tmp_path):
    seen = {}

    def fake_run(cmd, *, timeout, cwd=None, env=None):
        seen["cmd"] = cmd
        return 0, "../main/.git\n", ""

    monkeypatch.setattr(w, "_run", fake_run)
    repo = tmp_path / "wt"
    repo.mkdir()

    assert w._host_common_dir(repo) == (tmp_path / "main" / ".git").resolve()
    assert "--path-format=absolute" not in seen["cmd"]
