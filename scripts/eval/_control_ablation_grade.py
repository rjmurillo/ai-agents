"""Workspace I/O for the reduced-control ablation runner (REQ-043, DESIGN-041).

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
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path

from _control_ablation import ControlAblationConfigError, Task
from _runtime_parity import ParityConfigError, safe_workspace_file

#: DESIGN-041 "Task file": "Command timeouts are a fixed 120 seconds."
GRADE_TIMEOUT = 120.0

_GIT_CONTEXT_VARIABLES = ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE")
_SEED_COMMIT_MESSAGE = "control-ablation: seed"


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
    private to its module and outside DESIGN-041's reuse list). Without
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
        timeout=30,
        check=False,
    )


def _write_files(workspace: Path, files: Mapping[str, str]) -> None:
    for relative, content in files.items():
        path = _safe_file(workspace, relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def seed_workspace(workspace: Path, task: Task, control_files: Mapping[str, str]) -> None:
    """Create the isolated workspace: `git init`, write files, commit (DESIGN-041 step 1).

    Writes `task.setup_files` and then `control_files` (the resolved
    control's installed set), so a control file with the same relative path
    as a setup file wins, matching how a real checkout would look: the
    control's repository files sit alongside the task's seeded project
    files at workspace root.
    """
    workspace.mkdir(parents=True, exist_ok=True)
    init = _run_git(["init", "--quiet"], workspace)
    if init.returncode != 0:
        raise RuntimeError(f"git init failed in {workspace}: {init.stderr.strip()}")
    _write_files(workspace, task.setup_files)
    _write_files(workspace, control_files)
    add = _run_git(["add", "-A"], workspace)
    if add.returncode != 0:
        raise RuntimeError(f"git add failed in {workspace}: {add.stderr.strip()}")
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
        raise RuntimeError(f"git commit failed in {workspace}: {commit.stderr.strip()}")


def apply_control_files(workspace: Path, files: Mapping[str, str]) -> None:
    """Write a dry-run control's `files` as if they were the agent's edits."""
    _write_files(workspace, files)


def write_followup_files(workspace: Path, task: Task) -> None:
    """Write `task.followup_files` (DESIGN-041 step 3: only after the agent exits)."""
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
    """
    add = _run_git(["add", "-A"], workspace)
    if add.returncode != 0:
        raise RuntimeError(f"git add failed in {workspace}: {add.stderr.strip()}")
    diff = _run_git(["diff", "--cached", "--name-only", "-z", "HEAD"], workspace)
    if diff.returncode != 0:
        raise RuntimeError(f"git diff failed in {workspace}: {diff.stderr.strip()}")
    return tuple(path for path in diff.stdout.split("\0") if path)


def added_lines_by_python_path(
    workspace: Path, paths: Sequence[str]
) -> dict[str, str]:
    """Return, per changed `.py` path, the concatenated `+`-prefixed diff lines.

    Requires `changed_paths` to have already staged the working tree (`git
    add -A`); `git diff --cached` reads that staged state against `HEAD`.
    """
    added: dict[str, str] = {}
    for path in paths:
        if not path.endswith(".py"):
            continue
        diff = _run_git(["diff", "--cached", "--", path], workspace)
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
    """Inherit the ambient environment, forcing no bytecode cache writes.

    `PYTHONDONTWRITEBYTECODE=1` (coordinator addendum, 2026-09-28) keeps
    `python3 -m unittest` from creating `__pycache__/` directories that
    would otherwise need filtering out of every changed-path measurement.
    """
    return {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}


def _run_command(
    argv: Sequence[str], workspace: Path
) -> subprocess.CompletedProcess[str]:
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
        stdout = exc.stdout if isinstance(exc.stdout, str) else (exc.stdout or b"").decode(
            "utf-8", errors="replace"
        )
        stderr = exc.stderr if isinstance(exc.stderr, str) else (exc.stderr or b"").decode(
            "utf-8", errors="replace"
        )
        return subprocess.CompletedProcess(list(argv), returncode=124, stdout=stdout, stderr=stderr)


def run_acceptance(workspace: Path, task: Task) -> subprocess.CompletedProcess[str]:
    """Run the task's acceptance command (DESIGN-041 step 3)."""
    return _run_command(task.acceptance, workspace)


def run_followup(workspace: Path, task: Task) -> subprocess.CompletedProcess[str]:
    """Run the task's follow-up command, after `write_followup_files` (step 3)."""
    return _run_command(task.followup, workspace)
