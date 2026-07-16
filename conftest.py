"""Repository-wide pytest safety guards."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import uuid
import warnings
from collections.abc import Iterator
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent
_GIT_ENV_OVERRIDES = {"GIT_COMMON_DIR", "GIT_DIR", "GIT_INDEX_FILE", "GIT_WORK_TREE"}
_TRACE_ENV_NAMES = ("GIT_REFLOG_ACTION", "GIT_TRACE2_EVENT")


def _git_env() -> dict[str, str]:
    blocked = _GIT_ENV_OVERRIDES | set(_TRACE_ENV_NAMES)
    return {key: value for key, value in os.environ.items() if key not in blocked}


def _project_git_dir() -> Path:
    dot_git = PROJECT_ROOT / ".git"
    if dot_git.is_dir():
        return dot_git.resolve()
    try:
        git_dir_line = dot_git.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise OSError("could not resolve project git directory") from exc
    prefix = "gitdir:"
    if not git_dir_line.startswith(prefix):
        raise OSError("project .git file has no gitdir entry")
    git_dir = Path(git_dir_line[len(prefix) :].strip())
    if not git_dir.is_absolute():
        git_dir = PROJECT_ROOT / git_dir
    return git_dir.resolve()


def _run_git_capture(*args: str) -> subprocess.CompletedProcess[str] | None:
    """Run Git against PROJECT_ROOT and capture UTF-8 text output."""
    try:
        return subprocess.run(
            ["git", *args],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            env=_git_env(),
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None


def _real_repo_head() -> str | None:
    out = _run_git_capture("rev-parse", "HEAD")
    return out.stdout.strip() if out is not None and out.returncode == 0 else None


def _real_repo_head_subject() -> str:
    """Return the current HEAD commit subject, evidence for a concurrent commit."""
    out = _run_git_capture("log", "-1", "--format=%s")
    return out.stdout.strip() if out is not None and out.returncode == 0 else "<unknown>"


def _reflog_contains_action(action: str) -> bool:
    """Return whether the project reflogs contain this per-test action."""
    out = _run_git_capture(
        "reflog",
        "--all",
        "--format=%gs",
        f"--grep-reflog={action}",
        "-n",
        "1",
    )
    if out is None or out.returncode != 0:
        raise OSError("could not read project reflogs")
    return bool(out.stdout.strip())


def _command_args(argv: list[str], command: str) -> list[str]:
    executable = argv[0].replace("\\", "/").rsplit("/", 1)[-1].casefold() if argv else ""
    for suffix in (".exe", ".cmd", ".bat"):
        if executable.endswith(suffix):
            executable = executable[: -len(suffix)]
            break
    if executable == f"git-{command}".casefold():
        return argv[1:]
    command_name = command.casefold()
    for index, argument in enumerate(argv):
        if argument.casefold() == command_name:
            return argv[index + 1 :]
    return []


def _positional_args(args: list[str], options_with_values: set[str]) -> list[str]:
    positional: list[str] = []
    skip_next = False
    for argument in args:
        if skip_next:
            skip_next = False
            continue
        if argument in options_with_values:
            skip_next = True
            continue
        if argument == "--":
            continue
        if argument.startswith("-"):
            continue
        positional.append(argument)
    return positional


def _symbolic_ref_mutates_head(args: list[str]) -> bool:
    positional = _positional_args(args, {"-m"})
    if not positional or positional[0] != "HEAD":
        return False
    return "--delete" in args or len(positional) >= 2


def _update_ref_mutates_branch(args: list[str]) -> bool:
    if "--stdin" in args:
        return False
    positional = _positional_args(args, {"-m"})
    if not positional:
        return False
    ref_name = positional[0]
    return ref_name == "HEAD" or ref_name.startswith("refs/heads/")


def _record_trace_event(session: dict[str, object], event: dict[str, object]) -> None:
    event_type = event.get("event")
    if event_type == "start":
        argv = event.get("argv")
        if not isinstance(argv, list) or not all(isinstance(argument, str) for argument in argv):
            raise ValueError("Git Trace2 start event has invalid argv")
        session["argv"] = argv
    elif event_type == "cmd_name":
        command = event.get("name")
        if not isinstance(command, str):
            raise ValueError("Git Trace2 command event has invalid name")
        session["command"] = command
    elif event_type == "def_repo":
        worktree = event.get("worktree")
        if isinstance(worktree, str):
            session["worktree"] = worktree
    elif event_type == "exit":
        exit_code = event.get("code")
        if not isinstance(exit_code, int):
            raise ValueError("Git Trace2 exit event has invalid code")
        session["exit_code"] = exit_code


def _read_trace_sessions(trace_path: Path) -> dict[str, dict[str, object]]:
    sessions: dict[str, dict[str, object]] = {}
    for line in trace_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line:
            continue
        event = json.loads(line)
        if not isinstance(event, dict):
            raise ValueError("Git Trace2 event is not an object")
        session_id = event.get("sid")
        if not isinstance(session_id, str):
            raise ValueError("Git Trace2 event has no session id")
        _record_trace_event(sessions.setdefault(session_id, {}), event)
    return sessions


def _git_dir_argument(argv: list[str]) -> str | None:
    for index, argument in enumerate(argv):
        if argument.startswith("--git-dir="):
            return argument.split("=", 1)[1]
        if argument == "--git-dir" and index + 1 < len(argv):
            return argv[index + 1]
    return None


def _session_targets_project(session: dict[str, object]) -> bool:
    worktree = session.get("worktree")
    argv = session.get("argv")
    project_root = PROJECT_ROOT.resolve()
    if isinstance(worktree, str) and Path(worktree).resolve() == project_root:
        return True
    if not isinstance(argv, list):
        return False
    git_dir_argument = _git_dir_argument(argv)
    if git_dir_argument is None:
        return False
    git_dir = Path(git_dir_argument)
    if not git_dir.is_absolute():
        base = Path(worktree) if isinstance(worktree, str) else PROJECT_ROOT
        git_dir = base / git_dir
    return git_dir.resolve() == _project_git_dir()


def _session_has_plumbing_mutation(session: dict[str, object]) -> bool:
    exit_code = session.get("exit_code")
    if isinstance(exit_code, int) and exit_code != 0:
        return False
    command = session.get("command")
    argv = session.get("argv")
    if not isinstance(command, str) or not isinstance(argv, list):
        return False
    command_args = _command_args(argv, command)
    if command == "symbolic-ref":
        return _symbolic_ref_mutates_head(command_args)
    if command == "update-ref":
        return _update_ref_mutates_branch(command_args)
    return False


def _trace_has_project_plumbing_mutation(trace_path: Path) -> bool:
    """Detect project ref writes from plumbing commands that ignore reflog actions."""
    if not trace_path.exists():
        return False

    for session in _read_trace_sessions(trace_path).values():
        if _session_targets_project(session) and _session_has_plumbing_mutation(session):
            return True
    return False


def _check_head_change(
    before: str | None,
    after: str | None,
    reflog_action: str | None = None,
    trace_path: Path | None = None,
) -> None:
    """Fail for test-caused HEAD changes and warn for external commits."""
    if after is None:
        pytest.fail(
            "#2316: could not read repository HEAD after the test; refusing to "
            "treat an unreadable repository as a concurrent commit.",
            pytrace=False,
        )
    if before is None or before == after:
        return

    try:
        action_found = bool(reflog_action and _reflog_contains_action(reflog_action))
        plumbing_found = bool(trace_path and _trace_has_project_plumbing_mutation(trace_path))
    except (OSError, ValueError) as exc:
        pytest.fail(
            f"#2316: real repo HEAD changed ({before[:8]} -> {after[:8]}), "
            f"but the guard could not attribute the Git activity: {exc}",
            pytrace=False,
        )
    if action_found:
        pytest.fail(
            f"#2316: a test-launched Git command changed the REAL repo HEAD "
            f"({before[:8]} -> {after[:8]}). Run mutating Git commands only "
            "inside a repository created under tmp_path.",
            pytrace=False,
        )
    if plumbing_found:
        pytest.fail(
            f"#2316: a test-launched Git plumbing command changed the REAL repo "
            f"HEAD ({before[:8]} -> {after[:8]}). Run mutating Git commands only "
            "inside a repository created under tmp_path.",
            pytrace=False,
        )

    subject = _real_repo_head_subject()
    warnings.warn(
        f"#3109: real repo HEAD changed during this test's window "
        f"({before[:8]} -> {after[:8]}; new HEAD subject: {subject!r}). "
        "No test-launched Git mutation was recorded in the project repository, "
        "so this is a concurrent external commit in this worktree.",
        stacklevel=2,
    )


@pytest.fixture(autouse=True)
def _guard_real_repo_head() -> Iterator[None]:
    """Attribute project HEAD movement without blaming concurrent commits."""
    before = _real_repo_head()
    previous_env = {name: os.environ.get(name) for name in _TRACE_ENV_NAMES}
    attribution_token = uuid.uuid4().hex
    reflog_action = f"pytest-head-guard:{attribution_token}"
    trace_path = Path(tempfile.gettempdir()) / f"pytest-head-guard-{attribution_token}.json"
    os.environ["GIT_REFLOG_ACTION"] = reflog_action
    os.environ["GIT_TRACE2_EVENT"] = str(trace_path)
    try:
        yield
    finally:
        for name, value in previous_env.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
    try:
        _check_head_change(
            before,
            _real_repo_head(),
            reflog_action,
            trace_path,
        )
    finally:
        trace_path.unlink(missing_ok=True)
