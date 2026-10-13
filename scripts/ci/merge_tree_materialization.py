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

if sys.platform != "win32":
    import fcntl

_CLEANUP_RETRY_DELAYS = (0.1, 0.2, 0.4, 0.8, 1.6)
_TRANSIENT_CLEANUP_ERRNOS = frozenset({errno.EBUSY, errno.ENOTEMPTY})

# Scratch prefixes this package creates under the system temp dir. The sweep
# touches only entries named with one of these, or the dotted siblings that
# materialize_tree and init_scratch_repo create beside a scratch tree.
SCRATCH_PREFIXES = ("merge-tree-ratchet-", "base-derived-ratchet-")
_SIBLING_SUFFIXES = ("-materialize-home", "-materialize-index", "-git-home")
# The age floor is a backstop. A live run holds a lock on its scratch tree
# (see create_scratch), and the sweep skips any locked tree whatever its age.
# Where locks are unavailable (Windows), the floor alone protects a live run;
# it is twice the 30m cap on the longest pre-push job in lefthook.yml.
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


_HELD_SCRATCH_LOCKS: dict[Path, int] = {}


def create_scratch(prefix: str) -> Path:
    """Create a scratch tree under the temp dir and mark it live with a shared lock.

    A concurrent sweep from another run skips any tree whose lock it cannot
    take, whatever the tree's age. The kernel drops the lock when this process
    dies by any means, SIGKILL included, so a killed run's tree becomes
    sweepable. Release with ``remove_scratch``. Raises ``OSError`` when the
    directory cannot be created. A lock that cannot be taken is reported and
    skipped; the age floor then protects the tree.
    """
    scratch = Path(tempfile.mkdtemp(prefix=prefix))
    if sys.platform != "win32":
        try:
            _HELD_SCRATCH_LOCKS[scratch] = _open_locked(scratch, fcntl.LOCK_SH)
        except OSError as exc:
            sys.stderr.write(f"scratch lock skipped: {type(exc).__name__}: {exc}\n")
    return scratch


def remove_scratch(scratch: Path, label: str) -> str | None:
    """Release the live-run lock on ``scratch``, then remove it. Returns a cleanup error."""
    fd = _HELD_SCRATCH_LOCKS.pop(scratch, None)
    if fd is not None:
        os.close(fd)
    return remove_tree(scratch, label)


def _open_locked(path: Path, operation: int) -> int:
    """Open directory ``path`` and take a non-blocking ``operation`` flock on it.

    POSIX only; callers check ``sys.platform`` first. Raises
    ``BlockingIOError`` when another process holds a conflicting lock, and
    ``OSError`` when ``path`` is missing, a symlink, or not a directory.
    """
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        fcntl.flock(fd, operation | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        raise
    return fd


def _owning_scratch_name(name: str, prefixes: tuple[str, ...]) -> str | None:
    """Name of the scratch tree ``name`` belongs to, or None when it is not ours.

    A scratch tree owns itself. A dotted sibling such as
    ``.merge-tree-ratchet-abc-git-home`` belongs to ``merge-tree-ratchet-abc``.
    """
    if name.startswith(prefixes):
        return name
    if not name.startswith("."):
        return None
    for suffix in _SIBLING_SUFFIXES:
        if name.endswith(suffix) and name[1:].startswith(prefixes):
            return name[1 : -len(suffix)]
    return None


def _is_stale_and_owned(entry: Path, is_sibling: bool, cutoff: float) -> bool:
    """True for a non-symlink entry this user owns, last modified before ``cutoff``.

    A scratch tree must be a directory. A sibling may also be a regular file,
    because the temporary index is one. Ownership is not checked on Windows,
    which has no ``os.getuid``; the per-user temp dir scopes the sweep there.
    """
    try:
        info = entry.lstat()
    except OSError:
        return False
    is_dir = stat.S_ISDIR(info.st_mode)
    if not (is_dir or (is_sibling and stat.S_ISREG(info.st_mode))):
        return False
    if info.st_mtime >= cutoff:
        return False
    return not hasattr(os, "getuid") or info.st_uid == os.getuid()


def _remove_entry(entry: Path) -> str | None:
    if entry.is_dir():
        return remove_tree(entry, "stale ratchet scratch")
    try:
        entry.unlink(missing_ok=True)
    except OSError as exc:
        return f"stale ratchet scratch cleanup failed: {type(exc).__name__}: {exc}"
    return None


def _remove_unless_live(entry: Path, owner: Path) -> bool:
    """Remove ``entry`` while holding an exclusive lock on its scratch tree ``owner``.

    A lock held elsewhere means a live run owns the tree, so the entry stays.
    A missing owner means a sibling was orphaned, so the entry goes.
    """
    lock_fd: int | None = None
    if sys.platform != "win32":
        try:
            lock_fd = _open_locked(owner, fcntl.LOCK_EX)
        except FileNotFoundError:
            lock_fd = None
        except OSError:
            return False
    try:
        error = _remove_entry(entry)
    finally:
        if lock_fd is not None:
            os.close(lock_fd)
    if error:
        sys.stderr.write(f"{error}\n")
    return error is None


def sweep_stale_scratch(
    prefixes: tuple[str, ...] = SCRATCH_PREFIXES,
    max_age_seconds: float = STALE_SCRATCH_AGE_SECONDS,
    temp_root: Path | None = None,
) -> int:
    """Remove scratch left behind by earlier killed runs. Returns the count removed.

    An entry qualifies only when its name is a scratch tree or one of that
    tree's dotted siblings, it is not a symlink, the current user owns it, its
    mtime is older than ``max_age_seconds``, and no live run holds the lock on
    its scratch tree. Anything else is left alone. A removal that fails is
    reported on stderr and skipped: a sweep must never fail a ratchet.
    """
    root = temp_root if temp_root is not None else Path(tempfile.gettempdir())
    try:
        entries = list(root.iterdir())
    except OSError as exc:
        sys.stderr.write(f"scratch sweep skipped: {type(exc).__name__}: {exc}\n")
        return 0
    cutoff = time.time() - max_age_seconds
    removed = 0
    for entry in entries:
        owner_name = _owning_scratch_name(entry.name, prefixes)
        if owner_name is None:
            continue
        if not _is_stale_and_owned(entry, owner_name != entry.name, cutoff):
            continue
        if _remove_unless_live(entry, root / owner_name):
            removed += 1
    return removed


def _raise_system_exit(signum: int, _frame: object) -> None:
    # Ignore any further termination signal so a second SIGTERM cannot abort
    # the finally block that is about to remove the scratch tree.
    for each in _TERMINATION_SIGNALS:
        signal.signal(each, signal.SIG_IGN)
    raise SystemExit(128 + signum)


@contextmanager
def terminate_as_exit() -> Iterator[None]:
    """Turn SIGTERM and SIGHUP into ``SystemExit`` so ``finally`` blocks run.

    Python's default action for both signals ends the process without unwinding,
    which skips the ``finally`` that removes a scratch tree. The exit status is
    128 plus the signal number, the shell convention for death by signal, so a
    caller can tell a kill from the 0/1/2/3 result codes. After the first
    signal, later ones are ignored until the guard exits, so cleanup inside the
    guard runs to completion. Handlers can only be installed from the main
    thread; elsewhere the guard is a no-op. Windows has no SIGHUP and its
    process kill does not deliver SIGTERM, so there the sweep is the only
    protection. Previous handlers are restored on exit.
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
    """Sweep stale scratch, then run the body with termination signals unwinding.

    Create and remove the scratch tree inside the body, so a signal at any
    point after creation still reaches the removal.
    """
    sweep_stale_scratch()
    with terminate_as_exit():
        yield
