"""Exact-tree materialization and isolated Git helpers for merge ratchets."""

from __future__ import annotations

import errno
import os
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from scripts.cli_exec import resolve_executable

_CLEANUP_RETRY_DELAYS = (0.1, 0.2, 0.4, 0.8, 1.6)
_TRANSIENT_CLEANUP_ERRNOS = frozenset({errno.EBUSY, errno.ENOTEMPTY})

# Scratch prefixes this package creates under the system temp dir. The sweep
# touches only directories whose names start with one of these.
SCRATCH_PREFIXES = ("merge-tree-ratchet-", "base-derived-ratchet-")
# Longer than the 30m cap on the longest pre-push job in lefthook.yml, so a
# live run on another worktree is never swept.
STALE_SCRATCH_AGE_SECONDS = 3600
_TERMINATION_SIGNALS = tuple(
    getattr(signal, name) for name in ("SIGTERM", "SIGHUP") if hasattr(signal, name)
)


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
    # `--force` is load bearing, not noise (issue #5539). The materialized tree
    # carries its own `.gitignore`, and without `--force` that file decides what
    # enters the snapshot, so the scratch repository the ratchets measure is the
    # merged tree minus whatever the merged tree chose to hide. A branch could
    # then shrink what the gate can see by editing the one file the gate has no
    # reason to trust. Measured on `main`: `git ls-files -i -c
    # --exclude-standard` reports 47 tracked-but-ignored paths, none of them
    # `.py`, so no counter in `merge_tree_ratchet_registry.py` undercounts
    # today. The invariant is what is being fixed; the first Markdown, YAML, or
    # whole-tree counter added to that registry is what would have paid for it.
    commands = (
        ("init", "-q", "-b", "main", str(scratch)),
        ("config", "user.email", "ci@example.com"),
        ("config", "user.name", "ci"),
        ("add", "-A", "--force"),
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


def sweep_stale_scratch(
    prefixes: tuple[str, ...] = SCRATCH_PREFIXES,
    max_age_seconds: float = STALE_SCRATCH_AGE_SECONDS,
    temp_root: Path | None = None,
) -> int:
    """Remove scratch trees left behind by earlier killed runs. Returns the count removed.

    A path qualifies only when it is a real directory (not a symlink), its name
    starts with one of ``prefixes``, the current user owns it, and its mtime is
    older than ``max_age_seconds``. Anything else is left alone. A removal that
    fails is reported on stderr and skipped: a sweep must never fail a ratchet.
    """
    root = temp_root if temp_root is not None else Path(tempfile.gettempdir())
    uid = os.getuid() if hasattr(os, "getuid") else None
    cutoff = time.time() - max_age_seconds
    removed = 0
    try:
        entries = list(root.iterdir())
    except OSError as exc:
        sys.stderr.write(f"scratch sweep skipped: {type(exc).__name__}: {exc}\n")
        return 0
    for entry in entries:
        if not entry.name.startswith(prefixes):
            continue
        try:
            info = entry.lstat()
        except OSError:
            continue
        if not stat.S_ISDIR(info.st_mode) or info.st_mtime >= cutoff:
            continue
        if uid is not None and info.st_uid != uid:
            continue
        error = remove_tree(entry, "stale ratchet scratch")
        if error:
            sys.stderr.write(f"{error}\n")
        else:
            removed += 1
    return removed


def _raise_system_exit(signum: int, _frame: object) -> None:
    raise SystemExit(128 + signum)


@contextmanager
def terminate_as_exit() -> Iterator[None]:
    """Turn SIGTERM and SIGHUP into ``SystemExit`` so ``finally`` blocks run.

    Python's default action for both signals ends the process without unwinding,
    which skips the ``finally`` that removes a scratch tree. The exit status is
    128 plus the signal number, the shell convention for death by signal, so a
    caller can tell a kill from the 0/1/2/3 result codes. Handlers can only be
    installed from the main thread; elsewhere the guard is a no-op. Previous
    handlers are restored on exit.
    """
    previous: dict[int, Any] = {}
    try:
        for signum in _TERMINATION_SIGNALS:
            previous[signum] = signal.signal(signum, _raise_system_exit)
    except ValueError:
        pass
    try:
        yield
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)


@contextmanager
def guarded_scratch() -> Iterator[None]:
    """Sweep stale scratch, then run the body with termination signals unwinding."""
    sweep_stale_scratch()
    with terminate_as_exit():
        yield
