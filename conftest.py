"""Repository-wide pytest safety guards."""

from __future__ import annotations

import json
import os
import re
import stat
import subprocess
import tempfile
import uuid
import warnings
from collections.abc import Generator, Iterator
from pathlib import Path, PurePosixPath

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent

# Issue #5123: whether a test's call phase failed, keyed by node, so the
# teardown-time `_guard_real_repo_head` fixture can tell a real assertion
# failure apart from one caused by the repository moving under the test.
_CALL_FAILED_STASH_KEY: pytest.StashKey[bool] = pytest.StashKey()


def pytest_configure(config: pytest.Config) -> None:
    basetemp = getattr(config.option, "basetemp", None)
    if basetemp:
        os.environ["_PYTEST_BASETEMP"] = str(Path(os.fspath(basetemp)).resolve())


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(
    item: pytest.Item, call: pytest.CallInfo[None]
) -> Generator[None, pytest.TestReport, pytest.TestReport]:
    """Stash the call-phase outcome so fixtures can see it during teardown.

    Fixture teardown code runs after the test body regardless of whether it
    passed or failed, but it has no direct way to observe that outcome. The
    stash is the documented pytest mechanism for a hook to hand fixtures data
    keyed by test node (https://docs.pytest.org/en/stable/reference/reference.html#pytest.Item.stash).
    """
    report = yield
    if call.when == "call":
        item.stash[_CALL_FAILED_STASH_KEY] = report.failed
    return report


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
    """Project git dir: `.git/` itself, or the gitdir a worktree's `.git` file points at."""
    dot_git = PROJECT_ROOT / ".git"
    try:
        if stat.S_ISDIR(dot_git.stat().st_mode):
            return dot_git.resolve()
        git_dir_line = dot_git.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError) as exc:
        raise OSError("could not resolve project git directory") from exc
    prefix = "gitdir:"
    if not git_dir_line.startswith(prefix):
        raise OSError("project .git file has no gitdir entry")
    git_dir = Path(git_dir_line[len(prefix) :].strip())
    if not git_dir.is_absolute():
        git_dir = PROJECT_ROOT / git_dir
    return git_dir.resolve()


class _HeadFastPathUnresolvedError(Exception):
    """Fast path cannot prove HEAD; caller falls back to `git rev-parse HEAD`."""


_OBJECT_ID_PATTERN = re.compile(r"^[0-9a-f]{40}$|^[0-9a-f]{64}$")  # hex object id, man git-config
_SYMBOLIC_HEAD_PATTERN = re.compile(r"^ref:\s*(\S+)$")  # e.g. "ref: refs/heads/main"

# CWE-22, git-check-ref-format(1) rules 4 and 10: a ref name never contains ":" or "\"
# anywhere. Rejecting both closes traversal forms `PurePosixPath` cannot see -- "\" segments
# and UNC (`\\server\share`) -- plus Windows drive syntax (`C:\Windows`, `C:foo`), which
# `PureWindowsPath.joinpath` would treat as a new anchor that discards the accumulated path.
_UNSAFE_REF_NAME_CHARACTERS = frozenset("\\:")


def _is_safe_ref_name(ref_name: str) -> bool:
    """CWE-22 guard: accept only a `refs/heads/` branch target, before it is joined onto a
    filesystem path. `man gitrepository-layout`'s `refs` entry lists `refs/bisect`,
    `refs/rewritten`, and `refs/worktree` as per-worktree namespaces outside the shared
    `common_dir` `_resolve_ref` reads from, so anything else falls back to Git as unproven.
    """
    if not ref_name.startswith("refs/heads/"):
        return False
    if any(character in ref_name for character in _UNSAFE_REF_NAME_CHARACTERS):
        return False
    candidate = PurePosixPath(ref_name)
    return not candidate.is_absolute() and ".." not in candidate.parts


def _fast_path_stat_mode(path: Path, error: str) -> int | None:
    """`path`'s `stat().st_mode`, or None if absent.

    Only `FileNotFoundError` means absent. `Path.exists()`/`is_dir()`/`is_file()` swallow every
    `OSError` into False (`genericpath`, Python 3.14 stdlib), so an unreadable path would read
    as "not there"; here any other `OSError` raises and the caller falls back to Git instead.
    """
    try:
        return path.stat().st_mode
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise _HeadFastPathUnresolvedError(error) from exc


def _read_optional_text(path: Path, error: str) -> str | None:
    """`path`'s UTF-8 text, or None if absent (same absent/unreadable split as
    `_fast_path_stat_mode`). Non-UTF-8 content (`UnicodeError`, e.g. `UnicodeDecodeError`) is
    unproven, not absent: it raises rather than misreading foreign-encoded metadata as
    missing."""
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except (OSError, UnicodeError) as exc:
        raise _HeadFastPathUnresolvedError(error) from exc


def _common_git_dir(git_dir: Path) -> Path:
    """Resolve `git_dir`'s shared ref-storage dir via its `commondir` file (linked worktrees)."""
    raw = _read_optional_text(git_dir / "commondir", "could not read commondir file")
    if raw is None:
        return git_dir
    if not (target := raw.strip()):
        raise _HeadFastPathUnresolvedError("commondir file is empty")
    common_dir = (git_dir / target).resolve()  # an absolute `target` replaces `git_dir`
    mode = _fast_path_stat_mode(common_dir, "commondir target is not accessible")
    if mode is None or not stat.S_ISDIR(mode):
        raise _HeadFastPathUnresolvedError("commondir target does not exist")
    return common_dir


def _resolve_ref(common_dir: Path, ref_name: str) -> str | None:
    """Object id for `ref_name`'s loose ref file; None only for a genuinely unborn ref.

    Never scans `packed-refs`: this runs in every test's autouse fixture, and parsing it to
    find one ref costs an O(n) scan of every packed ref per test. A `packed-refs` file
    existing makes the ref unprovable here, so we raise and fall back to Git; no such file
    proves the ref absent everywhere at O(1) -- legal unborn HEAD (`man gitrepository-layout`,
    `HEAD`: "legal if the named branch name does not (yet) exist").
    """
    ref_path = common_dir.joinpath(*ref_name.split("/"))
    content = _read_optional_text(ref_path, "could not read loose ref file")
    if content is not None:
        content = content.strip()
        if not _OBJECT_ID_PATTERN.match(content):
            raise _HeadFastPathUnresolvedError("loose ref file does not hold a plain object id")
        return content
    packed_refs_mode = _fast_path_stat_mode(common_dir / "packed-refs", "packed-refs unreadable")
    if packed_refs_mode is not None:
        raise _HeadFastPathUnresolvedError("ref may be packed; not scanning packed-refs")
    return None


def _direct_read_repo_head() -> str | None:
    """Resolve HEAD via direct filesystem reads: no subprocess for proven cases.

    Raises `_HeadFastPathUnresolvedError` for anything unproven (reftable, malformed data, a
    packed-only ref, any read failure) so the caller falls back to `git rev-parse HEAD`; `None`
    means legal unborn HEAD. The reftable check runs first because such repos keep a dummy
    `refs/heads/.invalid` HEAD (reftable.adoc, git/git) that would otherwise misread as unborn.
    """
    try:
        git_dir = _project_git_dir()
    except OSError as exc:
        raise _HeadFastPathUnresolvedError("could not resolve project git directory") from exc
    common_dir = _common_git_dir(git_dir)
    if _fast_path_stat_mode(common_dir / "reftable", "reftable directory unreadable") is not None:
        raise _HeadFastPathUnresolvedError("repository uses reftable ref storage")
    head_content = _read_optional_text(git_dir / "HEAD", "could not read HEAD file")
    if head_content is None:
        raise _HeadFastPathUnresolvedError("could not read HEAD file")
    head_content = head_content.strip()

    if _OBJECT_ID_PATTERN.match(head_content):
        return head_content  # detached HEAD

    symbolic_match = _SYMBOLIC_HEAD_PATTERN.match(head_content)
    if symbolic_match is None:
        raise _HeadFastPathUnresolvedError("HEAD file content is not a recognized shape")

    ref_name = symbolic_match.group(1)
    if not _is_safe_ref_name(ref_name):
        raise _HeadFastPathUnresolvedError("HEAD ref name is not a safe refs/heads/ path")

    return _resolve_ref(common_dir, ref_name)  # None => unborn HEAD


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
    try:
        return _direct_read_repo_head()
    except _HeadFastPathUnresolvedError:
        pass  # unproven case: fail closed to the subprocess, never guess.
    out = _run_git_capture("rev-parse", "HEAD")
    return out.stdout.strip() if out is not None and out.returncode == 0 else None


def _real_repo_head_subject() -> str:
    """Return the current HEAD commit subject, evidence for a concurrent commit."""
    out = _run_git_capture("log", "-1", "--format=%s")
    return out.stdout.strip() if out is not None and out.returncode == 0 else "<unknown>"


def _reflog_contains_action(action: str) -> bool:
    """Return whether the project HEAD reflog contains this per-test action."""
    out = _run_git_capture("reflog", "HEAD", "--format=%gs", f"--grep-reflog={action}", "-n", "1")
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


def _is_project_git_dir(candidate: str, base: object) -> bool:
    """Whether `candidate` -- absolute, or relative to `base` -- is the project git dir."""
    root = Path(base) if isinstance(base, str) else PROJECT_ROOT
    return (root / candidate).resolve() == _project_git_dir()


def _session_targets_project(session: dict[str, object]) -> bool:
    worktree = session.get("worktree")
    if isinstance(worktree, str) and Path(worktree).resolve() == PROJECT_ROOT.resolve():
        return True
    setup_git_dir = session.get("git_dir")
    if isinstance(setup_git_dir, str) and _is_project_git_dir(setup_git_dir, session.get("cwd")):
        return True
    argv = session.get("argv")
    if not isinstance(argv, list):
        return False
    git_dir_argument = _git_dir_argument(argv)
    return git_dir_argument is not None and _is_project_git_dir(git_dir_argument, worktree)


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
    *,
    call_failed: bool = False,
) -> None:
    """Fail for test-caused HEAD changes; warn or fail for external commits.

    A concurrent external commit (issue #3109) only warns when the test
    itself passed: the result is still trustworthy, and most tests never read
    git state at all. When the test's own call phase already failed,
    ``call_failed`` escalates the same detection to a distinct, greppable
    failure (issue #5123) instead of a warning that is easy to miss in a
    28,000-item run. Without the escalation, a fixture whose assertions
    derive from live repo state fails with a plain, misleading AssertionError
    that sends the reader hunting for a defect that is not there; the
    original failure survives in the run (this adds a teardown-phase ERROR,
    it does not replace the CALL-phase FAILED entry pytest already recorded).
    """
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
    concurrent_commit_detail = (
        f"real repo HEAD changed during this test's window "
        f"({before[:8]} -> {after[:8]}; new HEAD subject: {subject!r}). "
        "No test-launched Git mutation was recorded in the project repository, "
        "so this is a concurrent external commit in this worktree."
    )
    if call_failed:
        pytest.fail(
            f"#5123: {concurrent_commit_detail} The repository moved under "
            "this test's window while the test also failed, but that is "
            "correlation, not proof: this autouse fixture cannot tell "
            "whether this specific test actually read live Git state, so "
            "the failure above may not be meaningful. Before debugging it "
            "as a code defect, wait for the in-flight push or commit in "
            "this worktree to finish and re-run: if the failure "
            "disappears, it was this race.",
            pytrace=False,
        )
    warnings.warn(f"#3109: {concurrent_commit_detail}", stacklevel=2)


@pytest.fixture(autouse=True)
def _guard_real_repo_head(request: pytest.FixtureRequest) -> Iterator[None]:
    """Attribute project HEAD movement without blaming concurrent commits.

    ``request`` MUST NOT carry a default. pytest's fixture-argument scanner
    (``_pytest.compat.getfuncargnames``) excludes any parameter that has a
    default value from the set of fixtures it injects, so a defaulted
    ``request`` silently stays unset (``None``) on every real test run: the
    call_failed lookup below never runs, and the issue #5123 escalation this
    fixture exists to provide never fires. Confirmed empirically (issue #5123
    PR #5287 review): a defaulted ``request`` parameter on an autouse fixture
    measurably never receives the injected value. Callers that drive this
    generator directly via ``__wrapped__()`` (the head-guard test suite) MUST
    pass a request-like object explicitly; there is no default to fall back to.
    """
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
    call_failed = request.node.stash.get(_CALL_FAILED_STASH_KEY, False)
    try:
        _check_head_change(
            before,
            _real_repo_head(),
            reflog_action,
            trace_path,
            call_failed=call_failed,
        )
    finally:
        trace_path.unlink(missing_ok=True)
