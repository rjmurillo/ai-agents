"""Git reads for sol-loop: the checkout's top level and critic freshness.

``gate`` refuses a fresh-critic file older than HEAD, than the last move of
HEAD (a checkout or reset to an older commit), or than any uncommitted
change, because fixes stay uncommitted during the loop. Changes include
modified, untracked, deleted, and renamed paths: a deleted or renamed file
counts as the mtime of its nearest existing parent directory, because a
rename keeps the file's own old mtime. Run logs, the critic file itself, and
the review brief are skipped: they are loop input or output, not reviewed
code. A checkout git cannot read (not a repository) is not checked.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Iterator
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


def _is_skipped(path: Path, skip: tuple[Path, ...]) -> bool:
    return any(path == s or s in path.parents for s in skip)


def _dir_mtime(path: Path) -> float:
    """mtime of the nearest existing directory above ``path``.

    Deleting or renaming a file updates its directory's mtime, so this is the
    only trace a removed path leaves.
    """
    return next((p.stat().st_mtime for p in path.parents if p.is_dir()), 0.0)


def _entry_mtime(path: Path, source: Path | None, skip: tuple[Path, ...]) -> float:
    """Newest change time one porcelain entry implies, 0.0 when it is skipped.

    A file that is gone counts as its parent directory's mtime. A rename or
    copy (``source`` is its old path) also counts both parent directories,
    because a move keeps the file's own old mtime.
    """
    times = []
    if not _is_skipped(path, skip):
        if path.is_file():
            times.append(path.stat().st_mtime)
        elif not path.exists():
            times.append(_dir_mtime(path))
        if source is not None:
            times.append(_dir_mtime(path))
    if source is not None and not _is_skipped(source, skip):
        times.append(_dir_mtime(source))
    return max(times, default=0.0)


def _changed_paths(top: Path, raw: str) -> Iterator[tuple[Path, Path | None]]:
    """Yield (path, rename or copy source) for each ``status --porcelain -z`` entry."""
    entries = raw.split("\0")
    index = 0
    while index < len(entries):
        entry = entries[index]
        index += 1
        if len(entry) < 4:
            continue
        source = None
        if ("R" in entry[:2] or "C" in entry[:2]) and index < len(entries):
            # with -z, a rename or copy source path follows as its own entry
            source = (top / entries[index]).resolve()
            index += 1
        yield (top / entry[3:]).resolve(), source


def _newest_uncommitted_change(repo: Path, skip: tuple[Path, ...]) -> float:
    """Newest change time among modified, untracked, deleted, and renamed paths.

    Fixes made during the loop stay uncommitted (the skill does not push
    mid-loop), so HEAD alone would let a round-1 critic file pass round 2.
    Paths under ``skip`` (run logs, the critic file, the review brief) are
    loop input or output, not reviewed code, and are ignored.
    """
    top = _git(repo, "rev-parse", "--show-toplevel")
    if not top:
        return 0.0
    raw = _git(repo, "status", "--porcelain", "-z", "--untracked-files=all", strip=False)
    return max(
        (_entry_mtime(path, source, skip) for path, source in _changed_paths(Path(top), raw)),
        default=0.0,
    )


def _head_moved_time(repo: Path) -> int:
    """Unix time HEAD last moved, from the reflog; 0 when there is no readable reflog.

    A checkout or reset to an older commit leaves that commit's own time
    behind the critic's, so the commit time alone cannot see the move.
    """
    entry = _git(repo, "log", "-g", "-1", "--date=unix", "--format=%gd", "HEAD")
    match = re.fullmatch(r"HEAD@\{(\d+)\}", entry)
    return int(match.group(1)) if match else 0


def _critic_is_stale(
    repo: Path, critic: Path, log_dir: Path, extra_skip: tuple[Path, ...] = ()
) -> bool:
    """True when the critic output predates HEAD, a move of HEAD, or an uncommitted change.

    ``extra_skip`` names more loop-owned paths to ignore, such as the review brief.
    """
    head_time = _git(repo, "log", "-1", "--format=%ct", "HEAD")
    if not head_time.isdigit():
        return False
    skip = (critic.resolve(), log_dir.resolve(), *(p.resolve() for p in extra_skip))
    newest = max(int(head_time), _head_moved_time(repo), _newest_uncommitted_change(repo, skip))
    return critic.stat().st_mtime < newest


def resolve_commit(repo: Path, ref: str) -> str:
    """Full SHA of the commit ``ref`` names in ``repo``, or "" when it names none."""
    if not re.fullmatch(r"[0-9a-fA-F]{7,64}", ref):
        return ""
    return _git(repo, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")


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
