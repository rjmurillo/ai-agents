"""Digests, subprocesses, and artifact I/O for `eval_controller.py`.

Split from the controller so each file stays reviewable. Nothing here decides
an accept; it runs children with bounded time, digests protected paths, and
reads and writes the artifact without following planted links.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from types import ModuleType
from typing import IO, Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _controller_config import (
    EVAL_DIR,
    EXIT_EXTERNAL,
    OPTIMIZER,
    REPO_ROOT,
    Config,
    ControllerError,
)

_TAIL = 400
# Largest optimizer reply the controller will parse. Real gate and extract
# documents are a few kilobytes; anything near this is a fault, not data.
_MAX_JSON_BYTES = 16 * 1024 * 1024
# Variables a Windows child needs to start at all; kept whatever the allowlist.
_WINDOWS_BASE_ENV = ("SYSTEMROOT", "COMSPEC", "PATHEXT", "TEMP", "TMP", "WINDIR")
# The state lock file. It holds no data; only who has it locked matters.
STATE_LOCK = "controller.lock"

_FCNTL: ModuleType | None
try:
    _FCNTL = importlib.import_module("fcntl")
except ImportError:  # Windows has no fcntl
    _FCNTL = None


def _walk(root: Path) -> list[Path]:
    """Every entry under `root`, failing on a directory it cannot read.

    `Path.rglob` skips unreadable directories silently, so two scans of a
    subtree nobody can read would digest equal without checking a file.
    Bytecode caches are skipped only under the eval directory, where the
    controller sends Python's caches elsewhere and nothing reads them.
    """

    def refuse(error: OSError) -> None:
        raise ControllerError(f"cannot read protected path {error.filename}: {error.strerror}")

    entries: list[Path] = []
    for current, dirs, files in os.walk(root, onerror=refuse):
        if root == EVAL_DIR:
            dirs[:] = [name for name in dirs if name != "__pycache__"]
        base = Path(current)
        entries.extend(base / name for name in (*dirs, *files))
    return sorted(entries)


def tree_digest(paths: Sequence[Path], exclude: Path | None = None) -> str:
    """One digest over the names and bytes of every file under `paths`."""
    sha = hashlib.sha256()
    for root in paths:
        try:
            info = root.lstat()
        except FileNotFoundError:
            info = None
        except OSError as exc:
            # A root under a directory nobody can traverse reads as "missing"
            # to the path predicates, so two scans would agree unseen.
            raise ControllerError(f"cannot inspect protected path {root}: {exc.strerror}") from exc
        is_tree = info is not None and stat.S_ISDIR(info.st_mode)
        entries = _walk(root) if is_tree else [root]
        for entry in entries:
            if exclude is not None and (entry == exclude or exclude in entry.parents):
                continue
            if entry.is_symlink():
                sha.update(f"link:{entry}:{os.readlink(entry)}\n".encode())
            elif entry.is_dir():
                sha.update(f"dir:{entry}\n".encode())
            elif entry.is_file():
                sha.update(f"{entry}:{hashlib.sha256(entry.read_bytes()).hexdigest()}\n".encode())
            else:
                sha.update(f"missing:{entry}\n".encode())
    return sha.hexdigest()


def lock_state(state: Path) -> int:
    """Take the one-controller lock on `state`; return the fd that holds it.

    Two controllers on one `state_dir` each see the other's writes as
    tampering, and both can pass the fresh-session check before either
    writes `split.json`. With `fcntl` the lock is `flock` on a file in state:
    the kernel drops it when the holder dies, so a crash leaves nothing to
    clear. Without `fcntl` an exclusive create is the lock, and a file left
    by a killed run is reported rather than broken.
    """
    lock = state / STATE_LOCK
    busy = f"another controller is running against {state}; wait for it or use a fresh state_dir"
    flags = os.O_CREAT | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0)
    if _FCNTL is None:
        try:
            return os.open(lock, flags | os.O_EXCL)
        except FileExistsError:
            raise ControllerError(f"{busy}; if none is, remove {lock}") from None
    handle = os.open(lock, flags)
    try:
        _FCNTL.flock(handle, _FCNTL.LOCK_EX | _FCNTL.LOCK_NB)
    except BlockingIOError:
        os.close(handle)
        raise ControllerError(busy) from None
    return handle


def unlock_state(state: Path, handle: int) -> None:
    """Release `lock_state`. The exclusive-create lock is the file itself."""
    os.close(handle)
    if _FCNTL is None:
        (state / STATE_LOCK).unlink(missing_ok=True)


def fill(template: str, values: Mapping[str, str]) -> str:
    out = template
    for key, value in values.items():
        out = out.replace("{" + key + "}", value)
    return out


def task_file(template: str, task: str) -> str:
    """Fill a task-file template, refusing an id that could leave its directory.

    Task ids come from scorer output. A forged id such as `../../secret` would
    otherwise copy an arbitrary file into the proposer workspace. Only the
    placeholders the template uses are checked.
    """
    values = {"task_id": task, "task_name": task.rsplit("::", 1)[-1]}
    for key, value in values.items():
        if "{" + key + "}" not in template:
            continue
        if "/" in value or "\\" in value or value in ("", ".", ".."):
            raise ControllerError(f"task id {task!r} is not safe to use in a path")
    return fill(template, values)


def kill_group(proc: subprocess.Popen[bytes]) -> None:
    """Kill the child's process group when its call ends.

    A proposer that leaves a background child behind could rewrite the artifact
    after the controller read it. This kills the group the child started in.
    It does not reach a descendant that left the group with `setsid`, and on
    Windows it kills only the direct child. The post-score byte check and the
    per-step integrity checks are the guards that remain.
    """
    if os.name != "posix":
        proc.kill()
        return
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def _spawn(
    argv: list[str],
    what: str,
    timeout: int,
    env: Mapping[str, str] | None,
    limit: int | None = None,
) -> tuple[int, str, str]:
    """Run one child in its own session; return its exit code and output.

    Output goes to temporary files, not pipes. A descendant that escapes the
    process group would otherwise hold a pipe open, and the read would block
    past the timeout until that descendant exited. The child's group is
    killed when the call ends, on timeout as well as on a normal exit.

    Only a bounded tail of stderr is read back, and stdout is read in full
    only up to `limit`. The files themselves are not capped while the child
    runs: capping them needs a pipe, and a pipe brings back the timeout
    bypass described above.
    """
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        try:
            proc = subprocess.Popen(
                argv,
                stdout=out,
                stderr=err,
                cwd=REPO_ROOT,
                start_new_session=True,
                env=None if env is None else dict(env),
            )
        except OSError as exc:
            raise ControllerError(f"{what} could not start: {exc}", EXIT_EXTERNAL) from exc
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            kill_group(proc)
            proc.wait()
            raise ControllerError(f"{what} timed out after {timeout}s", EXIT_EXTERNAL) from exc
        finally:
            kill_group(proc)
        stdout = _bounded(out, limit)
        stderr = _tail(err)
    return proc.returncode, stdout, stderr


def _tail(stream: IO[bytes]) -> str:
    """The last bytes of a child's output; only a diagnostic tail is kept."""
    size = stream.seek(0, os.SEEK_END)
    stream.seek(max(0, size - 4 * _TAIL))
    return stream.read().decode("utf-8", errors="replace")[-_TAIL:]


def _bounded(stream: IO[bytes], limit: int | None) -> str:
    """The child's stdout, refused past `limit` bytes, or its tail when unlimited."""
    if limit is None:
        return _tail(stream)
    size = stream.seek(0, os.SEEK_END)
    if size > limit:
        raise ControllerError(f"child output of {size} bytes exceeds {limit}", EXIT_EXTERNAL)
    stream.seek(0)
    return stream.read().decode("utf-8", errors="replace")


def run_child(
    argv: list[str],
    what: str,
    timeout: int,
    env: Mapping[str, str] | None = None,
    ok_codes: Sequence[int] = (0,),
) -> float:
    """Run one scorer or proposer call; return its duration in seconds."""
    started = time.monotonic()
    code, stdout, stderr = _spawn(argv, what, timeout, env)
    if code not in ok_codes:
        raise ControllerError(
            f"{what} exited {code}; see the controller log",
            EXIT_EXTERNAL,
            detail=(stderr or stdout).strip(),
        )
    return round(time.monotonic() - started, 3)


def optimizer(
    args: list[str], timeout: int, env: Mapping[str, str] | None = None
) -> tuple[int, dict[str, Any]]:
    what = f"optimize-artifact {args[0]}"
    code, stdout, stderr = _spawn(
        [sys.executable, str(OPTIMIZER), *args], what, timeout, env, _MAX_JSON_BYTES
    )
    try:
        payload = json.loads(stdout)
    except ValueError as exc:
        raise ControllerError(
            f"{what} returned no JSON (exit {code})",
            EXIT_EXTERNAL,
            detail=stderr.strip(),
        ) from exc
    if not isinstance(payload, dict):
        raise ControllerError(f"{what} returned a non-object", EXIT_EXTERNAL)
    return code, payload


def write_artifact(path: Path, data: bytes, mode: int) -> None:
    """Replace the artifact without following a link the proposer planted.

    `os.replace` swaps the directory entry, so a symlink or hard link at
    `path` is replaced rather than written through. A directory the proposer
    left there is removed first; `rmtree` does not follow links inside it.
    `mkstemp` creates the temp file at 0600, so the artifact's own mode,
    recorded before the loop, is set before the swap.
    """
    try:
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        handle, temp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
        try:
            with os.fdopen(handle, "wb") as stream:
                stream.write(data)
            os.chmod(temp, mode)
            os.replace(temp, path)
        except BaseException:
            Path(temp).unlink(missing_ok=True)
            raise
    except OSError as exc:
        raise ControllerError(f"could not restore artifact {path}: {exc}", EXIT_EXTERNAL) from exc


def read_artifact(path: Path) -> bytes:
    """Read the artifact, refusing a symlink, a hard link, or a non-file.

    A hard link would let the proposer make a denied file's bytes the
    candidate, and read them through the artifact path.
    """
    if path.is_symlink() or not path.is_file():
        raise ControllerError(f"artifact {path} is no longer a regular file")
    if path.stat().st_nlink > 1:
        raise ControllerError(f"artifact {path} has more than one hard link")
    return path.read_bytes()


def clear_dir(directory: Path) -> None:
    """Empty a proposer-writable directory without following any link in it."""
    if directory.is_symlink():
        raise ControllerError(f"{directory} must not be a symlink")
    directory.mkdir(parents=True, exist_ok=True)
    for child in directory.iterdir():
        if child.is_symlink() or not child.is_dir():
            child.unlink()
        else:
            shutil.rmtree(child)


def proposer_env(config: Config) -> dict[str, str]:
    """The proposer's environment: `PATH` plus the config's allowlist.

    The allowlist is required, so scorer credentials in the launcher's
    environment never reach the proposer unless the launcher names them.
    `EVAL_LEDGER_DIR` never passes, so a proposer that shells out to
    `optimize-artifact.py` cannot find the controller's ledger by it.
    """
    keep = {"PATH", *config.proposer_env}
    if os.name == "nt":
        # Windows children fail to start without these, and its variable
        # names are case-insensitive (`Path` is `PATH`).
        keep = {name.upper() for name in (*keep, *_WINDOWS_BASE_ENV)}
        return {
            key: value
            for key, value in os.environ.items()
            if key.upper() in keep and key.upper() != "EVAL_LEDGER_DIR"
        }
    keep.discard("EVAL_LEDGER_DIR")
    return {key: value for key, value in os.environ.items() if key in keep}
