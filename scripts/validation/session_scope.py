"""Decide whether a session log is being added or edited (issue #3385).

Two callers need the same answer: the git hook (``git_hook_policy``) and the
session-protocol workflow, which invokes ``validate_session_json.py`` directly.
The rule lives here rather than in either caller so they cannot disagree, and
so the workflow does not restate it in YAML (ADR-006).

The same validator also needs to ask git whether a commit a log names is
really there (issue #3618), so that question lives here too rather than
teaching a second module how to shell out to git.

Standard library only, on purpose. The workflow's ``validate`` job installs no
dependencies and runs a bare ``python3``; importing ``git_hook_policy`` there
would drag in PyYAML and fail.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Iterable
from pathlib import Path

_GIT_TIMEOUT_SECONDS = 30
_COMMIT_SHA = re.compile(r"^[0-9a-f]{7,40}$")

# The fragments ``commit_reachability_problem`` returns. Named so a caller can
# tell which question failed without matching on prose: the object being absent
# and the object being present but unreachable have different causes.
NOT_A_COMMIT_SHA = "is not a commit SHA"
NO_SUCH_COMMIT = "names no commit in this repository"
NOT_AN_ANCESTOR = "names a commit that is not an ancestor of HEAD"


def _git(args: list[str], repo_root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=_GIT_TIMEOUT_SECONDS,
        check=False,
    )


def commit_reachability_problem(sha: str, repo_root: Path) -> str | None:
    """Describe why ``sha`` is not a usable commit reference here, else None.

    None means "no complaint", and it covers two different situations on
    purpose. The commit may be present and reachable from HEAD, or this
    checkout may be unable to answer at all: not a work tree, or a shallow
    clone where older commits are genuinely absent. Complaining in the second
    case would describe the clone rather than the log.

    A commit cannot contain its own SHA, so a recorded ending commit is always
    at least one commit behind the log that names it. The satisfiable contract
    is therefore "names a commit reachable from HEAD", not "names HEAD".

    Args:
        sha: Candidate commit SHA. A value that is not a bare hex SHA is
            rejected without asking git: it reaches git as an argument, where a
            leading dash would be read as an option (CWE-88).
        repo_root: Repository to ask.

    Returns:
        A sentence fragment naming the problem, or None when there is none.
    """
    if not _COMMIT_SHA.match(sha):
        return NOT_A_COMMIT_SHA
    try:
        if _git(["rev-parse", "--is-inside-work-tree"], repo_root).returncode != 0:
            return None
        shallow = _git(["rev-parse", "--is-shallow-repository"], repo_root)
        if shallow.returncode != 0 or shallow.stdout.strip() == "true":
            return None
        if _git(["cat-file", "-e", f"{sha}^{{commit}}"], repo_root).returncode != 0:
            return NO_SUCH_COMMIT
        if _git(["merge-base", "--is-ancestor", sha, "HEAD"], repo_root).returncode != 0:
            return NOT_AN_ANCESTOR
    except (OSError, subprocess.SubprocessError):
        return None
    return None


def session_merge_base(repo_root: Path) -> str:
    """Return the commit this branch diverged from, or "" when unknown.

    The merge base is the comparison point rather than the tip of main: a log
    added to main after this branch started exists at the tip but not on this
    branch's own history, and treating it as pre-existing would let a new log
    in under the looser rule.
    """
    try:
        base = _git(["merge-base", "origin/main", "HEAD"], repo_root)
    except (OSError, subprocess.SubprocessError):
        return ""
    if base.returncode != 0:
        return ""
    return base.stdout.strip()


def _tracked(paths: list[str], repo_root: Path) -> set[str]:
    """Return the subset of ``paths`` git knows about.

    An untracked file never appears in ``git diff``, so without this check a
    brand-new log nobody has staged yet would look unchanged and skip the
    checklist. Both real call sites hand over staged or committed paths, but a
    rule that fails open on the most common shape of "new log" is one refactor
    away from being a bypass.
    """
    if not paths:
        return set()
    try:
        listed = _git(["ls-files", "-z", "--", *paths], repo_root)
    except (OSError, subprocess.SubprocessError):
        return set()
    if listed.returncode != 0:
        return set()
    return {entry for entry in listed.stdout.split("\0") if entry}


def _added_paths_from_name_status(
    output: str,
) -> tuple[set[str], bool] | None:
    """Return added paths and whether any session log was deleted."""
    added: set[str] = set()
    deleted_session = False
    tokens = output.split("\0")
    index = 0
    while index < len(tokens) and tokens[index]:
        status = tokens[index]
        index += 1
        if status.startswith(("R", "C")):
            if index + 1 >= len(tokens):
                return None
            index += 2
            continue
        if index >= len(tokens):
            return None
        path = tokens[index]
        index += 1
        if status == "A":
            added.add(path)
        elif status == "D" and path.startswith(".agents/sessions/") and path.endswith(".json"):
            deleted_session = True
    return added, deleted_session


def session_change_scope(
    paths: Iterable[str],
    repo_root: Path,
    *,
    compare_ref: str | None = None,
) -> tuple[set[str], bool]:
    """Return paths added by this branch and whether it deleted any session log.

    One ``git diff`` and one ``git ls-files`` for the whole batch, not a probe
    per path: the answer for every path comes out of the same comparison.

    Rename detection is on. Correcting a historical log's filename is the
    central use case of issue #3385, so a rename must stay an edit. Without
    ``-M`` the new name would look like an addition and the checklist would
    come back, defeating the fix.

    The diff carries no pathspec, and the caller's paths are intersected in
    Python instead. Git pairs a rename by seeing both sides, so limiting the
    diff to the new path hides the deletion and reports the rename as an add.
    Measured: the same rename reports ``A`` under ``-- <new path>`` and
    ``R100`` unlimited. ``--name-status`` reads no blob content, so diffing
    the whole tree costs little.

    ``compare_ref`` switches the diff from the ambient index and working tree
    to a named ref. Pre-push and pre-PR callers validate committed paths at
    HEAD, so their scope must not be affected by unrelated unstaged changes.

    A rewrite can fall below Git's rename-similarity threshold and appear as
    one deletion plus one addition. The added path still needs full validation
    as a new compliance claim, but the caller must not classify it as
    creation-mode when any session deletion makes ancestry ambiguous. The
    boolean second return value carries that ambiguity to the caller. The output
    is NUL-delimited so quoted or control characters cannot change path
    identity.

    Returns every path when the answer cannot be determined. A repository with
    no merge base (a shallow clone, a fresh init, no ``origin/main``) must not
    silently downgrade every log to record-only validation. Failing toward the
    stricter check keeps an unfetched CI checkout from becoming a bypass.
    """
    wanted = list(paths)
    if not wanted:
        return set(), False
    base = session_merge_base(repo_root)
    if not base:
        return set(wanted), False
    try:
        diff_args = ["diff", "--name-status", "-z", "-M", base]
        if compare_ref is not None:
            diff_args.append(compare_ref)
        diff = _git(diff_args, repo_root)
    except (OSError, subprocess.SubprocessError):
        return set(wanted), False
    if diff.returncode != 0:
        return set(wanted), False
    parsed = _added_paths_from_name_status(diff.stdout)
    if parsed is None:
        return set(wanted), False
    added, deleted_session = parsed
    tracked = _tracked(wanted, repo_root)
    return {path for path in wanted if path in added or path not in tracked}, deleted_session


def new_session_logs(
    paths: Iterable[str],
    repo_root: Path,
    *,
    compare_ref: str | None = None,
) -> set[str]:
    """Return the subset of ``paths`` this branch is adding rather than editing."""
    added, _ = session_change_scope(paths, repo_root, compare_ref=compare_ref)
    return added


def session_log_is_new(path: str, repo_root: Path) -> bool:
    """Return whether ``path`` is added by this branch rather than edited.

    A log this branch adds is a compliance claim its author is making now, so
    it gets the full checklist. A log already on the branch's base is a record
    being edited, and no edit can make "markdownlint ran" true for a session
    that already ended (issue #3385).
    """
    return path in new_session_logs([path], repo_root)
