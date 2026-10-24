"""Deterministic verifier runner: execute eval.json task commands against a bundle.

Each runnable task in eval.json carries a `command` (an argv list), a required
`timeout` in seconds, and at least one of `expect_exit` and `expect_stdout`:

    "t1": {"command": ["python3", "scripts/audit-draft.py", "--check", "x"],
           "timeout": 30, "expect_exit": 0, "expect_stdout": "clean"}

SECURITY. eval.json is executable input. Every `command` runs as the current
user and may start ANY binary on PATH. Run only an eval.json you wrote or
reviewed. The controls below shrink the blast radius of an honest mistake; they
are not a sandbox:

  - argv only, never a shell: no `shell=True`, so no pipes, globbing, or `$VAR`
    expansion, and a task cannot smuggle a second command through a string
  - a non-list command, an empty or non-string argv entry, or a NUL byte is
    refused before any task runs
  - a missing, non-numeric, non-positive, or over-limit `timeout` is refused
    before any task runs
  - argv[0] containing a path separator must stay inside the bundle after
    symlinks resolve; any argv entry that is an absolute path or has a `..`
    segment is refused. These are string checks on the literal argv, so a
    program that builds a path itself can still leave the bundle
  - cwd is the bundle root; stdin is closed; the environment is reduced to an
    allowlist, which keeps tokens in the caller's environment out of the task,
    and PATH keeps only absolute entries so a bare command name cannot resolve
    to a file inside the bundle
  - stdout goes to a temporary file; a task that writes more than
    MAX_STDOUT_BYTES is killed and fails, so a noisy task cannot fill memory
    or the disk
  - Python bytecode is redirected out of the bundle (PYTHONPYCACHEPREFIX), so a
    stale .pyc inside the bundle is never loaded in place of the source
  - the bundle is hashed before the run and after every task; a change fails
    the run without writing results, so a verifier cannot edit what it verifies

On POSIX a timed-out task is killed with its whole process group, and the group
is also killed after a normal exit, before the leader is reaped, so no orphan in
that group outlives its task. A process that starts its own session or process
group escapes this. On Windows only the direct child is killed. A task that
edits the bundle is detected, not undone: keep the bundle under version control.
"""

from __future__ import annotations

import os
import re
import signal
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from _skillopt_bundle import bundle_sha256
from _skillopt_patching import SkillOptError

MAX_TIMEOUT_SECONDS = 600
MAX_STDOUT_BYTES = 1024 * 1024
UNVERIFIED = "UNVERIFIED"
ENV_ALLOWLIST = (
    "PATH",
    "PATHEXT",
    "SYSTEMROOT",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "TMPDIR",
    "TEMP",
    "TMP",
)
_FORCED_ENV = {"PYTHONIOENCODING": "utf-8"}
_SHORT_OPTION = re.compile(r"^-[A-Za-z]")
_DRIVE_PATH = re.compile(r"^[A-Za-z]:[\\/]")
_SEPARATORS = re.compile(r"[\\/]")


@dataclass(frozen=True)
class RunnableTask:
    """A validated task: argv is final, with argv[0] resolved inside the bundle if pathy."""

    task_id: str
    argv: tuple[str, ...]
    timeout: float
    expect_exit: int
    expect_stdout: str | None


@dataclass(frozen=True)
class TaskOutcome:
    """Result of one task: True, False, or UNVERIFIED, with a short non-content reason."""

    value: bool | str
    reason: str


def _is_absolute_text(text: str) -> bool:
    return text.startswith(("/", "\\")) or bool(_DRIVE_PATH.match(text))


def _has_parent_segment(text: str) -> bool:
    return ".." in _SEPARATORS.split(text)


def _escape_reason(text: str) -> str | None:
    """Why this argv entry names a path outside the bundle, by literal string checks.

    Checks the whole entry, every `=`-separated piece (`--opt=v`, `of=v`), and the
    tail of an attached short option (`-Ipath`). It is a filter for honest mistakes.
    """
    candidates = [text, *text.split("=")[1:]]
    if len(text) > 2 and _SHORT_OPTION.match(text):
        candidates.append(text[2:])
    for candidate in candidates:
        if _is_absolute_text(candidate):
            return "is an absolute path"
        if _has_parent_segment(candidate):
            return "has a '..' path segment"
    return None


def _resolve_program(task_id: str, program: str, bundle: Path) -> str:
    """Keep a pathy argv[0] inside the bundle; leave a bare name to PATH lookup."""
    if not _SEPARATORS.search(program):
        return program
    resolved = (bundle / program).resolve()
    if not resolved.is_relative_to(bundle.resolve()):
        raise SkillOptError(f"task {task_id}: command[0] resolves outside the bundle")
    return str(resolved)


def _validate_timeout(task_id: str, task: dict[str, Any]) -> float:
    if "timeout" not in task:
        raise SkillOptError(f"task {task_id}: timeout is required (seconds)")
    timeout = task["timeout"]
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
        raise SkillOptError(f"task {task_id}: timeout must be a number of seconds")
    if not 0 < timeout <= MAX_TIMEOUT_SECONDS:
        raise SkillOptError(
            f"task {task_id}: timeout must be greater than 0 and at most {MAX_TIMEOUT_SECONDS}"
        )
    return float(timeout)


def _validate_command(task_id: str, task: dict[str, Any], bundle: Path) -> tuple[str, ...]:
    command = task["command"]
    if not isinstance(command, list):
        raise SkillOptError(f"task {task_id}: command must be an argv list, not a shell string")
    if not command:
        raise SkillOptError(f"task {task_id}: command is empty")
    for index, part in enumerate(command):
        if not isinstance(part, str):
            raise SkillOptError(f"task {task_id}: command[{index}] must be a string")
        if "\0" in part:
            raise SkillOptError(f"task {task_id}: command[{index}] contains a NUL byte")
        reason = _escape_reason(part)
        if reason:
            raise SkillOptError(f"task {task_id}: command[{index}] {reason}")
    if not command[0]:
        raise SkillOptError(f"task {task_id}: command[0] is empty")
    return (_resolve_program(task_id, command[0], bundle), *command[1:])


def validate_task(task_id: str, task: dict[str, Any], bundle: Path) -> RunnableTask:
    """Validate one command task or raise SkillOptError. Runs nothing."""
    has_exit, has_stdout = "expect_exit" in task, "expect_stdout" in task
    if not (has_exit or has_stdout):
        raise SkillOptError(f"task {task_id}: needs expect_exit or expect_stdout")
    expect_exit = task.get("expect_exit", 0)
    if isinstance(expect_exit, bool) or not isinstance(expect_exit, int):
        raise SkillOptError(f"task {task_id}: expect_exit must be an integer")
    expect_stdout = task.get("expect_stdout")
    if has_stdout and not isinstance(expect_stdout, str):
        raise SkillOptError(f"task {task_id}: expect_stdout must be a string")
    return RunnableTask(
        task_id=task_id,
        argv=_validate_command(task_id, task, bundle),
        timeout=_validate_timeout(task_id, task),
        expect_exit=expect_exit,
        expect_stdout=expect_stdout,
    )


def select_tasks(
    eval_set: dict[str, Any], bundle: Path, split: str | None
) -> tuple[list[RunnableTask], list[str]]:
    """Validate every command task in scope; return (runnable, ids skipped without a command).

    split=None means every id named by any split. A task with no `command` is a
    semantic task the agent grades, so it is skipped and left out of the results,
    which pair-gate reads as UNVERIFIED rather than as a pass.
    """
    splits = eval_set.get("splits")
    if not isinstance(splits, dict) or not splits:
        raise SkillOptError("eval set has no splits")
    if split is not None and split not in splits:
        raise SkillOptError(f"eval set has no '{split}' split")
    tasks = eval_set.get("tasks", {})
    if not isinstance(tasks, dict):
        raise SkillOptError("eval set 'tasks' must be an object")
    names = [split] if split is not None else list(splits)
    ordered: list[str] = []
    for name in names:
        ids = splits[name]
        if not isinstance(ids, list) or not all(isinstance(i, str) and i for i in ids):
            raise SkillOptError(f"'{name}' split must be a list of nonempty string task ids")
        ordered.extend(i for i in ids if i not in ordered)
    runnable: list[RunnableTask] = []
    skipped: list[str] = []
    for task_id in ordered:
        task = tasks.get(task_id)
        if task is None:
            skipped.append(task_id)
        elif not isinstance(task, dict):
            raise SkillOptError(f"task {task_id}: must be an object")
        elif "command" in task:
            runnable.append(validate_task(task_id, task, bundle))
        elif any(key in task for key in ("expect_exit", "expect_stdout", "timeout")):
            raise SkillOptError(f"task {task_id}: has verifier fields but no command")
        else:
            skipped.append(task_id)
    if not runnable:
        raise SkillOptError("no task in scope has a command; nothing to run")
    return runnable, skipped


def _absolute_path_entries(path: str) -> str:
    """Drop empty and relative PATH entries: they resolve against the bundle cwd."""
    entries = [entry for entry in path.split(os.pathsep) if entry and os.path.isabs(entry)]
    return os.pathsep.join(entries)


def _child_env() -> dict[str, str]:
    env = {key: os.environ[key] for key in ENV_ALLOWLIST if key in os.environ}
    if "PATH" in env:
        env["PATH"] = _absolute_path_entries(env["PATH"])
    env.update(_FORCED_ENV)
    return env


def _kill_tree(proc: subprocess.Popen[bytes]) -> None:
    try:
        if os.name == "posix":
            os.killpg(proc.pid, signal.SIGKILL)
        else:
            proc.kill()
    except OSError:
        pass


def _normalize(text: str) -> str:
    return text.replace("\r\n", "\n").rstrip("\n")


def _read_stdout(handle: Any) -> str:
    handle.seek(0)
    raw: bytes = handle.read(MAX_STDOUT_BYTES)
    return raw.decode("utf-8", errors="replace")


def _has_exited(proc: subprocess.Popen[bytes]) -> bool:
    """True once the task exited. On POSIX the leader is left unreaped (WNOWAIT).

    An unreaped leader keeps its pid reserved as the process group id, so the
    group kill that follows cannot hit a recycled pid.
    """
    if os.name == "posix" and hasattr(os, "waitid"):
        return os.waitid(os.P_PID, proc.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT) is not None
    return proc.poll() is not None


def _wait(proc: subprocess.Popen[bytes], timeout: float, captured: Any) -> str:
    """Wait for the task: "exited", "timeout", or "oversize". Always kills the group."""
    deadline = time.monotonic() + timeout
    delay = 0.001
    try:
        while True:
            if _has_exited(proc):
                state = "exited"
                break
            if os.fstat(captured.fileno()).st_size > MAX_STDOUT_BYTES:
                state = "oversize"
                break
            if time.monotonic() >= deadline:
                state = "timeout"
                break
            time.sleep(delay)
            delay = min(delay * 2, 0.05)
    except BaseException:
        _kill_tree(proc)
        proc.wait()
        raise
    # Kill any process the task left in its group, then reap the leader.
    _kill_tree(proc)
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass
    return state


def run_task(task: RunnableTask, bundle: Path, pycache: str) -> TaskOutcome:
    """Run one task. Timeout and launch failure are UNVERIFIED, never a pass."""
    env = {**_child_env(), "PYTHONPYCACHEPREFIX": pycache}
    with tempfile.TemporaryFile() as captured:
        try:
            proc = subprocess.Popen(
                list(task.argv),
                cwd=bundle,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=captured,
                stderr=subprocess.DEVNULL,
                shell=False,
                start_new_session=os.name == "posix",
            )
        except OSError as exc:
            return TaskOutcome(UNVERIFIED, f"could not start: {exc.__class__.__name__}")
        state = _wait(proc, task.timeout, captured)
        if state == "timeout":
            return TaskOutcome(UNVERIFIED, f"timed out after {task.timeout:g}s")
        if state == "oversize":
            return TaskOutcome(False, f"stdout longer than {MAX_STDOUT_BYTES} bytes")
        if proc.returncode != task.expect_exit:
            return TaskOutcome(False, f"exit {proc.returncode}, expected {task.expect_exit}")
        if task.expect_stdout is None:
            return TaskOutcome(True, "ok")
        text = _read_stdout(captured)
    if _normalize(text) != _normalize(task.expect_stdout):
        return TaskOutcome(False, "stdout did not match expect_stdout")
    return TaskOutcome(True, "ok")


def run_bundle(
    eval_set: dict[str, Any], bundle: Path, split: str | None
) -> tuple[dict[str, TaskOutcome], list[str], str]:
    """Validate, run, and re-hash. Returns (outcomes by id, skipped ids, bundle sha256)."""
    if bundle.is_symlink() or not bundle.is_dir():
        raise SkillOptError(f"bundle {bundle} is not a real directory")
    root = bundle.resolve()
    runnable, skipped = select_tasks(eval_set, root, split)
    before = bundle_sha256(root)
    outcomes: dict[str, TaskOutcome] = {}
    with tempfile.TemporaryDirectory(prefix="skillopt-pyc-") as pycache:
        for task in runnable:
            outcomes[task.task_id] = run_task(task, root, pycache)
            if bundle_sha256(root) != before:
                raise SkillOptError(
                    f"bundle changed while task {task.task_id} ran; no results written"
                )
    return outcomes, skipped, before
