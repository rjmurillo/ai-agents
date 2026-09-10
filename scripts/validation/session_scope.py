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

import json
import os
import re
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

_GIT_TIMEOUT_SECONDS = 30
_COMMIT_SHA = re.compile(r"^[0-9a-f]{7,40}$")

# The fragments ``commit_reachability_problem`` returns. Named so a caller can
# tell which question failed without matching on prose: the object being absent
# and the object being present but unreachable have different causes.
NOT_A_COMMIT_SHA = "is not a commit SHA"
NO_SUCH_COMMIT = "names no commit in this repository"
NOT_AN_ANCESTOR = "names a commit that is not an ancestor of HEAD"


def _git_env(*, preserve_index_file: bool = False) -> dict[str, str]:
    """Return a clean git environment, optionally preserving the active index."""
    from checks_common import _git_subprocess_env

    env: dict[str, str] = dict(_git_subprocess_env())
    if preserve_index_file and (index := os.environ.get("GIT_INDEX_FILE")):
        env["GIT_INDEX_FILE"] = index
    return env


def _git(
    args: list[str], repo_root: Path, *, preserve_index_file: bool = False
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo_root,
        env=_git_env(preserve_index_file=preserve_index_file),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=_GIT_TIMEOUT_SECONDS,
        check=False,
    )


_ADJUDICABLE_CACHE: dict[str, bool] = {}


def _can_adjudicate_reachability(repo_root: Path) -> bool:
    """Whether this checkout can answer a reachability question at all.

    Two git probes decide it: the directory has to be a work tree, and the
    clone must not be shallow, because a shallow clone is genuinely missing the
    older commits a log names. Neither answer depends on the SHA being asked
    about, and neither changes while a process runs, so the pair is asked once
    per repository root instead of once per commit.

    Uncached, validating the committed session-log corpus spawned 878 of each,
    1756 of the 2735 git processes that one test started, for two answers that
    were identical every time. Refs #5382, and #5379 for the same shape in the
    test harness.

    Only a completed probe is memoized. ``OSError`` and ``SubprocessError``
    propagate to the caller's fail-open handler and record nothing, so a git
    that was momentarily unavailable does not pin its own absence for the rest
    of the process.

    Call ``_adjudication_cache_clear()`` to force rediscovery. That is the
    supported seam for a test that changes a checkout's shape in place.
    """
    key = str(Path(repo_root).resolve())
    cached = _ADJUDICABLE_CACHE.get(key)
    if cached is not None:
        return cached
    if _git(["rev-parse", "--is-inside-work-tree"], repo_root).returncode != 0:
        answer = False
    else:
        shallow = _git(["rev-parse", "--is-shallow-repository"], repo_root)
        answer = shallow.returncode == 0 and shallow.stdout.strip() != "true"
    _ADJUDICABLE_CACHE[key] = answer
    return answer


_adjudication_cache_clear = _ADJUDICABLE_CACHE.clear


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
        if not _can_adjudicate_reachability(repo_root):
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

def _added_session_paths(
    paths: Iterable[str],
    repo_root: Path,
    git_args: list[str],
    *,
    preserve_index_file: bool = False,
) -> set[str] | None:
    """Return the subset of ``paths`` one git diff reports as additions.

    The diff carries no pathspec. With rename detection enabled, limiting the
    diff to the caller's paths hides the deletion half and can reclassify a
    rename as an add. Intersect in Python instead so only true adds receive
    creation-mode.

    Return ``None`` on a git failure so the caller can block instead of
    guessing. A failed probe must not silently reclassify an existing log as a
    creation-time log and skip compliance-only checks.
    """
    wanted = list(paths)
    if not wanted:
        return set()
    try:
        diff = _git(git_args, repo_root, preserve_index_file=preserve_index_file)
    except (OSError, subprocess.SubprocessError):
        return None
    if diff.returncode != 0:
        if diff.stdout:
            print(diff.stdout, end="", file=sys.stderr)
        if diff.stderr:
            print(diff.stderr, end="", file=sys.stderr)
        return None
    added: set[str] = set()
    for line in diff.stdout.splitlines():
        parts = line.split("	", 1)
        if len(parts) != 2:
            continue
        status, name = parts
        if status.startswith("A"):
            added.add(name.strip())
    return {path for path in wanted if path in added}


def added_session_paths_in_index(paths: Iterable[str], repo_root: Path) -> set[str] | None:
    """Return session-log paths staged as adds in the index, or ``None`` on failure."""
    return _added_session_paths(
        paths,
        repo_root,
        ["diff", "--cached", "--name-status", "-M", "--diff-filter=A"],
        preserve_index_file=True,
    )


def _commit_object_parents(repo_root: Path, head: str) -> list[str] | None:
    try:
        result = _git(["cat-file", "-p", head], repo_root)
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return [
        line.removeprefix("parent ")
        for line in result.stdout.splitlines()
        if line.startswith("parent ")
    ]


def _head_parents(repo_root: Path, head: str = "HEAD") -> list[str] | None:
    """Return a commit's parent SHAs, or ``None`` when git cannot answer."""
    try:
        result = _git(["rev-list", "--parents", "-n", "1", head], repo_root)
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        if result.stdout:
            print(result.stdout, end="", file=sys.stderr)
        if result.stderr:
            print(result.stderr, end="", file=sys.stderr)
        return None
    parts = result.stdout.split()
    if not parts:
        return None
    return parts[1:] or _commit_object_parents(repo_root, head)


def _pull_request_head_sha() -> str:
    event_path = os.environ.get("GITHUB_EVENT_PATH", "")
    if not event_path:
        return ""
    try:
        payload = json.loads(Path(event_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    if not isinstance(payload, dict):
        return ""
    pull_request = payload.get("pull_request")
    if not isinstance(pull_request, dict):
        return ""
    head_data = pull_request.get("head")
    if not isinstance(head_data, dict):
        return ""
    head = head_data.get("sha", "")
    return head if isinstance(head, str) and _COMMIT_SHA.fullmatch(head) else ""


def _validation_head(repo_root: Path, parents: list[str]) -> tuple[str, list[str] | None]:
    """Select the PR head behind GitHub's synthetic merge commit."""
    pull_request_head = _pull_request_head_sha()
    if len(parents) != 2 or pull_request_head != parents[1]:
        return "HEAD", parents

    return pull_request_head, _head_parents(repo_root, pull_request_head)


def added_session_paths_in_head(paths: Iterable[str], repo_root: Path) -> set[str] | None:
    """Return paths added by the validation head, or ``None`` on git failure."""
    wanted = list(paths)
    if not wanted:
        return set()
    parents = _head_parents(repo_root)
    if parents is None:
        return None
    head, parents = _validation_head(repo_root, parents)
    if parents is None:
        return None
    if not parents:
        return _added_session_paths(
            wanted,
            repo_root,
            ["diff-tree", "--root", "--name-status", "-M", "--diff-filter=A", "-r", head],
        )
    added_against_all: set[str] | None = None
    for parent in parents:
        added = _added_session_paths(
            wanted,
            repo_root,
            ["diff-tree", "--name-status", "-M", "--diff-filter=A", "-r", parent, head],
        )
        if added is None:
            return None
        if added_against_all is None:
            added_against_all = set(added)
        else:
            added_against_all &= added
        if not added_against_all:
            return set()
    return added_against_all or set()


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
    """Return paths added by this branch and whether it deleted any session log."""
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


def committed_session_validation_modes(
    paths: Iterable[str], repo_root: Path
) -> dict[str, str] | None:
    """Classify committed session logs as creation, full, or existing.

    ``creation`` applies only to paths that the validated branch-head commit adds.
    ``existing`` is reserved for paths proven to predate the branch, meaning
    they are absent from the branch-added set relative to the merge base.
    Everything else stays on the full validation path with no mode flag.
    """
    wanted = list(paths)
    if not wanted:
        return {}
    head_added = added_session_paths_in_head(wanted, repo_root)
    if head_added is None:
        return None
    branch_new = new_session_logs(wanted, repo_root)
    modes: dict[str, str] = {}
    for path in wanted:
        if path in head_added:
            modes[path] = "creation"
        elif path not in branch_new:
            modes[path] = "existing"
        else:
            modes[path] = "full"
    return modes


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
