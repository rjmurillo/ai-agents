"""Diagnostics for stale (prunable) worktree admin entries.

A stale entry is one git marks ``prunable``: it cannot find the working tree.
The tool never removes these, because the marker cannot separate a deleted
worktree from a moved one. It reports them instead, and points the operator at
``git worktree prune --expire``. These helpers supply the facts that decision
needs, above all whether prune would destroy work that nothing else anchors.
"""

from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Callable
from pathlib import Path

GitRunner = Callable[[list[str]], str]

_OID = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")
_NULL_OID = re.compile(r"0{40}|0{64}")


def admin_dir_for(worktree_path: str, run_git: GitRunner, repo_dir: str) -> Path | None:
    """Return the ``.git/worktrees/<name>`` directory backing ``worktree_path``.

    The porcelain listing does not name the admin directory, so this reads the
    ``gitdir`` file each candidate directory holds. Its contents are the
    worktree's own ``.git`` path, which is how git itself resolves the link.
    Returns ``None`` when the mapping cannot be established, which callers must
    treat as "unknown", never as "nothing there".

    ``rev-parse --git-common-dir`` answers relatively when it can, returning a
    bare ``.git`` even under ``git -C``. Anchoring that against ``repo_dir``
    rather than the process working directory is what keeps the lookup correct
    when the tool is invoked from somewhere else; without it every lookup fails
    and every staged-work warning goes silently missing.

    Cost is O(N) per call and O(N**2) across a scan: one subprocess plus one
    ``gitdir`` read per registered worktree. Measured at 200 stale entries that
    is roughly 0.4s. Caching the map across calls would halve it and is
    deliberately not done: ``apply_removals`` re-runs this on its revalidation
    pass, and a cache that outlived one scan would answer that pass from a
    reading the revalidation exists to replace.
    """
    try:
        common = Path(run_git(["rev-parse", "--git-common-dir"]).strip())
    except (RuntimeError, OSError):
        return None
    if not common.is_absolute():
        common = Path(repo_dir) / common
    container = common / "worktrees"
    try:
        entries = sorted(container.iterdir())
    except OSError:
        return None
    target = Path(worktree_path) / ".git"
    resolved_target = _resolved(target)
    for admin in entries:
        try:
            recorded = (admin / "gitdir").read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if recorded == str(target) or _resolved(Path(recorded)) == resolved_target:
            return admin
    return None


def _resolved(path: Path) -> Path:
    """Normalize ``path`` for comparison, tolerating that it no longer exists.

    A stale worktree's directory is gone, so ``resolve`` cannot walk the whole
    chain. It still normalizes the surviving parents, which is what separates
    ``/var/...`` from ``/private/var/...`` on a platform that symlinks one to
    the other. Falls back to the raw path when the filesystem refuses to answer.
    """
    try:
        return path.resolve()
    except OSError:
        return path


STAGED = "staged"
CLEAN = "clean"
UNKNOWN = "unknown"


def staged_content_state(admin: Path, head: str, repo_dir: str, timeout: float) -> str:
    """Does the orphaned index hold content no commit and no ref carries?

    ``git add`` writes a blob to the object database and records it only in the
    worktree's index. Deleting the directory leaves that index behind as the
    blob's sole anchor, and both ``git worktree remove`` and
    ``git worktree prune`` delete the admin directory, index included. Verified
    against real git: the blob is then reachable from nothing.

    Runs from ``repo_dir``, never from the admin directory. Git rejects the
    admin directory outright when ``safe.bareRepository`` is ``explicit``,
    which is the default on this machine, and that fatal error is
    indistinguishable from a real answer at the exit-code level.

    Three-valued on purpose. ``diff-index`` exits 1 for a difference and 0 for
    none, so anything else is git failing to answer, and reporting that as
    staged work would cry wolf on every entry. Callers warn on ``STAGED``,
    stay quiet on ``CLEAN``, and disclose the gap on ``UNKNOWN``.
    """
    index = admin / "index"
    if not index.is_file():
        return CLEAN
    try:
        result = subprocess.run(
            ["git", "diff-index", "--cached", "--quiet", head],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            cwd=repo_dir,
            env={**os.environ, "GIT_INDEX_FILE": str(index)},
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return UNKNOWN
    if result.returncode == 0:
        return CLEAN
    if result.returncode == 1:
        return STAGED
    return UNKNOWN


def unreachable_reflog_commits(admin: Path, repo_dir: str, timeout: float) -> list[str] | None:
    """Which commits does this worktree's reflog alone still anchor?

    ``HEAD`` is per worktree, and so is its reflog. A detached worktree that
    commits and then checks out something else leaves that commit anchored by
    ``logs/HEAD`` and nothing under ``refs/``. Deleting the admin directory
    deletes the reflog with it, and the commit becomes collectable. Verified
    against real git: ``for-each-ref --contains`` reports no ref, and after the
    entry goes the commit shows up under ``fsck --unreachable``.

    ``None`` means the question could not be answered, which callers disclose
    rather than read as "nothing to lose". An empty list means nothing here is
    at risk.
    """
    candidates = _reflog_oids(admin)
    if candidates is None:
        return None
    if not candidates:
        return []
    known = _existing_objects(candidates, repo_dir, timeout)
    if known is None:
        return None
    if not known:
        return []
    unreachable = _run(
        ["rev-list", "--no-walk", "--stdin", "--not", "--all"], repo_dir, timeout, known
    )
    if unreachable is None:
        return None
    return unreachable.split()


def _reflog_oids(admin: Path) -> list[str] | None:
    """Every non-null object id named in the admin reflog, oldest first.

    A file that holds text but yields no recognizable object id at all was not
    understood, so it answers "unknown" rather than "nothing at risk". Reading
    a truncated or unexpectedly encoded reflog as empty is the same silent
    all-clear the rest of this probe is built to avoid. Lines that parse and
    name only the null id are understood and carry no risk, which is why the
    test is "did any field look like an id" rather than "did any survive".
    """
    log = admin / "logs" / "HEAD"
    if not log.is_file():
        return []
    try:
        text = log.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    seen: dict[str, None] = {}
    understood = False
    for line in text.splitlines():
        for field in line.split(" ")[:2]:
            if not _OID.fullmatch(field):
                continue
            understood = True
            if _NULL_OID.fullmatch(field):
                continue
            seen[field] = None
    if text.strip() and not understood:
        return None
    return list(seen)


def _existing_objects(oids: list[str], repo_dir: str, timeout: float) -> list[str] | None:
    """Drop ids the object database no longer holds.

    ``rev-list`` aborts with ``fatal: bad object`` on the first missing id, and
    an old reflog naming a collected commit is ordinary. Filtering first keeps
    one dead id from turning the whole answer into "unknown".
    """
    out = _run(["cat-file", "--batch-check"], repo_dir, timeout, oids)
    if out is None:
        return None
    return [
        line.split(" ")[0] for line in out.splitlines() if line and not line.endswith(" missing")
    ]


def _run(args: list[str], repo_dir: str, timeout: float, stdin: list[str]) -> str | None:
    """Run a git command over ids on stdin. ``None`` on any refusal."""
    try:
        result = subprocess.run(
            ["git", *args],
            input="".join(f"{oid}\n" for oid in stdin),
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            cwd=repo_dir,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return result.stdout
