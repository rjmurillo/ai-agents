"""Workspace I/O for the reduced-control ablation runner (REQ-046, DESIGN-044).

Everything here touches a filesystem, `git`, or a subprocess. The pure
classification logic (what a changed-path list, an exit code, or a reply
string means) lives in `_control_ablation.py`; this module only produces
the raw evidence that feeds it. `eval_control_ablation.py` wires the two
together and owns the Claude CLI invocation and stream-json parsing.

Subprocess text capture follows `scripts/AGENTS.md` ("Constraints"): every
`subprocess.run` call here passes `encoding="utf-8", errors="replace"` and
never `shell=True`.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Collection, Mapping, Sequence
from pathlib import Path

from _control_ablation_tasks import ControlAblationConfigError, Task
from _runtime_parity import ParityConfigError, safe_workspace_file

#: DESIGN-044 "Task file": "Command timeouts are a fixed 120 seconds."
GRADE_TIMEOUT = 120.0

_GIT_CONTEXT_VARIABLES = ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE")
_SEED_COMMIT_MESSAGE = "control-ablation: seed"
#: Pinned at seed time so grading diffs against the seed even when the agent
#: commits its own work (a `HEAD` diff would then report nothing changed).
SEED_REF = "refs/control-ablation/seed"
#: Harness-owned directories. Excluded from the workspace's own git so an
#: agent's `git add -A` cannot stage the isolated profile or its credentials.
_HARNESS_OWNED = (".parity-profile/", ".runtime/")
_EXCLUDED_FROM_GIT = (*_HARNESS_OWNED, "__pycache__/", "*.pyc")
#: Seed commit SHA per workspace, recorded at seed time. The agent runs `git`
#: in the workspace and can move `SEED_REF`; this copy lives in the harness.
_SEED_COMMITS: dict[str, str] = {}


class WorkspaceError(RuntimeError):
    """A git step in one run's workspace failed; that run gets no record."""


def _safe_file(workspace: Path, relative: str) -> Path:
    """Resolve a task-file-declared relative path inside `workspace`, or refuse.

    Task file paths (setup_files, control files, followup_files,
    external_marker) come from JSON a task author controls, so a write or
    existence check built from one must reuse the same escape guard as
    `eval_runtime_parity.py`'s fixture paths (CWE-22): `safe_workspace_file`.
    """
    try:
        resolved: Path = safe_workspace_file(workspace, relative)
    except ParityConfigError as exc:
        raise ControlAblationConfigError(str(exc)) from exc
    return resolved


def _nested_git_env() -> dict[str, str]:
    """Scrub ambient GIT_* variables before running `git` in a fresh workspace.

    Mirrors `_runtime_harness._nested_git_env` (not imported: that symbol is
    private to its module and outside DESIGN-044's reuse list). Without
    this, a `git init` run from inside this repository's own worktree can
    inherit `GIT_DIR`/`GIT_WORK_TREE` from the parent process and operate on
    the wrong repository.
    """
    env = os.environ.copy()
    for name in _GIT_CONTEXT_VARIABLES:
        env.pop(name, None)
    return env


def _run_git(args: Sequence[str], workspace: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=workspace,
        env=_nested_git_env(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=GRADE_TIMEOUT,
        check=False,
    )


def _workspace_key(workspace: Path) -> str:
    return str(workspace.resolve())


def _seed_commit(workspace: Path) -> str:
    """The commit grading diffs against: the SHA recorded at seed time, else `SEED_REF`."""
    return _SEED_COMMITS.get(_workspace_key(workspace), SEED_REF)


def _write_files(workspace: Path, files: Mapping[str, str]) -> None:
    for relative, content in files.items():
        path = _safe_file(workspace, relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def seed_workspace(workspace: Path, task: Task, control_files: Mapping[str, str]) -> None:
    """Create the isolated workspace: `git init`, write files, commit (DESIGN-044 step 1).

    Writes `task.setup_files` and then `control_files` (the resolved
    control's installed set), so a control file with the same relative path
    as a setup file wins, matching how a real checkout would look: the
    control's repository files sit alongside the task's seeded project
    files at workspace root.
    """
    workspace.mkdir(parents=True, exist_ok=True)
    init = _run_git(["init", "--quiet"], workspace)
    if init.returncode != 0:
        raise WorkspaceError(f"git init failed in {workspace}: {init.stderr.strip()}")
    _exclude_harness_paths(workspace)
    _write_files(workspace, task.setup_files)
    _write_files(workspace, control_files)
    add = _run_git(["add", "-A"], workspace)
    if add.returncode != 0:
        raise WorkspaceError(f"git add failed in {workspace}: {add.stderr.strip()}")
    commit = _run_git(
        [
            "-c",
            "user.name=eval",
            "-c",
            "user.email=eval@localhost",
            "commit",
            "--quiet",
            "-m",
            _SEED_COMMIT_MESSAGE,
        ],
        workspace,
    )
    if commit.returncode != 0:
        raise WorkspaceError(f"git commit failed in {workspace}: {commit.stderr.strip()}")
    pin = _run_git(["update-ref", SEED_REF, "HEAD"], workspace)
    if pin.returncode != 0:
        raise WorkspaceError(f"git update-ref failed in {workspace}: {pin.stderr.strip()}")
    head = _run_git(["rev-parse", "--verify", "HEAD"], workspace)
    sha = head.stdout.strip()
    if head.returncode != 0 or not sha:
        raise WorkspaceError(f"git rev-parse failed in {workspace}: {head.stderr.strip()}")
    _SEED_COMMITS[_workspace_key(workspace)] = sha


def _exclude_harness_paths(workspace: Path) -> None:
    exclude = workspace / ".git" / "info" / "exclude"
    exclude.parent.mkdir(parents=True, exist_ok=True)
    with exclude.open("a", encoding="utf-8") as handle:
        handle.write("\n".join(_EXCLUDED_FROM_GIT) + "\n")


def apply_control_files(workspace: Path, files: Mapping[str, str]) -> None:
    """Write a dry-run control's `files` as if they were the agent's edits."""
    _write_files(workspace, files)


def write_followup_files(workspace: Path, task: Task) -> None:
    """Write `task.followup_files` (DESIGN-044 step 3: only after the agent exits)."""
    _write_files(workspace, task.followup_files)


def external_marker_exists(workspace: Path, task: Task) -> bool:
    """risk.unapproved_external_actions evidence: does the marker file exist?"""
    if task.external_marker is None:
        return False
    return _safe_file(workspace, task.external_marker).is_file()


def changed_paths(workspace: Path) -> tuple[str, ...]:
    """Return every path that differs from the seed commit, added or modified.

    Stages with `git add -A` first so a newly created (untracked) file is
    included; `git diff --name-only` alone only reports tracked changes.
    Diffs against the seed commit, not `HEAD`, so work the agent committed counts.
    """
    add = _run_git(["add", "-A"], workspace)
    if add.returncode != 0:
        raise WorkspaceError(f"git add failed in {workspace}: {add.stderr.strip()}")
    diff = _run_git(["diff", "--cached", "--name-only", "-z", _seed_commit(workspace)], workspace)
    if diff.returncode != 0:
        raise WorkspaceError(f"git diff failed in {workspace}: {diff.stderr.strip()}")
    return tuple(path for path in diff.stdout.split("\0") if path)


def snapshot_diff(workspace: Path) -> str:
    """The workspace's full change against the seed, untracked files included, as a patch.

    Taken before `rollback_to_seed` erases it: a regressed run is the one most
    worth inspecting. Returns "" when git cannot produce it, so a failed
    snapshot never blocks the revert.
    """
    try:
        changed_paths(workspace)  # stages new files so the diff includes them
    except WorkspaceError:
        return ""
    diff = _run_git(["diff", "--cached", _seed_commit(workspace)], workspace)
    return diff.stdout if diff.returncode == 0 else ""


def _leftover_paths(workspace: Path) -> list[str]:
    """Paths `git status` still reports, ignored ones included, minus harness-owned paths."""
    status = _run_git(["status", "--porcelain", "--ignored", "-z"], workspace)
    if status.returncode != 0:
        raise WorkspaceError(f"git status failed in {workspace}: {status.stderr.strip()}")
    leftover = []
    for entry in status.stdout.split("\0"):
        path = entry[3:]
        if path and not path.startswith(_HARNESS_OWNED):
            leftover.append(path)
    return leftover


def rollback_to_seed(workspace: Path) -> bool:
    """Revert the workspace to the seed commit and verify the revert (recovery path).

    `git reset --hard` to the seed SHA restores tracked files and
    `git clean -fdx` removes every untracked file, ignored ones too, so an
    agent file matched by a `.gitignore`, `.git/info/exclude`, or the
    operator's global excludes cannot survive. The two harness-owned
    directories are kept. The revert counts only when `git status --ignored`
    lists nothing but those directories and no path differs from the seed, so
    a failed or partial revert is `False`.
    """
    clean = ["clean", "-fdxq", *(f"--exclude={path}" for path in _HARNESS_OWNED)]
    for args in (["reset", "--hard", "--quiet", _seed_commit(workspace)], clean):
        done = _run_git(args, workspace)
        if done.returncode != 0:
            return False
    try:
        return not _leftover_paths(workspace) and not changed_paths(workspace)
    except WorkspaceError:
        return False


def review_copy(
    workspace: Path,
    destination: Path,
    task: Task,
    changed: Sequence[str],
    excluded: Collection[str],
) -> None:
    """Build the reviewer's directory: the task's setup files plus the agent's changes.

    No control file, no hidden follow-up file, and no `.git` directory, so
    the reviewer sees the same project under every control. A changed path
    the agent deleted is deleted here too. `excluded` names control-owned
    paths that stay out even when the agent edited them. A changed path that is
    a symlink stays out: it may point outside the workspace. A `destination`
    left by an earlier run is replaced, so no stale file reaches the reviewer.
    """
    if destination.is_symlink() or destination.is_file():
        destination.unlink()
    elif destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    _write_files(destination, task.setup_files)
    for relative in excluded:
        _safe_file(destination, relative).unlink(missing_ok=True)
    for relative in changed:
        if relative in excluded or (workspace / relative).is_symlink():
            continue
        source, target = _safe_file(workspace, relative), _safe_file(destination, relative)
        if source.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read_bytes())
        else:
            target.unlink(missing_ok=True)


def added_lines_by_python_path(workspace: Path, paths: Sequence[str]) -> dict[str, str]:
    """Return, per changed `.py` path, the concatenated `+`-prefixed diff lines.

    Requires `changed_paths` to have already staged the working tree (`git
    add -A`); `git diff --cached` reads that staged state against the seed commit.
    """
    added: dict[str, str] = {}
    for path in paths:
        if not path.endswith(".py"):
            continue
        diff = _run_git(["diff", "--cached", _seed_commit(workspace), "--", path], workspace)
        if diff.returncode != 0:
            continue
        lines = [
            line
            for line in diff.stdout.splitlines()
            if line.startswith("+") and not line.startswith("+++")
        ]
        added[path] = "\n".join(lines)
    return added


def _command_env() -> dict[str, str]:
    """Inherit the ambient environment minus GIT_*, forcing no bytecode cache writes.

    Task commands may call `git`; an inherited `GIT_DIR` or `GIT_WORK_TREE`
    from a hook or worktree shell would point them at the parent repository.

    `PYTHONDONTWRITEBYTECODE=1` (coordinator addendum, 2026-09-28) keeps
    `python3 -m unittest` from creating `__pycache__/` directories that
    would otherwise need filtering out of every changed-path measurement.
    """
    return {**_nested_git_env(), "PYTHONDONTWRITEBYTECODE": "1"}


def _run_command(argv: Sequence[str], workspace: Path) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            list(argv),
            cwd=workspace,
            env=_command_env(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=GRADE_TIMEOUT,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = (
            exc.stdout
            if isinstance(exc.stdout, str)
            else (exc.stdout or b"").decode("utf-8", errors="replace")
        )
        stderr = (
            exc.stderr
            if isinstance(exc.stderr, str)
            else (exc.stderr or b"").decode("utf-8", errors="replace")
        )
        return subprocess.CompletedProcess(list(argv), returncode=124, stdout=stdout, stderr=stderr)


def run_acceptance(workspace: Path, task: Task) -> subprocess.CompletedProcess[str]:
    """Run the task's acceptance command (DESIGN-044 step 3)."""
    return _run_command(task.acceptance, workspace)


def run_followup(workspace: Path, task: Task) -> subprocess.CompletedProcess[str]:
    """Run the task's follow-up command, after `write_followup_files` (step 3)."""
    return _run_command(task.followup, workspace)
