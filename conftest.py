"""Repository-wide pytest safety guards."""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import uuid
import warnings
from collections.abc import Iterator
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent


def pytest_configure(config: pytest.Config) -> None:
    basetemp = getattr(config.option, "basetemp", None)
    if basetemp:
        os.environ["_PYTEST_BASETEMP"] = str(Path(os.fspath(basetemp)).resolve())


_GIT_ENV_OVERRIDES = {"GIT_COMMON_DIR", "GIT_DIR", "GIT_INDEX_FILE", "GIT_WORK_TREE"}
_TRACE_FILE_ENV_NAMES = ("GIT_TRACE2_EVENT", "GIT_TRACE_SETUP")
_TRACE_BLOCKED_ENV_NAMES = ("GIT_TRACE_REFS",)
_TRACE_ENV_NAMES = ("GIT_REFLOG_ACTION", *_TRACE_FILE_ENV_NAMES, *_TRACE_BLOCKED_ENV_NAMES)
_TRACE_LINE_PATTERN = re.compile(r"^\d{2}:\d{2}:\d{2}\.\d{6}\s+\S+:\d+\s+(?P<message>.*)$")
_REFLOG_EXPIRY_CONTINUATION_PATTERN = re.compile(r"^ \d+: -?\d+$")
_SETUP_GIT_DIR_PREFIX = "setup: git_dir: "
_SETUP_CWD_PREFIX = "setup: cwd: "


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
    """Return whether the project HEAD reflog contains this per-test action."""
    out = _run_git_capture(
        "reflog",
        "HEAD",
        "--format=%gs",
        f"--grep-reflog={action}",
        "-n",
        "1",
    )
    if out is None or out.returncode != 0:
        raise OSError("could not read project HEAD reflog")
    return bool(out.stdout.strip())


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


def _decode_trace_path(value: str) -> str:
    decoded: list[str] = []
    index = 0
    escapes = {"\\": "\\", "n": "\n", "r": "\r"}
    while index < len(value):
        character = value[index]
        if character != "\\" or index + 1 == len(value):
            decoded.append(character)
            index += 1
            continue
        next_character = value[index + 1]
        decoded.append(escapes.get(next_character, f"\\{next_character}"))
        index += 2
    return "".join(decoded)


def _record_ref_trace_line(session: dict[str, object], line: str) -> None:
    match = _TRACE_LINE_PATTERN.fullmatch(line)
    if match is None:
        raise ValueError("Git ref trace line has an unknown format")
    message = match.group("message")

    if message.startswith(_SETUP_GIT_DIR_PREFIX):
        session["git_dir"] = _decode_trace_path(message[len(_SETUP_GIT_DIR_PREFIX) :])
        return
    if message.startswith(_SETUP_CWD_PREFIX):
        session["cwd"] = _decode_trace_path(message[len(_SETUP_CWD_PREFIX) :])
        return


def _read_trace_sessions(trace_path: Path) -> dict[str, dict[str, object]]:
    sessions: dict[str, dict[str, object]] = {}
    current_session_id: str | None = None
    for line in trace_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line:
            continue
        if line.startswith("{"):
            event = json.loads(line)
            if not isinstance(event, dict):
                raise ValueError("Git Trace2 event is not an object")
            session_id = event.get("sid")
            if not isinstance(session_id, str):
                raise ValueError("Git Trace2 event has no session id")
            current_session_id = session_id
            _record_trace_event(sessions.setdefault(session_id, {}), event)
            continue
        if _REFLOG_EXPIRY_CONTINUATION_PATTERN.fullmatch(line):
            continue
        if current_session_id is None:
            raise ValueError("Git ref trace line has no Trace2 session")
        _record_ref_trace_line(sessions[current_session_id], line)
    return sessions


def _git_dir_argument(argv: list[str]) -> str | None:
    for index, argument in enumerate(argv):
        if argument.startswith("--git-dir="):
            return argument.split("=", 1)[1]
        if argument == "--git-dir" and index + 1 < len(argv):
            return argv[index + 1]
    return None


def _symbolic_ref_arguments(argv: list[str]) -> list[str]:
    """Return argv entries after the symbolic-ref subcommand token.

    Falls back to skipping only argv[0] when Git dispatches directly to a
    plumbing executable (e.g. Windows' git-symbolic-ref.exe) without a
    separate "symbolic-ref" token.
    """
    try:
        command_index = argv.index("symbolic-ref")
    except ValueError:
        return argv[1:]
    return argv[command_index + 1 :]


def _symbolic_ref_short_option_width(argument: str) -> int | None:
    if not argument.startswith("-") or argument.startswith("--") or len(argument) == 1:
        return None
    for index, flag in enumerate(argument[1:]):
        if flag in {"q", "d"}:
            continue
        if flag == "m":
            return 1 if index + 2 < len(argument) else 2
        return None
    return 1


def _parse_symbolic_ref_positionals(arguments: list[str]) -> list[str] | None:
    """Return symbolic-ref positionals, or None for an unsupported argv shape."""
    positionals: list[str] = []
    index = 0
    while index < len(arguments):
        argument = arguments[index]
        if argument in {"--", "--end-of-options"}:
            positionals.extend(arguments[index + 1 :])
            break
        if argument.startswith("--"):
            index += 1
            continue
        if argument.startswith("-"):
            width = _symbolic_ref_short_option_width(argument)
            if width is None or index + width > len(arguments):
                return None
            index += width
            continue
        positionals.append(argument)
        index += 1
    return positionals


def _successful_symbolic_ref_updates_head(session: dict[str, object]) -> bool:
    """Detect a successful `symbolic-ref` write that repoints project HEAD.

    Git 2.55 can omit the ref-transaction trace lines for symbolic-ref, so
    this inspects argv directly instead of relying on _record_ref_trace_line.
    """
    if session.get("command") != "symbolic-ref" or session.get("exit_code") != 0:
        return False
    argv = session.get("argv")
    if not isinstance(argv, list) or not argv or not all(isinstance(a, str) for a in argv):
        return False

    positionals = _parse_symbolic_ref_positionals(_symbolic_ref_arguments(argv))
    return positionals is not None and len(positionals) == 2 and positionals[0] == "HEAD"


def _session_targets_project(session: dict[str, object]) -> bool:
    worktree = session.get("worktree")
    argv = session.get("argv")
    project_root = PROJECT_ROOT.resolve()
    if isinstance(worktree, str) and Path(worktree).resolve() == project_root:
        return True
    setup_git_dir = session.get("git_dir")
    if isinstance(setup_git_dir, str):
        git_dir = Path(setup_git_dir)
        if not git_dir.is_absolute():
            cwd = session.get("cwd")
            base = Path(cwd) if isinstance(cwd, str) else PROJECT_ROOT
            git_dir = base / git_dir
        if git_dir.resolve() == _project_git_dir():
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


def _trace_has_project_head_mutation(trace_path: Path) -> bool:
    """Detect successful test-launched ref transactions that changed project HEAD."""
    if not trace_path.exists():
        return False

    for session in _read_trace_sessions(trace_path).values():
        if not _session_targets_project(session):
            continue
        if _successful_symbolic_ref_updates_head(session):
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
        trace_found = bool(trace_path and _trace_has_project_head_mutation(trace_path))
    except (OSError, ValueError) as exc:
        pytest.fail(
            f"#2316: real repo HEAD changed ({before[:8]} -> {after[:8]}), "
            f"but the guard could not attribute the Git activity: {exc}",
            pytrace=False,
        )
    if action_found or trace_found:
        pytest.fail(
            f"#2316: a test-launched Git command changed the REAL repo HEAD "
            f"({before[:8]} -> {after[:8]}). Run mutating Git commands only "
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
    trace_path = Path(tempfile.gettempdir()) / f"pytest-head-guard-{attribution_token}.log"
    os.environ["GIT_REFLOG_ACTION"] = reflog_action
    for name in _TRACE_FILE_ENV_NAMES:
        os.environ[name] = str(trace_path)
    # Keep ref tracing blocked. Git 2.43 rejects an explicit commit branch point
    # while GIT_TRACE_REFS is enabled.
    for name in _TRACE_BLOCKED_ENV_NAMES:
        os.environ.pop(name, None)
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
