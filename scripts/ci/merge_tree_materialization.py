"""Exact-tree materialization and isolated Git helpers for merge ratchets."""

from __future__ import annotations

import errno
import os
import shutil
import stat
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

from scripts.cli_exec import resolve_executable

_CLEANUP_RETRY_DELAYS = (0.1, 0.2, 0.4, 0.8, 1.6)
_TRANSIENT_CLEANUP_ERRNOS = frozenset({errno.EBUSY, errno.ENOTEMPTY})


def _make_writable_and_retry(
    function: Callable[[str], object], path: str, exc: BaseException
) -> None:
    """Clear a Windows read-only attribute, then retry the failed removal."""
    if not isinstance(exc, PermissionError):
        raise exc
    try:
        os.chmod(path, os.stat(path).st_mode | stat.S_IWRITE)
        function(path)
    except FileNotFoundError:
        return


def run_git(
    cwd: Path,
    *argv: str,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run Git without a shell, returning rc 127 when launch itself fails."""
    command = ["git", "-C", str(cwd), *argv]
    try:
        command[0] = resolve_executable("git", env=env)
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            env=env,
        )
    except OSError as exc:
        return subprocess.CompletedProcess(
            command,
            127,
            "",
            f"{type(exc).__name__}: {exc}",
        )


def isolated_git_environment(isolated_home: Path) -> dict[str, str]:
    """Retain platform process state while replacing user-controlled Git state."""
    isolated_home.mkdir(parents=True, exist_ok=True)
    xdg_home = isolated_home / "xdg"
    gnupg_home = isolated_home / "gnupg"
    template_dir = isolated_home / "templates"
    for directory in (xdg_home, gnupg_home, template_dir):
        directory.mkdir()
    global_config = isolated_home / "gitconfig"
    global_config.write_text("", encoding="utf-8")

    env = os.environ.copy()
    isolated_names = {"GNUPGHOME", "HOME", "LEFTHOOK", "USERPROFILE", "XDG_CONFIG_HOME"}
    for name in tuple(env):
        normalized = name.upper()
        if normalized.startswith("GIT_") or normalized in isolated_names:
            env.pop(name)
    env.update(
        {
            "GIT_ATTR_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": str(global_config),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TEMPLATE_DIR": str(template_dir),
            "GNUPGHOME": str(gnupg_home),
            "HOME": str(isolated_home),
            "USERPROFILE": str(isolated_home),
            "XDG_CONFIG_HOME": str(xdg_home),
        }
    )
    return env


def remove_tree(path: Path, label: str) -> str | None:
    """Remove one temporary tree, returning a diagnostic instead of hiding failure."""
    for delay in (*_CLEANUP_RETRY_DELAYS, None):
        try:
            shutil.rmtree(path, onexc=_make_writable_and_retry)
            return None
        except FileNotFoundError:
            return None
        except PermissionError as exc:
            if delay is None:
                return f"{label} cleanup failed: {type(exc).__name__}: {exc}"
            time.sleep(delay)
        except OSError as exc:
            if exc.errno in _TRANSIENT_CLEANUP_ERRNOS and delay is not None:
                time.sleep(delay)
                continue
            return f"{label} cleanup failed: {type(exc).__name__}: {exc}"
    raise AssertionError("cleanup retry loop exhausted without returning")


def _cleanup_materialization(index_path: Path, isolated_home: Path) -> bool:
    success = True
    try:
        index_path.unlink(missing_ok=True)
    except OSError as exc:
        print(
            f"temporary index cleanup failed: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        success = False
    cleanup_error = remove_tree(isolated_home, "materialization Git home")
    if cleanup_error:
        print(cleanup_error, file=sys.stderr)
        success = False
    return success


def _checkout_tree(
    repo_root: Path,
    tree_oid: str,
    destination: Path,
    env: dict[str, str],
) -> bool:
    read_tree = run_git(repo_root, "read-tree", tree_oid, env=env)
    if read_tree.returncode != 0:
        print(f"git read-tree failed: {read_tree.stderr}", file=sys.stderr)
        return False
    prefix = f"{destination.resolve().as_posix()}/"
    checkout = run_git(
        repo_root,
        "-c",
        "core.symlinks=true",
        "checkout-index",
        "--all",
        "--force",
        f"--prefix={prefix}",
        env=env,
    )
    if checkout.returncode != 0:
        print(f"git checkout-index failed: {checkout.stderr}", file=sys.stderr)
        return False
    return True


def materialize_tree(repo_root: Path, tree_oid: str, destination: Path) -> bool:
    """Check out every tree entry through a temporary index, ignoring export-ignore."""
    destination.mkdir(parents=True, exist_ok=True)
    isolated_home = destination.parent / f".{destination.name}-materialize-home"
    index_path = destination.parent / f".{destination.name}-materialize-index"
    setup_error = remove_tree(isolated_home, "stale materialization Git home")
    if setup_error:
        print(setup_error, file=sys.stderr)
        return False

    materialized = False
    cleaned = False
    try:
        env = isolated_git_environment(isolated_home)
        env["GIT_INDEX_FILE"] = str(index_path)
        materialized = _checkout_tree(repo_root, tree_oid, destination, env)
    finally:
        cleaned = _cleanup_materialization(index_path, isolated_home)
    if not materialized:
        print("merged-tree materialization did not complete", file=sys.stderr)
    return materialized and cleaned


def _initialize_repo(scratch: Path, env: dict[str, str]) -> bool:
    commands = (
        ("init", "-q", "-b", "main", str(scratch)),
        ("config", "user.email", "ci@example.com"),
        ("config", "user.name", "ci"),
        ("add", "-A"),
        ("commit", "-qm", "merge-tree snapshot"),
    )
    for index, argv in enumerate(commands):
        cwd = scratch if index else scratch.parent
        proc = run_git(cwd, *argv, env=env)
        if proc.returncode != 0:
            print(f"git scratch init failed: {proc.stderr}", file=sys.stderr)
            return False
    return True


def init_scratch_repo(scratch: Path) -> bool:
    """Commit the materialized tree in a Git environment isolated from user state."""
    isolated_home = scratch.parent / f".{scratch.name}-git-home"
    setup_error = remove_tree(isolated_home, "stale scratch Git home")
    if setup_error:
        print(setup_error, file=sys.stderr)
        return False

    initialized = False
    cleanup_error: str | None = None
    try:
        env = isolated_git_environment(isolated_home)
        initialized = _initialize_repo(scratch, env)
    finally:
        cleanup_error = remove_tree(isolated_home, "scratch Git home")
        if cleanup_error:
            print(cleanup_error, file=sys.stderr)
    if not initialized:
        print("scratch Git initialization did not complete", file=sys.stderr)
    return initialized and cleanup_error is None
