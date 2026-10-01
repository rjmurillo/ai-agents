"""Execute stage of the ADR-101 requirement 2a publisher (issue #5245).

Runs in the ``execute`` job: its own GitHub-hosted runner, ``contents: read``,
no environment, no secret. It is the only job that runs candidate code.

What it does, in order:

  1. Applies the same flag and event gate as every stage. Off means SKIP and
     nothing runs.
  2. Validates the head SHA, repository and pull request number from the event.
  3. Fetches the pull request head by its ref and refuses to continue unless the
     fetched commit IS the SHA the event named.
  4. Checks the head out into a scratch directory as a detached worktree of this
     base checkout. A worktree, not ``checkout-index``, because the repository's
     root ``conftest.py`` refuses to run in a tree whose HEAD is unreadable: a
     bare export errored every test at teardown (measured in a dry run).
  5. Replaces the scratch tree's pytest configuration with this base checkout's
     ``pyproject.toml``, removing a candidate ``pytest.ini``, ``tox.ini`` and
     ``setup.cfg`` that would outrank it, so a candidate cannot widen ``addopts``
     or narrow the test paths through configuration.
  6. Runs the base-owned harness argument vector with the scratch tree as the
     working directory and a scrubbed environment.

What its PASS means: the harness exited 0. It does not mean the tests ran or
passed. A candidate that controls the test process can make the harness exit 0
three measured ways (ADR-101 requirement 2b, open research). This stage never
claims otherwise, and the publisher's label says so.

Mirrors ``scripts/ci/verify_dispatch_closure.py`` ``materialize_head`` for the
fetch-by-ref step and the moved-head refusal. Its docstring, quoted: "The head
SHA comes from the event payload. It is fetched through the pull request ref and
the fetched commit must be that SHA: if the branch moved between the event and
this run the check aborts rather than verify a revision nobody named."

Different from ``materialize_head``: that function writes files with
``checkout-index`` and leaves no ``.git`` directory, because it reads the head as
data. This stage must RUN the head's tests, whose root ``conftest.py`` needs a
readable HEAD, so it uses a detached worktree. A moved head is a typed FAIL
``revision.moved`` here and the harness never runs.

Standard library only (``ci-scripts.md`` MUST 18).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from scripts.ci.adr101_publisher_inputs import (
    REASON_EXECUTION_FAILED,
    REASON_INPUT_INVALID,
    REASON_REVISION_MOVED,
    VALIDATOR,
    PublisherEnv,
    first_stop,
    gate_outcome,
    is_number,
    is_repository,
    is_sha,
)
from scripts.validation.evidence import (
    REASON_PR_UNRESOLVED,
    REASON_TIMEOUT,
    REASON_TOOL_ABSENT,
    CheckOutcome,
)

HARNESS_TIMEOUT_SECONDS = 2400
GIT_TIMEOUT_SECONDS = 300
_PULL_REF = "refs/pull/{number}/head"
_COMPETING_CONFIGS = (
    "pytest.ini",
    ".pytest.ini",
    "pytest.toml",
    ".pytest.toml",
    "tox.ini",
    "setup.cfg",
)
# A system or global gitconfig can register a filter driver (git-lfs) that
# checkout would run on head blobs when the head's .gitattributes names it.
_INERT_GIT = ("-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false")
_NO_SYSTEM_CONFIG = {"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null"}
# The candidate runs inside the harness. It receives these names and nothing
# else from this job's environment, so no token or event value reaches it.
_CHILD_ENV_ALLOWLIST = ("PATH", "HOME", "TMPDIR", "LANG", "LC_ALL", "UV_CACHE_DIR")

Runner = Callable[..., "subprocess.CompletedProcess[str]"]


class MaterializeError(Exception):
    """The head could not be fetched, or is not the commit the event named."""

    def __init__(self, message: str, *, moved: bool = False, blocked_reason: str = "") -> None:
        super().__init__(message)
        self.moved = moved
        self.blocked_reason = blocked_reason


def harness_argv(scratch: Path) -> list[str]:
    """The base-owned test invocation. The candidate supplies no part of it.

    ``-c`` names the base ``pyproject.toml`` copied into ``scratch`` and
    ``--rootdir`` pins the root, so pytest never searches the candidate's
    ``tests/`` directory or any ancestor for its own configuration file.
    """
    return [
        "uv", "run", "--frozen", "--no-config", "--extra", "dev", "--project", str(_tool_root()),
        "python", "-m", "pytest", "-q", "-p", "no:cacheprovider",
        "-c", str(scratch / "pyproject.toml"), "--rootdir", str(scratch),
        "-n", "auto", "--dist", "loadfile", "tests",
    ]  # fmt: skip


def _tool_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _git(cwd: Path, args: Sequence[str], env: Mapping[str, str], runner: Runner) -> str:
    try:
        result = runner(
            ["git", *_INERT_GIT, *args],
            cwd=cwd,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=GIT_TIMEOUT_SECONDS,
            env={**env, **_NO_SYSTEM_CONFIG},
        )
    except FileNotFoundError:
        raise MaterializeError("git not found", blocked_reason=REASON_TOOL_ABSENT) from None
    except subprocess.TimeoutExpired:
        raise MaterializeError(
            f"git {args[0]} exceeded {GIT_TIMEOUT_SECONDS}s", blocked_reason=REASON_TIMEOUT
        ) from None
    if result.returncode != 0:
        raise MaterializeError(f"git {args[0]} failed with exit {result.returncode}")
    return str(result.stdout).strip()


def materialize_head(
    tool_root: Path, pull_number: str, head_sha: str, dest: Path, runner: Runner = subprocess.run
) -> None:
    """Check the pull request head out into ``dest`` as a detached worktree, or raise.

    The head SHA comes from the event. It is fetched through the pull request
    ref, and the fetched commit must be that SHA: if the branch moved between
    the event and this run the stage aborts rather than test a revision nobody
    named. ``dest`` is a worktree of the base checkout's object store, so the
    repository's own tests find a readable HEAD (the root ``conftest.py`` guard
    refuses a tree without one). Hooks and filter drivers are disabled for every
    git call here.
    """
    env = dict(os.environ)
    ref = _PULL_REF.format(number=pull_number)
    fetch = ["fetch", "--no-tags", "--no-recurse-submodules", "--depth=1", "origin", ref]
    _git(tool_root, fetch, env, runner)
    fetched = _git(tool_root, ["rev-parse", "FETCH_HEAD"], env, runner)
    if fetched != head_sha:
        raise MaterializeError("pull request head moved after the event named it", moved=True)
    _git(tool_root, ["worktree", "add", "--detach", "--force", str(dest), head_sha], env, runner)


def _child_env(environ: Mapping[str, str]) -> dict[str, str]:
    kept = {name: environ[name] for name in _CHILD_ENV_ALLOWLIST if name in environ}
    return {**kept, "CI": "true", "PYTHONDONTWRITEBYTECODE": "1"}


def _validate(env: PublisherEnv) -> CheckOutcome | None:
    if not env.pull_number:
        return CheckOutcome.unknown(
            VALIDATOR, reason=REASON_PR_UNRESOLVED, detail="the event names no pull request"
        )
    problems = []
    if not is_sha(env.head_sha):
        problems.append("head SHA is not 40 lowercase hex characters")
    if not is_repository(env.repository):
        problems.append("repository is not owner/name")
    if not is_number(env.pull_number):
        problems.append("pull request number is not numeric")
    if not problems:
        return None
    return CheckOutcome.failed(
        VALIDATOR, reason=REASON_INPUT_INVALID, findings=len(problems), detail="; ".join(problems)
    )


def _run_harness(
    scratch: Path, environ: Mapping[str, str], runner: Runner
) -> CheckOutcome | None:
    """Run the harness. Return None when it exited 0, else the typed failure."""
    try:
        completed = runner(
            harness_argv(scratch),
            cwd=scratch,
            env=_child_env(environ),
            check=False,
            timeout=HARNESS_TIMEOUT_SECONDS,
        )
    except FileNotFoundError:
        return CheckOutcome.blocked(VALIDATOR, reason=REASON_TOOL_ABSENT, detail="uv not found")
    except subprocess.TimeoutExpired:
        return CheckOutcome.blocked(
            VALIDATOR, reason=REASON_TIMEOUT, detail=f"harness exceeded {HARNESS_TIMEOUT_SECONDS}s"
        )
    if completed.returncode == 0:
        return None
    return CheckOutcome.failed(
        VALIDATOR, reason=REASON_EXECUTION_FAILED, detail=f"harness exited {completed.returncode}"
    )


def _passed(head_sha: str) -> CheckOutcome:
    return CheckOutcome.passed(
        VALIDATOR,
        revision=head_sha,
        scope="candidate tests under the base-owned harness",
        detail="harness exited 0; whether tests ran is ADR-101 requirement 2b, open",
    )


def _remove(path: Path) -> None:
    """Remove a file, a symlink (not its target), or a directory (not its links)."""
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink(missing_ok=True)


def _install_base_pytest_config(tool_root: Path, scratch: Path) -> None:
    """Make the base ``pyproject.toml`` the only pytest configuration at the root.

    pytest takes the first of ``pytest.ini``, ``pyproject.toml``, ``tox.ini`` and
    ``setup.cfg`` that carries pytest settings, so a candidate ``pytest.ini``
    would outrank the base copy. Each is unlinked first. ``unlink`` removes a
    symlink and not its target, which matters because git checks a symlink out as
    a symlink, and copying onto one would write through it to a path outside the
    scratch tree.

    This does not stop a candidate ``conftest.py`` or a plugin it imports from
    changing results. That is the (2b) gap, accepted and open.

    Pytest is also pointed at this file with ``-c`` (see ``harness_argv``), so a
    configuration file under the candidate's ``tests/`` directory is not found.
    """
    for name in (*_COMPETING_CONFIGS, "pyproject.toml"):
        _remove(scratch / name)
    shutil.copyfile(tool_root / "pyproject.toml", scratch / "pyproject.toml")


def run_execute(
    env: PublisherEnv,
    environ: Mapping[str, str] | None = None,
    runner: Runner = subprocess.run,
    scratch_root: Path | None = None,
) -> CheckOutcome:
    """Run the execute stage and return its typed outcome. Never raises on input.

    This job holds no secret and binds no environment, so it cannot see whether
    the App key exists. Credential absence is the publish job's gate.
    """
    source = os.environ if environ is None else environ
    stop = first_stop(env, gate_outcome, _validate)
    if stop is not None:
        return stop
    tool_root = _tool_root()
    with tempfile.TemporaryDirectory(dir=scratch_root, prefix="adr101-") as parent:
        scratch = Path(parent) / "candidate"
        try:
            materialize_head(tool_root, env.pull_number, env.head_sha, scratch, runner)
        except MaterializeError as exc:
            if exc.blocked_reason:
                return CheckOutcome.blocked(VALIDATOR, reason=exc.blocked_reason, detail=str(exc))
            reason = REASON_REVISION_MOVED if exc.moved else REASON_EXECUTION_FAILED
            return CheckOutcome.failed(VALIDATOR, reason=reason, detail=str(exc))
        try:
            _install_base_pytest_config(tool_root, scratch)
        except OSError as exc:
            return CheckOutcome.failed(
                VALIDATOR,
                reason=REASON_EXECUTION_FAILED,
                detail=f"the base pytest config could not be installed ({type(exc).__name__})",
            )
        failure = _run_harness(scratch, source, runner)
    if failure is None:
        return _passed(env.head_sha)
    return failure
