"""Diagnostics for stale (prunable) worktree admin entries.

A stale entry is one git marks ``prunable``: it cannot find the working tree.
The tool never removes these, because the marker cannot separate a deleted
worktree from a moved one. It reports them instead, and points the operator at
``git worktree prune --expire``. These helpers supply the facts that decision
needs, above all whether prune would destroy work that nothing else anchors.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable
from pathlib import Path

from scripts.maintenance import _gc_anchors
from scripts.maintenance._gc_files import regular_file
from scripts.maintenance.worktree_report import Worktree

GitRunner = Callable[[list[str]], str]


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
    present = regular_file(index)
    if present is None:
        return UNKNOWN
    if not present:
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


def unreachable_admin_commits(admin: Path, repo_dir: str, timeout: float) -> list[str] | None:
    """Which commits does this worktree's admin directory alone still anchor?

    Two anchors live in there and both die with the directory. The first is the
    reflog: ``HEAD`` is per worktree and so is ``logs/HEAD``, so a worktree that
    commits and then checks something else out leaves that commit named by the
    reflog and by nothing under the repository's ``refs/``. The second is the
    worktree's own refs. ``refs/worktree/``, ``refs/bisect/``, and
    ``refs/rewritten/`` are per-worktree namespaces stored under the admin
    directory, so ``rev-list --not --all`` in the main repository cannot see
    them and neither can ``for-each-ref``.

    Verified against real git 2.43.0 on both: a commit held only by
    ``refs/worktree/`` survives ``git worktree remove`` as an unreachable object
    and is gone after ``git gc --prune=now``, and the reflog case reports no
    containing ref before removal and shows up under ``fsck --unreachable``
    after it.

    ``None`` means the question could not be answered, which callers disclose
    rather than read as "nothing to lose". An empty list means nothing here is
    at risk.
    """
    candidates = _gc_anchors.reflog_oids(admin)
    if candidates is None:
        return None
    local_refs = _gc_anchors.worktree_ref_oids(admin)
    if local_refs is None:
        return None
    candidates = list(dict.fromkeys(candidates + local_refs))
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


def linked_checkout_present(path: str) -> bool:
    """Is a live linked checkout for *this* entry still sitting at ``path``?

    Asks for the ``.git`` marker rather than the directory, because a bare
    ``exists`` verifies a pathname and not an identity. Delete a worktree and
    recreate an ordinary directory at the same path and ``exists`` still says
    yes, so the entry reads as healthy while its admin record points at
    something that is no longer that worktree. Verified against real git: a
    linked worktree always carries a ``.git`` file holding ``gitdir:``, and a
    replacement directory does not. The main worktree, whose ``.git`` is a
    directory, never reaches here; ``decide`` returns ``KEEP_MAIN`` above. A
    ``.git`` directory at any other path is therefore a foreign standalone
    repository sitting where the linked checkout used to be, not this entry, so
    it reads as stale rather than present. Reading it as present would let
    ``git worktree remove`` delete that unrelated repository and its object
    database.

    The marker existing is not enough either. Move worktree B onto worktree
    A's deleted path and A's directory now holds a ``.git`` file, but it names
    B's admin directory. A then reads as healthy, and every probe that follows
    reports on A's admin record while the checkout actually there belongs to B.
    So the marker has to point back: the admin directory it names must record
    this same path as its worktree. A mismatch means this entry has no
    checkout, which is the stale answer, and B is a registered entry of its own
    that the report reaches separately.

    Both links can be relative. ``worktree.useRelativePaths`` writes them that
    way, and ``git worktree repair`` can too, so each is anchored against the
    file that holds it rather than against the process working directory. That
    is the same mistake ``--git-common-dir`` punishes in ``admin_dir_for``.

    Two O(1) file reads, no directory scan, named so ``decide`` can take it as
    a default argument.
    """
    marker = Path(path) / ".git"
    try:
        recorded = marker.read_text(encoding="utf-8").strip()
    except IsADirectoryError:
        return False
    except OSError:
        return False
    admin = _anchored(recorded.removeprefix("gitdir:").strip(), marker.parent)
    if admin is None:
        return False
    try:
        back = (admin / "gitdir").read_text(encoding="utf-8").strip()
    except OSError:
        return False
    pointed = _anchored(back, admin)
    return pointed is not None and _resolved(pointed) == _resolved(marker)


# Every per-worktree marker git writes while an operation is mid-flight, mapped
# to the words a reader would use for it. Each lives in the worktree's own admin
# directory, so removing the worktree deletes the marker along with whatever it
# anchors. Verified against real git 2.43.0: an interrupted merge whose result
# is an empty tree leaves ``git status --porcelain`` empty while ``MERGE_HEAD``
# holds a commit no branch, no tag, and no reflog entry reaches, so the porcelain
# check, the HEAD comparison, and the reflog re-probe all pass and the commit is
# orphaned by the removal. ``git worktree remove`` does not guard this either.
# ``index.lock`` rides along because it is the same question asked of the same
# directory: is anything working here right now. Verified against real git
# 2.43.0 that ``git worktree remove`` deletes a worktree whose index is locked,
# exits 0, and says nothing, so a commit being written at that moment is lost.
# A lock left behind by a crashed git reads the same way and keeps the entry,
# which is the safe direction and one the reason text tells the reader how to
# clear.
# ``HEAD.lock`` rides along for the same reason as ``index.lock``: git writes it
# while it moves ``HEAD``, then renames it into place. A detached-HEAD update,
# which writes ``HEAD`` directly, leaves ``HEAD.lock`` in the admin directory
# during that window while none of the operation markers above exist. Verified
# against real git 2.43.0 that ``git worktree remove`` deletes a worktree whose
# ``HEAD.lock`` is held, exits 0, and says nothing, so a HEAD move in flight is
# interrupted with no warning. A lock left by a crashed git keeps the entry,
# again the safe direction.
_OPERATION_MARKERS: tuple[tuple[str, str], ...] = (
    ("MERGE_HEAD", "an unfinished merge is running"),
    ("CHERRY_PICK_HEAD", "an unfinished cherry-pick is running"),
    ("REVERT_HEAD", "an unfinished revert is running"),
    ("BISECT_LOG", "an unfinished bisect is running"),
    ("rebase-merge", "an unfinished rebase is running"),
    ("rebase-apply", "an unfinished rebase is running"),
    ("sequencer", "an unfinished sequencer run is waiting"),
    ("index.lock", "another git process is holding the index lock"),
    ("HEAD.lock", "another git process is updating HEAD"),
)


def admin_dir_from_marker(path: str) -> Path | None:
    """The admin directory this checkout's ``.git`` marker names, or None.

    Two O(1) file reads and no subprocess, unlike ``admin_dir_for``, which scans
    every registered entry. That matters because this runs once per worktree on
    the decision path, where the time budget already carries three git calls.
    A main worktree holds a ``.git`` directory rather than a marker file, and
    that directory is its gitdir, so it answers itself.
    """
    marker = Path(path) / ".git"
    try:
        recorded = marker.read_text(encoding="utf-8").strip()
    except IsADirectoryError:
        return marker
    except OSError:
        return None
    return _anchored(recorded.removeprefix("gitdir:").strip(), marker.parent)


def in_progress_operation(path: str) -> str | None:
    """Name the git operation this worktree is in the middle of, or None.

    Answers None when the admin directory cannot be resolved, because the two
    callers that matter both treat an unresolvable entry as stale on their own
    and a false refusal here would keep every unreadable worktree forever.

    Probes each marker with ``lstat`` rather than ``exists``. ``exists`` folds a
    missing file and an unreadable one into the same ``False``, so a permission
    or I/O error on the admin directory would read as "no operation in progress"
    and let the entry be removed mid-flight. ``lstat`` separates the two: a
    ``FileNotFoundError`` is the ordinary "marker absent" and moves on, while any
    other ``OSError`` means the question could not be answered, which is
    disclosed as a withholding reason rather than swallowed. Checking the link
    itself, not its target, keeps a marker that happens to be a symlink from
    reading as absent because its target is gone.

    The flat names are not the whole answer. Git also writes a lock beside a
    per-worktree ref while it installs one, at whatever depth that ref sits, so
    ``_ref_update_in_flight`` asks the same question of ``refs/`` once the named
    markers have all answered absent.
    """
    admin = admin_dir_from_marker(path)
    if admin is None:
        return None
    for name, description in _OPERATION_MARKERS:
        try:
            (admin / name).lstat()
        except FileNotFoundError:
            continue
        except OSError:
            return f"the {name} marker could not be read, so an operation may be in progress"
        return description
    return _ref_update_in_flight(admin)


def _ref_update_in_flight(admin: Path) -> str | None:
    """Name a per-worktree ref update git is in the middle of, or None.

    The flat marker names above cover the locks git writes at the top of the
    admin directory. They are not the only locks it writes there. Per-worktree
    refs, ``refs/worktree/*`` and ``refs/bisect/*``, live under this same
    directory, and the files backend creates ``<ref>.lock`` beside the ref while
    it installs one. Removing the admin directory during that window interrupts
    the write, so the commit the ref was being pointed at ends up with no
    anchor, which is the same loss ``index.lock`` and ``HEAD.lock`` are guarded
    against one level up.

    The anchor readers do not cover this either. ``worktree_ref_oids`` skips a
    file that holds no text, and a lock is empty for the whole of a delete
    transaction and for the window between creation and the write. Verified
    against real git 2.43.0: with ``refs/worktree/<name>.lock`` held, this probe
    answered ``None``, ``worktree_ref_oids`` answered ``[]``, and
    ``git worktree remove`` deleted the worktree, exited 0, and printed nothing.

    Any name ending in ``.lock`` counts, whatever its depth, because the backend
    derives the lock's name from the ref's own path. A walk that cannot be
    trusted answers unknown rather than "nothing in flight", the same direction
    every other probe in this module takes. Costs one ``stat`` on a worktree
    that has never held a per-worktree ref, because git does not create the
    ``refs`` directory until it writes one, and no subprocess in any case.
    """
    entries = _gc_anchors.walk_files(admin / "refs")
    if entries is None:
        return "its per-worktree refs could not be read, so an operation may be in progress"
    if any(entry.name.endswith(".lock") for entry in entries):
        return "another git process is updating a worktree-local ref"
    return None


def _anchored(recorded: str, base: Path) -> Path | None:
    """Resolve a gitdir link against the file that holds it, not the cwd."""
    if not recorded:
        return None
    link = Path(recorded)
    return link if link.is_absolute() else base / link


def is_stale(worktree: Worktree, checkout_present: Callable[[str], bool]) -> bool:
    """Report whether the worktree's directory is gone, by git's word or by stat.

    ``prunable`` is git's own answer and is the reliable signal for an unlocked
    entry. Verified against real git: git omits it for a locked worktree whose
    directory has been deleted, because a locked entry is never a prune
    candidate and git does not compute the marker. Trusting ``prunable`` alone
    would let a locked stale entry report ``locked`` and nothing more, hiding
    the orphaned index and reflog from the reader who is about to unlock it.

    ``checkout_present`` is a seam so a test states what it means rather than
    depending on whether its synthetic path happens to be absent from the
    machine running the suite. In production it is one ``stat`` for the
    ``.git`` marker, and it cannot fire on a healthy worktree, which carries
    that marker by definition. A transient mount failure would produce a
    warning that keeps the worktree, which is the fail-safe direction.
    """
    return bool(worktree.prunable) or not checkout_present(worktree.path)
