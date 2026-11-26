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

import os
import re
import stat
import subprocess
from collections.abc import Iterator
from pathlib import Path, PureWindowsPath

# A Windows absolute path, optionally behind a URL-style slash: C:\x, C:/x, /C:/x.
_WINDOWS_ABSOLUTE = re.compile(r"^/?([A-Za-z]:[\\/].*)$")

# Variables that point git at a repository other than ``cwd``. Inherited, they
# make a read of checkout A answer for checkout B.
_GIT_REPO_VARS = frozenset(
    {
        "GIT_DIR",
        "GIT_WORK_TREE",
        "GIT_INDEX_FILE",
        "GIT_COMMON_DIR",
        "GIT_OBJECT_DIRECTORY",
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_NAMESPACE",
        "GIT_PREFIX",
    }
)


def _git_env() -> dict[str, str]:
    """The current environment minus the variables that redirect git to another repository."""
    return {k: v for k, v in os.environ.items() if k not in _GIT_REPO_VARS}


def _git(cwd: Path, *args: str, strip: bool = True) -> str:
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=cwd,
            env=_git_env(),
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


def _is_skipped_entry(path: Path, skip: tuple[Path, ...]) -> bool:
    """Skip-list test on the entry itself: resolve its directory, never a final symlink."""
    return _is_skipped(path.parent.resolve() / path.name, skip)


def _entry_mtime(path: Path, source: Path | None, skip: tuple[Path, ...]) -> float:
    """Newest change time one porcelain entry implies, 0.0 when it is skipped.

    ``path`` and ``source`` are lexical, so a symlink counts its own mtime
    (``lstat``), not its target's: retargeting a link to an old file is a
    change. A path that is gone counts as its parent directory's mtime. A
    rename or copy (``source`` is its old path) also counts both parent
    directories, because a move keeps the file's own old mtime.
    """
    times = []
    if not _is_skipped_entry(path, skip):
        try:
            info = os.lstat(path)
        except OSError:
            times.append(_dir_mtime(path))
        else:
            if not stat.S_ISDIR(info.st_mode):
                times.append(info.st_mtime)
        if source is not None:
            times.append(_dir_mtime(path))
    if source is not None and not _is_skipped_entry(source, skip):
        times.append(_dir_mtime(source))
    return max(times, default=0.0)


def _changed_paths(top: Path, raw: str) -> Iterator[tuple[Path, Path | None]]:
    """Yield lexical (path, rename or copy source) for each ``status --porcelain -z`` entry."""
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
            source = top / entries[index]
            index += 1
        yield top / entry[3:], source


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

    Commit and reflog times are whole seconds, so a critic written in the same
    second as one of them cannot be proven newer and counts as stale: the
    comparison truncates the critic's mtime. File mtimes keep their fraction.
    ``extra_skip`` names more loop-owned paths to ignore, such as the review brief.
    """
    head_time = _git(repo, "log", "-1", "--format=%ct", "HEAD")
    if not head_time.isdigit():
        return False
    skip = (critic.resolve(), log_dir.resolve(), *(p.resolve() for p in extra_skip))
    critic_time = critic.stat().st_mtime
    if int(critic_time) <= max(int(head_time), _head_moved_time(repo)):
        return True
    return critic_time < _newest_uncommitted_change(repo, skip)


def resolve_commit(repo: Path, ref: str) -> str:
    """Full SHA of the commit ``ref`` names in ``repo``, or "" when it names none."""
    if not re.fullmatch(r"[0-9a-fA-F]{7,64}", ref):
        return ""
    return _git(repo, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")


def _relative_to_top(value: str, top: str) -> str:
    """Return ``value`` relative to ``top`` in POSIX form, or "" when it is outside.

    A drive-letter path is compared as a Windows path on any host, so a
    Windows checkout's ``C:/repo`` top and a ``C:\\repo\\a.py`` citation match.
    """
    windows = _WINDOWS_ABSOLUTE.match(value)
    try:
        if windows:
            return PureWindowsPath(windows.group(1)).relative_to(PureWindowsPath(top)).as_posix()
        if value.startswith("/"):
            return Path(value).resolve().relative_to(Path(top).resolve()).as_posix()
    except ValueError:
        return ""
    return ""


def _repo_relative(repo: Path, finding: dict) -> dict:
    """Rewrite an absolute file path inside the checkout as a repo-relative one."""
    value = str(finding.get("file") or "")
    top = _git(repo, "rev-parse", "--show-toplevel")
    relative = _relative_to_top(value, top) if value and top else ""
    return {**finding, "file": relative} if relative else finding
