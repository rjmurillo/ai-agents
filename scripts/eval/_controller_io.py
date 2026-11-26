"""Config, digests, subprocesses, and artifact I/O for `eval_controller.py`.

Split from the controller so each file stays reviewable. Nothing here decides
an accept; it only loads the launcher's config, runs children with bounded
time, and reads and writes the artifact without following planted links.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

EXIT_OK = 0
EXIT_CONFIG = 2
EXIT_EXTERNAL = 3

KINDS = ("agent", "rule", "hook")
EVAL_DIR = Path(__file__).resolve().parent
OPTIMIZER = EVAL_DIR / "optimize-artifact.py"
REPO_ROOT = EVAL_DIR.parents[1]
_TAIL = 400


class ControllerError(Exception):
    """A config, integrity, or subprocess failure with a known exit code."""

    def __init__(self, message: str, code: int = EXIT_CONFIG, detail: str = "") -> None:
        super().__init__(message)
        self.code = code
        # Child output stays out of the message, which reaches the launcher's
        # stderr. The controller writes it to its own denied log instead.
        self.detail = detail


@dataclass(frozen=True)
class Config:
    kind: str
    artifact: Path
    state_dir: Path
    workspace_dir: Path
    scorer: list[str]
    collect: list[str]
    inputs: list[str]
    extract_args: list[str]
    proposer: list[str]
    seed: str
    sel_ratio: str
    max_consultations: int
    max_p: float | None
    steps: int
    opt_task_files: str | None
    deny_paths: list[Path]
    trusted_paths: list[Path]
    proposer_env: list[str]
    scorer_exit_codes: tuple[int, ...]
    config_path: Path
    timeout_seconds: int


def resolve(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else REPO_ROOT / path


def overlaps(left: Path, right: Path) -> bool:
    a, b = left.resolve(), right.resolve()
    return a == b or a in b.parents or b in a.parents


def _string_list(data: Mapping[str, Any], key: str, required: bool = True) -> list[str]:
    value = data.get(key, None if required else [])
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ControllerError(f"config `{key}` must be a list of strings")
    if required and not value:
        raise ControllerError(f"config `{key}` must not be empty")
    return list(value)


def _positive_int(value: object, key: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ControllerError(f"config `{key}` must be a positive integer")
    return value


def _checked_strings(data: Mapping[str, Any]) -> None:
    if data.get("kind") not in KINDS:
        raise ControllerError(f"config `kind` must be one of {', '.join(KINDS)}")
    for key in ("artifact", "state_dir", "workspace_dir", "seed"):
        if not isinstance(data.get(key), str) or not data[key]:
            raise ControllerError(f"config `{key}` must be a non-empty string")
    max_p = data.get("max_p")
    if max_p is not None and (isinstance(max_p, bool) or not isinstance(max_p, (int, float))):
        raise ControllerError("config `max_p` must be a number or null")
    template = data.get("opt_task_files")
    if template is not None and (
        not isinstance(template, str)
        or ("{task_id}" not in template and "{task_name}" not in template)
    ):
        raise ControllerError(
            "config `opt_task_files` must be a string holding `{task_id}` or `{task_name}`"
        )
    if not isinstance(data.get("sel_ratio", "0.4"), str):
        raise ControllerError("config `sel_ratio` must be a string, as `split` reads it")


def load_config(path: Path) -> Config:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ControllerError(f"cannot read config {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ControllerError("config must be a JSON object")
    _checked_strings(data)
    max_p = data.get("max_p")
    codes = data.get("scorer_exit_codes", [0])
    if (
        not isinstance(codes, list)
        or not codes
        or not all(isinstance(c, int) and not isinstance(c, bool) and 0 <= c < 256 for c in codes)
    ):
        raise ControllerError("config `scorer_exit_codes` must be a non-empty list of exit codes")
    if not isinstance(data.get("proposer_env"), list):
        raise ControllerError(
            "config `proposer_env` must list the variables the proposer may see ([] for none)"
        )
    config = Config(
        kind=data["kind"],
        # Canonical path: a launcher may name a tracked symlink (rules are
        # links into src/claude/rules/). Every later read refuses a link, so
        # the controller works on the file the link names.
        artifact=resolve(data["artifact"]).resolve(),
        state_dir=resolve(data["state_dir"]),
        workspace_dir=resolve(data["workspace_dir"]),
        scorer=_string_list(data, "scorer"),
        collect=_string_list(data, "collect", required=False),
        inputs=_string_list(data, "inputs"),
        extract_args=_string_list(data, "extract_args", required=False),
        proposer=_string_list(data, "proposer"),
        seed=data["seed"],
        sel_ratio=data.get("sel_ratio", "0.4"),
        max_consultations=_positive_int(data.get("max_consultations"), "max_consultations"),
        max_p=None if max_p is None else float(max_p),
        steps=_positive_int(data.get("steps"), "steps"),
        opt_task_files=data.get("opt_task_files"),
        # Required: an empty list leaves the held-out task definitions readable
        # and undigested, which is the cooperating-optimizer design again.
        deny_paths=[resolve(item) for item in _string_list(data, "deny_paths")],
        trusted_paths=[
            resolve(item) for item in _string_list(data, "trusted_paths", required=False)
        ],
        proposer_env=_string_list(data, "proposer_env", required=False),
        scorer_exit_codes=tuple(codes),
        config_path=path.resolve(),
        timeout_seconds=_positive_int(data.get("timeout_seconds", 3600), "timeout_seconds"),
    )
    check_layout(config)
    return config


def trusted_code(config: Config) -> list[Path]:
    """Code the controller runs with its own authority: the gate and the scorer.

    The whole eval directory, not only its `.py` files: a planted package
    directory or data file beside `optimize-artifact.py` could shadow a module
    it imports. `tree_digest` records every entry, directories included.
    Bytecode caches are excluded because the controller runs the optimizer
    with `PYTHONPYCACHEPREFIX` under its state directory, so a cache under
    `scripts/eval/__pycache__` is never read.
    """
    return [EVAL_DIR, *config.trusted_paths]


def check_layout(config: Config) -> None:
    """Refuse a layout where the proposer would need a denied path to work."""
    _check_workspace_and_artifact(config)
    _check_protected_paths(config)


def _check_workspace_and_artifact(config: Config) -> None:
    if overlaps(config.state_dir, config.workspace_dir):
        raise ControllerError("`workspace_dir` and `state_dir` must not contain each other")
    if overlaps(config.config_path, config.workspace_dir):
        raise ControllerError("the config must not sit inside the proposer workspace")
    if overlaps(config.artifact, config.workspace_dir):
        raise ControllerError(
            "the artifact must not sit inside the proposer workspace, which is emptied each step"
        )
    if overlaps(config.artifact, config.state_dir):
        raise ControllerError("the artifact must not sit inside state_dir")


def _check_protected_paths(config: Config) -> None:
    for path in [*config.deny_paths, *config.trusted_paths]:
        if overlaps(path, config.workspace_dir) or overlaps(path, config.artifact):
            raise ControllerError(
                "a deny or trusted path overlaps the proposer workspace or the artifact; "
                "the proposer would need it to do its job"
            )
    for path in trusted_code(config):
        if overlaps(path, config.state_dir) or overlaps(path, config.workspace_dir):
            raise ControllerError(
                "state_dir and workspace_dir must sit outside trusted code; the controller's "
                "own writes there would read as tampering"
            )
    for path in config.deny_paths:
        if overlaps(path, config.state_dir) or overlaps(path, config.config_path):
            raise ControllerError(
                "a deny path overlaps state_dir or the config; the digest would "
                "change as the controller writes its own state"
            )


def tree_digest(paths: Sequence[Path], exclude: Path | None = None) -> str:
    """One digest over the names and bytes of every file under `paths`."""
    sha = hashlib.sha256()
    for root in paths:
        if root.is_dir() and not root.is_symlink():
            entries = sorted(p for p in root.rglob("*") if "__pycache__" not in p.parts)
        else:
            entries = [root]
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


def run_child(
    argv: list[str],
    what: str,
    timeout: int,
    env: Mapping[str, str] | None = None,
    ok_codes: Sequence[int] = (0,),
) -> float:
    """Run one scorer or proposer call; return its duration in seconds."""
    # Output goes to temporary files, not pipes. A descendant that escapes the
    # process group would otherwise hold a pipe open, and the read would block
    # past the timeout until that descendant exited.
    started = time.monotonic()
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
        if proc.returncode not in ok_codes:
            err.seek(0)
            out.seek(0)
            tail = (err.read() or out.read()).decode("utf-8", errors="replace").strip()[-_TAIL:]
            raise ControllerError(
                f"{what} exited {proc.returncode}; see the controller log",
                EXIT_EXTERNAL,
                detail=tail,
            )
    return round(time.monotonic() - started, 3)


def optimizer(
    args: list[str], timeout: int, env: Mapping[str, str] | None = None
) -> tuple[int, dict[str, Any]]:
    argv = [sys.executable, str(OPTIMIZER), *args]
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            cwd=REPO_ROOT,
            env=None if env is None else dict(env),
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise ControllerError(
            f"optimize-artifact {args[0]} timed out after {timeout}s", EXIT_EXTERNAL
        ) from exc
    except OSError as exc:
        raise ControllerError(
            f"optimize-artifact {args[0]} could not start: {exc}", EXIT_EXTERNAL
        ) from exc
    try:
        payload = json.loads(proc.stdout)
    except ValueError as exc:
        raise ControllerError(
            f"optimize-artifact {args[0]} returned no JSON (exit {proc.returncode})",
            EXIT_EXTERNAL,
            detail=proc.stderr.strip()[-_TAIL:],
        ) from exc
    if not isinstance(payload, dict):
        raise ControllerError(f"optimize-artifact {args[0]} returned a non-object", EXIT_EXTERNAL)
    return proc.returncode, payload


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
    keep = {"PATH", *config.proposer_env} - {"EVAL_LEDGER_DIR"}
    return {key: value for key, value in os.environ.items() if key in keep}
