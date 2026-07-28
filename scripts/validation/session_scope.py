"""Decide whether a session log is being added or edited (issue #3385).

Two callers need the same answer: the git hook (``git_hook_policy``) and the
session-protocol workflow, which invokes ``validate_session_json.py`` directly.
The rule lives here rather than in either caller so they cannot disagree, and
so the workflow does not restate it in YAML (ADR-006).

Standard library only, on purpose. The workflow's ``validate`` job installs no
dependencies and runs a bare ``python3``; importing ``git_hook_policy`` there
would drag in PyYAML and fail.
"""

from __future__ import annotations

import subprocess
from collections.abc import Iterable
from pathlib import Path

_GIT_TIMEOUT_SECONDS = 30


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


def new_session_logs(paths: Iterable[str], repo_root: Path) -> set[str]:
    """Return the subset of ``paths`` this branch is adding rather than editing.

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

    Returns every path when the answer cannot be determined. A repository with
    no merge base (a shallow clone, a fresh init, no ``origin/main``) must not
    silently downgrade every log to record-only validation. Failing toward the
    stricter check keeps an unfetched CI checkout from becoming a bypass.
    """
    wanted = list(paths)
    if not wanted:
        return set()
    base = session_merge_base(repo_root)
    if not base:
        return set(wanted)
    try:
        diff = _git(["diff", "--name-status", "-M", "--diff-filter=A", base], repo_root)
    except (OSError, subprocess.SubprocessError):
        return set(wanted)
    if diff.returncode != 0:
        return set(wanted)
    added = {line.split("\t", 1)[1].strip() for line in diff.stdout.splitlines() if "\t" in line}
    tracked = _tracked(wanted, repo_root)
    return {path for path in wanted if path in added or path not in tracked}


def session_log_is_new(path: str, repo_root: Path) -> bool:
    """Return whether ``path`` is added by this branch rather than edited.

    A log this branch adds is a compliance claim its author is making now, so
    it gets the full checklist. A log already on the branch's base is a record
    being edited, and no edit can make "markdownlint ran" true for a session
    that already ended (issue #3385).
    """
    return path in new_session_logs([path], repo_root)
