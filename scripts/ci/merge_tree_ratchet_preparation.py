"""Base-ref resolution and merge-tree construction for the merge-tree ratchet.

Split out of ``merge_tree_ratchet_check.py`` to keep that file under the
taste-lints 500-line ceiling (issue #5441 review; same reasoning as
``merge_tree_ratchet_baseline_direction.py``'s split).

These are leaf helpers: none of them calls back into
``merge_tree_ratchet_check.py``, so moving them does not disturb that
module's own functions or the tests that patch them by name on that module
(``_resolve_base_oid`` and ``_prepare_merged_tree`` stay there and call these
through the re-exported names, which is what keeps
``patch.object(_m, "_refresh_base_ref", ...)`` and
``patch.object(_m, "_merge_tree_oid", ...)`` working unchanged).
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from scripts.ci.merge_tree_materialization import run_git as _git
from scripts.validation.checks_common import _resolve_default_base_ref

if TYPE_CHECKING:
    from pathlib import Path


def _sanitize_diagnostic(text: str) -> str:
    cleaned = " ".join(text.replace("\x00", "").split())
    return cleaned[:500]


def resolve_default_base_ref(repo_root: Path) -> str | None:
    """The dynamic default: PR base, then origin/HEAD (normalized), then main.

    ``checks_common._resolve_default_base_ref`` can itself return the literal
    string ``refs/remotes/origin/HEAD``, which is not a fetchable branch name:
    ``_refresh_base_ref`` below treats the segment after ``origin/`` as one,
    and a fetch for a remote branch literally named ``HEAD`` fails. Resolving
    the symbolic ref to its real target (``origin/main``, typically) before
    returning is what ``scripts/validation/checks_ratchet.py``'s own
    ``_normalize_remote_head`` does for that module's callers; this repeats
    the same normalization for this module's (issue #5441 review: an earlier
    version of the dynamic-base-ref fix skipped this and broke the fetch on
    every checkout where ``gh pr view`` found no PR).
    """
    base_ref = _resolve_default_base_ref(repo_root)
    if base_ref != "refs/remotes/origin/HEAD":
        return base_ref
    proc = _git(repo_root, "symbolic-ref", "--short", base_ref)
    resolved = proc.stdout.strip()
    if proc.returncode == 0 and resolved.startswith("origin/"):
        return resolved
    detail = _sanitize_diagnostic(proc.stderr) or f"git symbolic-ref exit {proc.returncode}"
    print(f"merge-tree-ratchet: cannot resolve remote HEAD: {detail}", file=sys.stderr)
    return None


def _remote_branch(base_ref: str) -> str | None:
    """The branch name under ``origin/``, or None when ``base_ref`` is not one.

    None is the "nothing to refresh" answer, and ``_refresh_base_ref`` turns it
    into a silent skip. So only a ref that genuinely names no remote branch may
    return None. An earlier version also returned None whenever the remainder
    held a ``/``, which sent every nested branch name down that silent-skip
    path: ``origin/feat/parent``, the shape ``checks_common``'s ``gh pr view``
    branch produces for a stacked PR, then evaluated a local tracking ref that
    was never refreshed (issue #5441 review).

    Slashes are valid in a branch name, and the caller interpolates this value
    into ``+refs/heads/{branch}:refs/remotes/origin/{branch}``, one argv token,
    so a malformed name cannot be read as a git option. It reaches ``git
    fetch``, which rejects it, and ``_refresh_base_ref`` reports that refusal.
    Failing loudly there is the point: a name this function cannot vouch for
    must not take the silent-skip path that means "already up to date".
    """
    for prefix in ("origin/", "refs/remotes/origin/"):
        if base_ref.startswith(prefix):
            branch = base_ref[len(prefix) :]
            return branch or None
    return None


def _refresh_base_ref(repo_root: Path, base_ref: str) -> bool:
    """Refresh a remote-tracking base before resolving its immutable OID."""
    branch = _remote_branch(base_ref)
    if branch is None:
        return True
    refspec = f"+refs/heads/{branch}:refs/remotes/origin/{branch}"
    proc = _git(repo_root, "fetch", "--no-tags", "--quiet", "origin", refspec)
    if proc.returncode == 0:
        return True
    detail = _sanitize_diagnostic(proc.stderr) or f"git fetch rc {proc.returncode}"
    print(
        f"merge-tree-ratchet: failed to refresh {base_ref}: {detail}",
        file=sys.stderr,
    )
    return False


def is_fast_forward_clean(repo_root: Path, base_oid: str) -> bool:
    """True when merging ``base_oid`` into HEAD is provably a no-op.

    Issue #5441. ``git merge-tree --write-tree base_oid HEAD`` computes a tree
    identical to HEAD's own tree whenever ``base_oid`` is an ancestor of HEAD:
    there is nothing from the base side left to fold in. A clean working tree
    (no staged or unstaged changes) is in turn identical to HEAD. Chain the two
    and the repository's working tree IS the merged tree, so whatever a
    ratchet counts against ``repo_root`` is exactly what it would count
    against a materialized copy. Materializing one and recounting anyway would
    recompute a value already in hand; skipping it is what closes issue #5441
    without weakening the check itself, which still runs in full (materialize,
    checkout, recount) the moment either condition fails, e.g. a branch behind
    a base ref that lowered a baseline (issue #4398).
    """
    ancestor = _git(repo_root, "merge-base", "--is-ancestor", base_oid, "HEAD")
    if ancestor.returncode != 0:
        return False
    clean = _git(repo_root, "diff", "--quiet", "HEAD", "--")
    return clean.returncode == 0


def _merge_tree_oid(repo_root: Path, base_oid: str) -> tuple[str | None, bool]:
    """Return (tree-oid, conflicts). oid is None on git failure.

    Every None return writes its own explanation to stderr, so callers must not
    add a second generic one. Two messages for one failure make the specific
    diagnosis read like a guess (PR #4567 review).
    """
    proc = _git(repo_root, "merge-tree", "--write-tree", base_oid, "HEAD")
    if proc.returncode in (0, 1):
        # exit 1 means conflicts; stdout still has the partial tree oid on line 1
        lines = proc.stdout.strip().splitlines()
        conflicts = proc.returncode == 1
        if not lines:
            sys.stderr.write(
                f"merge-tree-ratchet: git merge-tree exited {proc.returncode} but wrote\n"
                "no tree OID, so there is no merged tree to evaluate.\n"
            )
            return None, conflicts
        return lines[0], conflicts
    sys.stderr.write(f"git merge-tree failed (rc {proc.returncode}):\n{proc.stderr}\n")
    if "unrelated histories" in proc.stderr:
        sys.stderr.write(
            "merge-tree-ratchet: no merge base was reachable. This is a shallow-fetch\n"
            "regression, not a ratchet breach: a `git fetch --depth=1` writes\n"
            ".git/shallow and cuts history traversal, so any branch behind the base\n"
            "aborts here. Fetch the base ref at full depth (issue #4518).\n"
        )
    return None, False
