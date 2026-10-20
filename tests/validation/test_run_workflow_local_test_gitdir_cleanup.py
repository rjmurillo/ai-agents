"""Tests for removing the git dir copy the act job leaves behind (#6792).

The act job runs as uid 1001. Files it creates in the mounted copy of a linked
worktree's git dir belong to a user the host cannot delete, so the copy leaked
to the temp dir with the repository config. A root container in the act runner
image removes it; when that fails, the warning names the exact command.
"""

from __future__ import annotations

import os
import shlex
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_VALIDATION_DIR = str(REPO_ROOT / "scripts" / "validation")
if _VALIDATION_DIR not in sys.path:
    sys.path.insert(0, _VALIDATION_DIR)

import pytest
import run_workflow_local_test as w

from tests.validation.test_run_workflow_local_test_worktree_mount import _linked_worktree


@pytest.fixture
def trusted(monkeypatch):
    """Make git report the common dir the fake worktree's own pointers name."""

    def report(repo_root):
        return w._worktree_common_dir(Path(w._read_worktree_gitdir(repo_root))).resolve()

    monkeypatch.setattr(w, "_host_common_dir", report)


# --- Files the act container user made (#6792) ---------------------------


def _undeletable_copy(tmp_path: Path, monkeypatch, name: str = "act-gitdir-t1") -> Path:
    """A copy whose subdirectory the host cannot write, as a uid 1001 dir would be."""
    root = tmp_path / name
    foreign = root / "git" / "worktrees" / "abc"
    foreign.mkdir(parents=True)
    (foreign / "index").write_text("x", encoding="utf-8")
    foreign.chmod(0o500)
    monkeypatch.setattr(w, "_make_tree_writable", lambda _root: None)
    return root


def _mounted_root(cmd: list[str]) -> Path:
    mount = next(arg for arg in cmd if arg.endswith(":/cleanup"))
    return Path(mount.removesuffix(":/cleanup"))


def _fake_root_cleanup(calls):
    """Stand in for ``docker run --user 0 ... find /cleanup -delete``."""

    def run(cmd, *, timeout, cwd=None, env=None):
        calls.append((list(cmd), timeout))
        root = _mounted_root(cmd)
        for current, dirs, _files in os.walk(root):
            Path(current).chmod(0o700)
            for name in dirs:
                Path(current, name).chmod(0o700)
        for child in root.iterdir():
            shutil.rmtree(child)
        return 0, "", ""

    return run


@pytest.mark.skipif(os.geteuid() == 0, reason="root can delete a read-only directory")
def test_remove_copy_empties_a_tree_the_host_user_cannot_write_through_a_root_container(
    monkeypatch, tmp_path
):
    root = _undeletable_copy(tmp_path, monkeypatch)
    calls: list = []
    monkeypatch.setattr(w, "_run", _fake_root_cleanup(calls))

    assert w._remove_copy(root) is None

    assert not root.exists()
    assert len(calls) == 1
    cmd, timeout = calls[0]
    assert cmd == w._container_cleanup_command(root)
    assert timeout == w._CLEANUP_TIMEOUT
    assert cmd[:3] == ["docker", "run", "--rm"]
    assert "--pull=never" in cmd
    assert cmd[cmd.index("--user") + 1] == "0"
    assert cmd[-5:] == ["find", "/cleanup", "-mindepth", "1", "-delete"]


@pytest.mark.skipif(os.geteuid() == 0, reason="root can delete a read-only directory")
def test_remove_copy_names_the_exact_command_when_the_container_cleanup_fails(
    monkeypatch, tmp_path
):
    root = _undeletable_copy(tmp_path, monkeypatch)
    monkeypatch.setattr(w, "_run", lambda *_a, **_k: (1, "", "docker: image not found"))

    message = w._remove_copy(root)

    assert message is not None
    assert root.exists()
    assert shlex.join(w._container_cleanup_command(root)) in message
    assert f"&& rmdir {shlex.quote(str(root))}" in message
    assert str(root) in message
    assert "Permission denied" in message


def test_remove_copy_reports_a_missing_docker_with_the_same_command(monkeypatch, tmp_path):
    root = tmp_path / "act-gitdir-t2"
    root.mkdir()
    monkeypatch.setattr(
        w.shutil, "rmtree", lambda _p: (_ for _ in ()).throw(PermissionError("denied"))
    )
    monkeypatch.setattr(w, "_run", lambda *_a, **_k: (-1, "", "command not found: docker"))

    message = w._remove_copy(root)

    assert message is not None
    assert shlex.join(w._container_cleanup_command(root)) in message


def test_remove_copy_does_not_start_a_root_container_for_a_foreign_directory(monkeypatch, tmp_path):
    # Safety: a root process is only handed a directory this module created.
    root = tmp_path / "copy"
    root.mkdir()
    monkeypatch.setattr(
        w.shutil, "rmtree", lambda _p: (_ for _ in ()).throw(PermissionError("denied"))
    )
    monkeypatch.setattr(w, "_run", lambda *_a, **_k: pytest.fail("must not run docker"))

    message = w._remove_copy(root)

    assert message is not None
    assert "Remove it with:" in message


def test_remove_copy_does_not_start_a_root_container_for_a_symlink(monkeypatch, tmp_path):
    target = tmp_path / "elsewhere"
    target.mkdir()
    link = tmp_path / "act-gitdir-link"
    link.symlink_to(target)
    monkeypatch.setattr(
        w.shutil, "rmtree", lambda _p: (_ for _ in ()).throw(PermissionError("denied"))
    )
    monkeypatch.setattr(w, "_run", lambda *_a, **_k: pytest.fail("must not run docker"))

    assert w._remove_copy_as_container_root(link) is False
    assert target.exists()


def test_remove_copy_skips_the_container_for_an_error_that_is_not_a_permission_error(
    monkeypatch, tmp_path
):
    # Edge: a busy mount is not fixed by root, so no container starts.
    root = tmp_path / "act-gitdir-t3"
    root.mkdir()
    monkeypatch.setattr(
        w.shutil, "rmtree", lambda _p: (_ for _ in ()).throw(OSError(16, "Device or resource busy"))
    )
    monkeypatch.setattr(w, "_run", lambda *_a, **_k: pytest.fail("must not run docker"))

    message = w._remove_copy(root)

    assert message is not None
    assert "busy" in message


def test_remove_copy_removes_nothing_through_a_container_when_the_host_can_delete(
    monkeypatch, tmp_path
):
    root = tmp_path / "act-gitdir-t4"
    (root / "git").mkdir(parents=True)
    monkeypatch.setattr(w, "_run", lambda *_a, **_k: pytest.fail("must not run docker"))

    assert w._remove_copy(root) is None
    assert not root.exists()


def test_cleanup_image_is_an_act_runner_image():
    # Conformance: the cleanup image is one the repository .actrc maps a runner to.
    actrc = (REPO_ROOT / ".actrc").read_text(encoding="utf-8")
    images = {
        line.split("=", 1)[1].strip()
        for line in actrc.splitlines()
        if line.startswith("-P ubuntu") and "=" in line
    }
    assert w._ACT_CLEANUP_IMAGE in images


def test_mount_leaves_no_copy_behind_when_the_job_made_files_the_host_cannot_delete(
    trusted, monkeypatch, tmp_path
):
    worktree, _, _ = _linked_worktree(tmp_path)
    calls: list = []
    real_rmtree = shutil.rmtree

    def deny_until_cleaned(path, *a, **k):
        if not calls:
            raise PermissionError(13, "Permission denied", str(path))
        return real_rmtree(path, *a, **k)

    def run(cmd, *, timeout, cwd=None, env=None):
        calls.append(list(cmd))
        shutil.rmtree(_mounted_root(cmd) / "git")
        return 0, "", ""

    monkeypatch.setattr(w.shutil, "rmtree", deny_until_cleaned)
    monkeypatch.setattr(w, "_run", run)

    with w._worktree_git_mount(worktree) as args:
        copy_root = Path(shlex.split(args[1])[1].split(":", 1)[0]).parent

    assert len(calls) == 1
    assert not copy_root.exists()
