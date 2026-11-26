"""Digests, subprocesses, and artifact I/O for `eval_controller.py`.

It runs children with bounded time and digests protected paths. It provides
file helpers that reject leaf links and moves reports into the run directory.
"""

from __future__ import annotations

import hashlib
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
from typing import IO, Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _controller_config import (
    EVAL_DIR,
    EXIT_EXTERNAL,
    OPTIMIZER,
    REPO_ROOT,
    Config,
    ControllerError,
    resolve,
)

_TAIL = 400
# Largest optimizer reply the controller will parse. Real gate and extract
# documents are a few kilobytes; anything near this is a fault, not data.
_MAX_JSON_BYTES = 16 * 1024 * 1024
# Variables a Windows child needs to start at all; kept whatever the allowlist.
_WINDOWS_BASE_ENV = ("SYSTEMROOT", "COMSPEC", "PATHEXT", "TEMP", "TMP", "WINDIR")
# Every controller open of a file a child could have replaced: never follow a
# link at the leaf, never block on a FIFO, never translate line endings.
_OPEN_FLAGS = (
    getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)
)


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


def _open_regular(path: Path, flags: int) -> tuple[int, os.stat_result] | None:
    """Open `path` as a regular file, or return None.

    None covers a link at the leaf, a FIFO, a directory, a device, and a
    missing file; the caller names the refusal. The type check reads the open
    descriptor, so the file checked is the file then read or written. Windows
    has no `O_NOFOLLOW`, so a leaf link is refused there by a check first.
    """
    if not getattr(os, "O_NOFOLLOW", 0) and os.path.islink(path):
        return None
    try:
        handle = os.open(path, flags | _OPEN_FLAGS, 0o600)
    except OSError:
        return None
    info = os.fstat(handle)
    if not stat.S_ISREG(info.st_mode):
        os.close(handle)
        return None
    return handle, info


def read_private(path: Path, what: str) -> bytes:
    """Read a file the controller wrote, refusing a link, FIFO, or hard link."""
    opened = _open_regular(path, os.O_RDONLY)
    if opened is not None and opened[1].st_nlink != 1:
        os.close(opened[0])
        opened = None
    if opened is None:
        raise ControllerError(f"{what} {path} is not a regular file with one link")
    with os.fdopen(opened[0], "rb") as stream:
        return stream.read()


def write_private(path: Path, text: str, *, append: bool = False) -> None:
    """Create (or append to) a controller file without writing through a plant.

    A new file is an exclusive create, which fails on anything already at the
    path, link included. An append refuses a link, FIFO, or hard link.
    """
    mode = os.O_APPEND if append else os.O_EXCL
    opened = _open_regular(path, os.O_WRONLY | os.O_CREAT | mode)
    if opened is not None and opened[1].st_nlink != 1:
        os.close(opened[0])
        opened = None
    if opened is None:
        raise ControllerError(f"{path} is not a regular file the controller made; not writing it")
    with os.fdopen(opened[0], "ab" if append else "wb") as stream:
        stream.write(text.encode("utf-8"))


def is_real_dir(path: Path) -> bool:
    """Whether `path` is a directory reached through no link at all.

    Callers pass paths under the resolved `state_dir`, so any link swapped in
    for the leaf or a directory above it makes the real path differ.
    """
    return os.path.realpath(path) == str(path) and path.is_dir()


def _file_digest(path: Path) -> str:
    opened = _open_regular(path, os.O_RDONLY)
    if opened is None:
        # Raced from a file to something else; an unequal digest refuses.
        return "unreadable"
    sha = hashlib.sha256()
    with os.fdopen(opened[0], "rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            sha.update(block)
    return sha.hexdigest()


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
                sha.update(f"{entry}:{_file_digest(entry)}\n".encode())
            else:
                sha.update(f"missing:{entry}\n".encode())
    return sha.hexdigest()


def collect_into(source: Path, destination: Path) -> list[str]:
    """Move one scorer output to `destination`; return what went wrong.

    `shutil.move` follows a link at the destination and moves the report into
    whatever directory it names, which can be outside state. A link there is
    removed before the move, so the report still leaves the checkout; anything
    else there is left alone. Either way the run fails.
    """
    problems: list[str] = []
    if os.path.lexists(destination):
        problems.append(f"collect destination {destination} existed before collection")
        if not destination.is_symlink():
            return problems
        destination.unlink()
    try:
        shutil.move(str(source), str(destination))
    except OSError as exc:
        problems.append(f"could not move scorer output {source}: {exc}")
    return problems


def collect_all(templates: Sequence[str], values: Mapping[str, str], run_dir: Path) -> list[str]:
    """Move every `collect` output into `run_dir`; return what went wrong.

    Each path is attempted on its own, so one missing or unmovable report
    never leaves a later one, with its held-out outcomes, in the checkout.
    The caller has checked that `run_dir` is still a real directory.
    """
    problems: list[str] = []
    for index, template in enumerate(templates):
        source = resolve(fill(template, values))
        if not (source.exists() or source.is_symlink()):
            problems.append(f"scorer output {source} was not produced")
            continue
        # The scorer knows `run_dir`, so it may have planted the destination.
        problems.extend(collect_into(source, run_dir / str(index)))
    return problems


def refuse_stale_reports(templates: Sequence[str], values: Mapping[str, str], label: str) -> None:
    # A report already sitting at a collect path belongs to some earlier run.
    # Collecting it would gate on the wrong results.
    for template in templates:
        stale = resolve(fill(template, values))
        if stale.exists() or stale.is_symlink():
            raise ControllerError(
                f"scorer output {stale} exists before {label} was scored; "
                "use a collect path that names the run (`{run_id}`) or clear it"
            )


def contained_inputs(
    templates: Sequence[str], values: Mapping[str, str], run_dir: Path
) -> list[str]:
    inputs = [fill(item, values) for item in templates]
    for item in inputs:
        # The template check at load is lexical; `{run_dir}/../x` passes it.
        if run_dir.resolve() not in Path(item).resolve().parents:
            raise ControllerError(f"extract input {item} is outside the run directory")
    return inputs


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
    candidate, and read them through the artifact path. The checks read the
    open descriptor, so a link swapped in after them is never read.
    """
    opened = _open_regular(path, os.O_RDONLY)
    if opened is None:
        raise ControllerError(f"artifact {path} is no longer a regular file")
    handle, info = opened
    with os.fdopen(handle, "rb") as stream:
        if info.st_nlink > 1:
            raise ControllerError(f"artifact {path} has more than one hard link")
        return stream.read()


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
