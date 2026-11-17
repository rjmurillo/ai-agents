"""Git reads for sol-loop: the checkout's top level and critic freshness.

``gate`` refuses a fresh-critic file older than HEAD or than any uncommitted
change, because fixes stay uncommitted during the loop. Run logs and the
critic file itself are skipped: they are loop output, not reviewed code.
A checkout git cannot read (not a repository) is not checked.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def _git(cwd: Path, *args: str, strip: bool = True) -> str:
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except FileNotFoundError:
        return ""
    if proc.returncode != 0:
        return ""
    # Porcelain status lines start with a space (" M path"), so keep raw output there.
    return proc.stdout.strip() if strip else proc.stdout


def default_log_base(repo: Path) -> Path:
    """Anchor logs at the reviewed checkout's top level.

    Commit each run file with the branch it reviewed: a linked worktree is
    removed when its work ends. ``AI_AGENTS_ARTIFACT_ROOT`` overrides the root.
    This script never writes into a different checkout on its own.
    """
    top = _git(repo, "rev-parse", "--show-toplevel")
    return Path(top) if top else repo


def _newest_uncommitted_change(repo: Path, skip: tuple[Path, ...]) -> float:
    """Newest mtime among modified and untracked files, ignoring ``skip`` paths.

    Fixes made during the loop stay uncommitted (the skill does not push
    mid-loop), so HEAD alone would let a round-1 critic file pass round 2.
    Run logs and the critic file itself are skipped: they are loop output.
    """
    top = _git(repo, "rev-parse", "--show-toplevel")
    if not top:
        return 0.0
    newest = 0.0
    entries = _git(repo, "status", "--porcelain", "-z", "--untracked-files=all", strip=False).split(
        "\0"
    )
    index = 0
    while index < len(entries):
        entry = entries[index]
        index += 1
        if len(entry) < 4:
            continue
        if entry[0] in "RC":
            index += 1  # with -z, a rename or copy source path follows as its own entry
        path = (Path(top) / entry[3:]).resolve()
        if any(path == s or s in path.parents for s in skip) or not path.is_file():
            continue
        newest = max(newest, path.stat().st_mtime)
    return newest


def _critic_is_stale(repo: Path, critic: Path, log_dir: Path) -> bool:
    """True when the critic output predates HEAD or an uncommitted change."""
    head_time = _git(repo, "log", "-1", "--format=%ct", "HEAD")
    if not head_time.isdigit():
        return False
    newest = max(
        int(head_time), _newest_uncommitted_change(repo, (critic.resolve(), log_dir.resolve()))
    )
    return critic.stat().st_mtime < newest


def _repo_relative(repo: Path, finding: dict) -> dict:
    """Rewrite an absolute file path inside the checkout as a repo-relative one."""
    value = str(finding.get("file") or "")
    top = _git(repo, "rev-parse", "--show-toplevel")
    if not value.startswith("/") or not top:
        return finding
    try:
        return {
            **finding,
            "file": Path(value).resolve().relative_to(Path(top).resolve()).as_posix(),
        }
    except ValueError:
        return finding
