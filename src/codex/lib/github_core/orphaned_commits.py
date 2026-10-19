"""Detect unpushed local commits behind an escalated round-cap record (issue #5447).

A pr-autofix session that hits the round-cap escalation can leave local,
unpushed commits in its worktree. Nothing marked those commits as unverified,
so a resuming session could push them on the strength of a commit message.
On PR #5344 one such commit claimed to drop a duplicate pre-push gate. Its diff
deleted the lefthook job and the one test that would have caught the deletion.

This module is read-only. It compares the live PR head SHA with the local
``HEAD`` and reports every commit the live head does not contain, flagging the
two shapes the incident showed: edits to CI or pre-push wiring, and removed
tests. ``check_pr_round_cap.py`` owns the CLI and the output envelope; the git
calls go through an injectable runner so tests never need a repository.

Status values: ``clean`` (no commit ahead), ``ahead`` (commits listed),
``unverified`` (git could not answer, so the caller must check by hand).
"""

from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass

#: Runs ``git <args>`` and returns ``(exit code, stdout)``.
GitRunner = Callable[[list[str]], tuple[int, str]]

#: Most commits inspected per scan. Bounds the git calls on a runaway branch.
MAX_COMMITS = 50

# Matched with ``fullmatch``: ``$`` also accepts one trailing newline (#6506).
_SHA = re.compile(r"[0-9a-fA-F]{7,64}")
#: Exit code the runners report when git could not be launched.
_LAUNCH_FAILURE = 127
#: Exit code the worktree runner reports for a path it refused to use.
_INVALID_WORKTREE = 126
#: Every repo-local variable ``git rev-parse --local-env-vars`` reports. Each
#: one redirects, rewrites, or hides history for a child that ``-C`` should
#: have pointed at one repository (``GIT_GRAFT_FILE`` and ``GIT_SHALLOW_FILE``
#: hide commits, ``GIT_REPLACE_REF_BASE`` and ``GIT_NO_REPLACE_OBJECTS`` swap them).
_GIT_ENV_KEYS = (
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_CONFIG",
    "GIT_CONFIG_PARAMETERS",
    "GIT_CONFIG_COUNT",
    "GIT_OBJECT_DIRECTORY",
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_IMPLICIT_WORK_TREE",
    "GIT_GRAFT_FILE",
    "GIT_INDEX_FILE",
    "GIT_NO_REPLACE_OBJECTS",
    "GIT_REPLACE_REF_BASE",
    "GIT_PREFIX",
    "GIT_SHALLOW_FILE",
    "GIT_COMMON_DIR",
    # Not in the rev-parse list, but each one still steers git away from ``-C``.
    "GIT_NAMESPACE",
    "GIT_CEILING_DIRECTORIES",
)
#: Numbered config injection variables (``GIT_CONFIG_KEY_0``, ``GIT_CONFIG_VALUE_0``).
_GIT_ENV_PREFIXES = ("GIT_CONFIG_KEY_", "GIT_CONFIG_VALUE_")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_RECORD_SEP = "\x1e"

_WIRING_PATH = re.compile(
    r"(^|/)lefthook\.ya?ml$"
    r"|^\.github/workflows/"
    r"|(^|/)\.pre-commit-config\.ya?ml$"
    r"|^\.husky/"
    r"|(^|/)\.gitlab-ci\.yml$"
)
_TEST_PATH = re.compile(
    r"(^|/)(tests?|__tests__)/"
    r"|(^|/)test_[^/]*\.py$"
    r"|_test\.(py|go|js|ts)$"
    r"|\.(test|spec)\.(js|ts|jsx|tsx)$"
    r"|Tests?\.cs$"
)
_TEST_DEF = r"(?:async\s+)?def\s+test_|(?:it|test)\(|\[(?:Fact|Theory|Test|TestMethod)\b"
_REMOVED_TEST_DEF = re.compile(rf"^-\s*(?:{_TEST_DEF})")
_ADDED_TEST_DEF = re.compile(rf"^\+\s*(?:{_TEST_DEF})")

RISK_WIRING = "touches CI or pre-push wiring"
RISK_TEST_FILE_DELETED = "deletes a test file"
RISK_TEST_DEFS_REMOVED = "removes test definitions"


@dataclass(frozen=True, slots=True)
class Commit:
    """One unpushed commit: id, subject, changed files, and risk flags."""

    sha: str
    subject: str
    files: tuple[tuple[str, str], ...]
    risks: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {"sha": self.sha, "subject": self.subject, "risks": list(self.risks)}


def _run_git(args: list[str], env: dict[str, str] | None = None) -> tuple[int, str]:
    try:
        result = subprocess.run(
            ["git", *args],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
            env=env,
        )
    except (subprocess.SubprocessError, OSError):
        return _LAUNCH_FAILURE, ""
    return result.returncode, result.stdout or ""


def default_runner(args: list[str]) -> tuple[int, str]:
    """Run ``git`` in the current directory. A launch failure maps to exit 127."""
    return _run_git(args)


def _is_worktree_path(worktree: str) -> bool:
    """Return whether ``worktree`` is a usable git checkout path.

    The value comes from a CLI flag that a dispatch block fills from a PR
    branch lookup, so it is checked before it reaches a git argument vector.
    Refuses an empty value, a NUL byte, a leading ``-`` (read as an option),
    and anything that is not a directory holding a ``.git`` entry. A linked
    worktree holds a ``.git`` file, a clone holds a ``.git`` directory.
    """
    if not worktree or "\x00" in worktree or worktree.startswith("-"):
        return False
    return os.path.isdir(worktree) and os.path.exists(os.path.join(worktree, ".git"))


def worktree_runner(worktree: str) -> GitRunner:
    """Return a runner that executes ``git -C <worktree> <args>``.

    The tier-dispatch loop runs from a shared checkout, so the comparison must
    name the PR's worktree instead of trusting the current directory's ``HEAD``.

    The path is validated, and ``GIT_DIR``, ``GIT_WORK_TREE`` and every other
    variable that ``git rev-parse --local-env-vars`` lists are dropped from the
    child environment.
    Inherited, they would override ``-C`` and point git back at the shared
    checkout (issue #6506). The variables that inject config values go too,
    since they can set ``core.fsmonitor`` or ``core.hooksPath`` for the child:
    ``GIT_CONFIG_PARAMETERS``, ``GIT_CONFIG_COUNT``, and the numbered
    ``GIT_CONFIG_KEY_<n>`` and ``GIT_CONFIG_VALUE_<n>`` pairs. ``GIT_CONFIG_GLOBAL``
    and ``GIT_CONFIG_SYSTEM`` are kept on purpose: they only relocate the
    user's own config files, which git reads from ``~/.gitconfig`` and
    ``/etc/gitconfig`` anyway, and dropping them would change which files the
    child reads. A file at either path is trusted like the user's real config.
    An invalid path yields a runner that always reports exit 126, so the scan
    ends ``unverified`` and never raises.
    """
    if not _is_worktree_path(worktree):
        return lambda _args: (_INVALID_WORKTREE, "")
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in _GIT_ENV_KEYS and not key.startswith(_GIT_ENV_PREFIXES)
    }

    def run(args: list[str]) -> tuple[int, str]:
        return _run_git(["-C", worktree, *args], env)

    return run


def _clean(text: str) -> str:
    return _CONTROL.sub(" ", text).strip()


def parse_log(text: str) -> list[Commit]:
    """Parse ``git log --name-status --format=%x1e%H%x09%s`` output."""
    commits: list[Commit] = []
    for record in text.split(_RECORD_SEP):
        lines = [line for line in record.splitlines() if line.strip()]
        if not lines:
            continue
        sha, _, subject = lines[0].partition("\t")
        files = tuple(
            (parts[0], parts[-1])
            for parts in (line.split("\t") for line in lines[1:])
            if len(parts) >= 2
        )
        commits.append(Commit(sha=sha.strip(), subject=_clean(subject), files=files))
    return commits


def _count_test_defs(patch: str) -> int:
    """Removed minus added test definitions in a zero-context patch."""
    lines = patch.splitlines()
    removed = sum(1 for line in lines if _REMOVED_TEST_DEF.match(line))
    added = sum(1 for line in lines if _ADDED_TEST_DEF.match(line))
    return removed - added


def _removed_test_defs(commit: Commit, runner: GitRunner) -> int:
    modified = [path for status, path in commit.files if status == "M" and _TEST_PATH.search(path)]
    if not modified:
        return 0
    code, patch = runner(["show", "-U0", "--format=", "--no-renames", commit.sha, "--", *modified])
    return _count_test_defs(patch) if code == 0 else 0


def classify(commit: Commit, runner: GitRunner) -> Commit:
    """Return *commit* with the risk flags the diff supports."""
    risks: list[str] = []
    if any(_WIRING_PATH.search(path) for _, path in commit.files):
        risks.append(RISK_WIRING)
    if any(status == "D" and _TEST_PATH.search(path) for status, path in commit.files):
        risks.append(RISK_TEST_FILE_DELETED)
    if _removed_test_defs(commit, runner) > 0:
        risks.append(RISK_TEST_DEFS_REMOVED)
    return Commit(commit.sha, commit.subject, commit.files, tuple(risks))


def _report(status: str, live_head: str, **extra: object) -> dict[str, object]:
    return {"status": status, "live_head": live_head, "commits": [], "warning": "", **extra}


def _unverified(live_head: str, reason: str) -> dict[str, object]:
    warning = (
        f"Could not compare local HEAD with live PR head {live_head[:9] or 'unknown'}: {reason}. "
        "Run `git log <live head>..HEAD` by hand and treat any commit there as "
        "unverified input before reuse."
    )
    return _report("unverified", live_head, reason=reason, warning=warning)


def render_warning(live_head: str, commits: list[Commit], truncated: bool) -> str:
    """Human-readable warning naming each commit and its risk flags."""
    lines = [
        f"{len(commits)} local commit(s) ahead of live PR head {live_head[:9]}"
        f"{' (latest ' + str(MAX_COMMITS) + ' shown)' if truncated else ''}. "
        "No record shows they were pushed. Treat each as unverified input, "
        "not ready to push."
    ]
    for commit in commits:
        flags = f" [{'; '.join(commit.risks)}]" if commit.risks else ""
        lines.append(f"  - {commit.sha[:9]} {commit.subject}{flags}")
    lines.append(
        "Before reuse, inspect each diff in isolation and run the tests that "
        "could disprove its claim with and without the commit. Preserve the "
        "local tip on a branch or tag before any reset."
    )
    return "\n".join(lines)


def scan_unpushed_commits(live_head: str, runner: GitRunner = default_runner) -> dict[str, object]:
    """Report local commits that the live PR head does not contain.

    Read-only. Never raises: a git failure yields an ``unverified`` report.
    The SHA comes from the GitHub API, so its shape is checked before it
    reaches a git argument vector (CWE-88).
    """
    if not _SHA.fullmatch(live_head):
        return _unverified(live_head, "live head is not a commit SHA")
    code, _ = runner(["merge-base", "--is-ancestor", live_head, "HEAD"])
    if code == 1:
        return _unverified(
            live_head, "live head is not an ancestor of HEAD (diverged or another branch)"
        )
    if code == _INVALID_WORKTREE:
        return _unverified(live_head, "the --worktree path is not a git checkout; scan skipped")
    if code == _LAUNCH_FAILURE:
        return _unverified(live_head, "git could not be launched")
    if code != 0:
        return _unverified(live_head, f"git merge-base exited {code}; fetch the PR head first")
    code, out = runner(
        [
            "log",
            "--reverse",
            "--no-renames",
            "--name-status",
            f"--max-count={MAX_COMMITS + 1}",
            f"--format={_RECORD_SEP}%H%x09%s",
            f"{live_head}..HEAD",
        ]
    )
    if code != 0:
        return _unverified(live_head, f"git log exited {code}")
    parsed = parse_log(out)
    if not parsed:
        return _report("clean", live_head)
    truncated = len(parsed) > MAX_COMMITS
    commits = [classify(commit, runner) for commit in parsed[-MAX_COMMITS:]]
    return _report(
        "ahead",
        live_head,
        commits=[commit.to_dict() for commit in commits],
        truncated=truncated,
        warning=render_warning(live_head, commits, truncated),
    )


def scan_if_escalated(
    escalated: bool,
    live_head: str | None,
    runner: GitRunner = default_runner,
) -> dict[str, object]:
    """Scan only when the round-cap record is escalated; otherwise ``not_checked``.

    A missing live head SHA yields ``unverified``, never a silent pass.
    """
    if not escalated:
        return _report("not_checked", live_head or "")
    if not live_head:
        return _unverified("", "live PR head SHA unavailable")
    return scan_unpushed_commits(live_head, runner)
