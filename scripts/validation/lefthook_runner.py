#!/usr/bin/env python3
"""Resolve and run Lefthook for the generated Git hook shims (issue #5431).

`lefthook.yml` sets ``lefthook: python3 scripts/validation/lefthook_runner.py``.
Lefthook bakes that string into ``.git/hooks/*`` as::

    elif test -n "python3 scripts/validation/lefthook_runner.py"
    then
      python3 scripts/validation/lefthook_runner.py "$@"

The ``test -n "<literal>"`` is always true (verified against a generated
shim), so no fallback below it in the shim ever runs. This program owns the
fallback instead: it tries the pinned runtime first, then a locally installed
binary, then fails with a diagnosis.

Resolution order:

1. ``uv run --frozen lefthook`` when a ``version`` probe exits 0. The probe
   separates "uv cannot resolve Lefthook" from "a hook job failed", because
   both surface as a non-zero exit from the real run.
2. ``lefthook`` on PATH, then ``node_modules/.bin/lefthook`` in the repo.
3. No candidate: print a diagnosis to stderr and exit 3.

``LEFTHOOK_BIN`` is handled by the shim before this program runs, so it is not
read here. Bypass switches stay forbidden by ADR-086 and are not offered.

Pre-push file list (issue #6884): Lefthook skips every pre-push job, the
ref guards included, when ``git diff HEAD @{push}`` is empty. For ``run
pre-push`` this program reads the ref lines git writes to stdin, asks
``push_file_list.py`` for the files of the refs being pushed, and passes them
as ``--file`` arguments. The ref lines are replayed to Lefthook unchanged. When
the list cannot be built the push stops with exit 1. It never skips.

Delete-only pushes: a delete pushes no code, so jobs that inspect the working
tree can only block cleanup. When every ref line is a delete and the caller
passed no ``--job``, ``--tag``, ``--command``, or file flag, this program adds
``--tag ref-guard`` and prints one stderr line. ``lefthook.yml`` tags the jobs
that guard refs and repository state, so it stays the one source of truth for
what runs (ADR-086).
The ref guards, including the protected-branch check, still run. A push that
mixes a delete with an update, or has an empty stdin, runs every job as before.

Failure report (issue #6734, item 5): ``run <hook>`` goes through
``lefthook_failure_report.py``, which names the failed stage and job and prints a
rerun command.

Exit codes: the child's exit status when a runner started, 1 when the pre-push
file list cannot be built, 3 (external) when no runner is available.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from lefthook_failure_report import (  # noqa: E402
    ChildStartError,
    hook_name,
    recorded_stdin,
    run_hook_with_report,
    should_report,
)
from push_file_list import (  # noqa: E402
    PushFileListError,
    caller_chose_files,
    lefthook_file_args,
    parse_ref_lines,
)

EXIT_FILE_LIST = 1
EXIT_UNAVAILABLE = 3
PROBE_TIMEOUT_SECONDS = 60
_UV_RUNNER = ("uv", "run", "--frozen", "lefthook")
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPAIR_COMMAND = "uv sync --frozen --extra dev"

DIAGNOSIS = f"""\
lefthook_runner: Lefthook itself is unavailable. Your change is not the cause.
Tried: 'uv run --frozen lefthook version' (failed or uv missing), then
'lefthook' on PATH and node_modules/.bin/lefthook (not found).
Bypassing the hook (--no-verify, LEFTHOOK=0, LEFTHOOK_BIN, LEFTHOOK_EXCLUDE)
is forbidden by ADR-086. Repair the runtime instead:
  1. Restore the locked environment while online: {REPAIR_COMMAND}
  2. Or install a Lefthook binary onto PATH, then retry the git command.
"""


def _uv_is_ready() -> bool:
    """Return True when ``uv run --frozen lefthook version`` exits 0."""
    if shutil.which("uv") is None:
        return False
    try:
        probe = subprocess.run(
            [*_UV_RUNNER, "version"],
            capture_output=True,
            timeout=PROBE_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return probe.returncode == 0


def _local_binary(project_root: Path) -> str | None:
    """Return a Lefthook binary from PATH or the repo's node_modules, else None."""
    on_path = shutil.which("lefthook")
    if on_path is not None:
        return on_path
    return shutil.which("lefthook", path=str(project_root / "node_modules" / ".bin"))


def resolve_command(project_root: Path = _PROJECT_ROOT) -> list[str] | None:
    """Return the argv prefix that runs Lefthook, or None when none works."""
    if _uv_is_ready():
        return list(_UV_RUNNER)
    binary = _local_binary(project_root)
    return [binary] if binary is not None else None


def _cannot_start(command: list[str], error: Exception) -> int:
    """Report that the Lefthook child did not start, and return the exit code."""
    sys.stderr.write(f"lefthook_runner: cannot start {command[0]}: {error}\n{DIAGNOSIS}")
    return EXIT_UNAVAILABLE


# Lefthook ``run`` flags that take a separate value.
_VALUE_FLAGS = frozenset({"--job", "--tag", "--command", "--exclude", "--file"})


def _split_hook_arguments(rest: list[str], from_git: bool) -> tuple[list[str], list[str]]:
    """Split the arguments after ``run pre-push`` into Lefthook flags and git's arguments.

    Git passes a pre-push hook exactly two arguments, the remote name and its
    URL, after any flags a rerun adds. Taking them from the end, not by their
    shape, keeps a remote named like a flag (``git remote add -- --job x``)
    from being read as one. ``from_git`` is True when stdin carries ref lines,
    which only git or a printed rerun sends, so the last two are always git's.
    Otherwise a trailing value flag such as ``--job x`` marks a manual call.
    """
    if len(rest) >= 2 and (from_git or rest[-2] not in _VALUE_FLAGS):
        return rest[:-2], rest[-2:]
    return rest, []


# The lefthook.yml tag on the pre-push jobs that guard refs and repository
# state, not tree content. A push that only deletes refs runs just those jobs.
# tests/test_lefthook_delete_only.py lists every pre-push job as a ref guard or a
# tree job, so a new job fails a test until someone puts it in one list.
REF_GUARD_TAG = "ref-guard"
_SCOPE_FLAGS = ("--job", "--tag", "--command")


def _deleted_ref_count(stdin_bytes: bytes, flags: list[str]) -> int:
    """Return how many refs a delete-only push deletes, or 0 when the full hook runs.

    A delete pushes no code, so a job that inspects the working tree can only
    block cleanup. Returns 0 for any ref line that updates or creates a ref,
    and when the caller already chose jobs.
    """
    if any(item == flag or item.startswith(f"{flag}=") for item in flags for flag in _SCOPE_FLAGS):
        return 0
    updates = parse_ref_lines(stdin_bytes)
    if not all(update.is_delete for update in updates):
        return 0
    return len(updates)


def _child_arguments(arguments: list[str], stdin_bytes: bytes | None) -> list[str]:
    """Return what Lefthook receives: for pre-push, the file list and a ``--`` boundary.

    ``--`` ends Lefthook's flags, so git's arguments always reach ``{1}`` and
    ``{2}`` and never act as a flag. With an empty stdin there is no push and
    no file list. A push that only deletes refs also gets ``--tag ref-guard``
    and one stderr line that says so.
    Raises :class:`PushFileListError` when the list cannot be built.
    """
    if hook_name(arguments) != "pre-push":
        return arguments
    flags, git_arguments = _split_hook_arguments(arguments[2:], bool(stdin_bytes))
    file_args: list[str] = []
    tag_args: list[str] = []
    if stdin_bytes and not caller_chose_files(flags):
        remote = git_arguments[0] if git_arguments else None
        file_args = lefthook_file_args(stdin_bytes, remote)
        deleted = _deleted_ref_count(stdin_bytes, flags)
        if deleted:
            sys.stderr.write(
                "lefthook_runner: pre-push skipped the tree jobs because the push only "
                f"deletes refs ({deleted}). Only jobs tagged {REF_GUARD_TAG} run.\n"
            )
            tag_args = ["--tag", REF_GUARD_TAG]
    boundary = ["--", *git_arguments] if git_arguments else []
    return [*arguments[:2], *file_args, *tag_args, *flags, *boundary]


# The command the shim runs, from lefthook.yml. Git hooks run at the repository root.
RUNNER_COMMAND = ("python3", "scripts/validation/lefthook_runner.py")


def _rerun_command(arguments: list[str], command: list[str]) -> list[str]:
    """Return the command a printed rerun uses: this runner for pre-push, else Lefthook."""
    return list(RUNNER_COMMAND) if hook_name(arguments) == "pre-push" else command


def main(argv: list[str] | None = None) -> int:
    """Run Lefthook with ``argv`` through the first working runner."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    command = resolve_command()
    if command is None:
        sys.stderr.write(DIAGNOSIS)
        return EXIT_UNAVAILABLE
    stdin_bytes = recorded_stdin(hook_name(arguments))
    try:
        child_arguments = _child_arguments(arguments, stdin_bytes)
    except PushFileListError as error:
        sys.stderr.write(
            f"lefthook_runner: pre-push stopped. The pushed file list cannot be built: "
            f"{error}\nNo pre-push check ran, so the push is refused.\n"
        )
        return EXIT_FILE_LIST
    if should_report(arguments):
        try:
            reported: int = run_hook_with_report(
                command,
                arguments,
                stdin_bytes,
                child_arguments,
                _rerun_command(arguments, command),
            )
        except ChildStartError as error:
            return _cannot_start(command, error)
        return reported
    try:
        sys.stdout.flush()
        return subprocess.run(
            [*command, *child_arguments], input=stdin_bytes, check=False
        ).returncode
    except OSError as error:
        return _cannot_start(command, error)


if __name__ == "__main__":
    sys.exit(main())
