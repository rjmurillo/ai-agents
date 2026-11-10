"""Scanner-input guard and diff helpers for the /review CodeQL pre-step.

Implements the "Scanner-input guard" of the ADR-041 amendment 2026-11-09 (rules
file: ``.project-toolkit/analysis/adr-041-review-caller-rules.md``). The guard
runs before either result source. A branch must not change the code, config, or
queries that scan it and then have the result trusted, so when the diff touches
a guarded path the pre-step reads no result and reports
``CodeQL: SKIPPED (scanner inputs modified)``.

The diff is the merge base with the default branch to HEAD, plus uncommitted
changes (staged, unstaged, and untracked). It uses ``--no-renames`` so both sides
of a rename are listed: a file moved out of a guarded directory still counts.

Guarded paths (the rules file's list):

* ``.codeql/**``
* ``.github/codeql/**``
* ``.github/workflows/codeql-analysis.yml``
* ``.github/actions/**`` (composite actions the workflow calls)
* the ``codeql-scan`` skill scripts, in any tree that carries them
  (``.claude/skills/``, ``src/*/skills/``, a vendored ``skills/``)

Matching is case-insensitive, because the default macOS and Windows file systems
fold case and ``.CodeQL/`` would be the same directory there. That is stricter
than a byte comparison and never lets a guarded path through.

Standard library only: this module ships in the plugin tree.
"""

from __future__ import annotations

import posixpath
import subprocess
from collections.abc import Sequence
from pathlib import Path

GIT_TIMEOUT_SECONDS = 20

_GUARDED_PREFIXES = (".codeql/", ".github/codeql/", ".github/actions/")
_GUARDED_FILES = frozenset({".github/workflows/codeql-analysis.yml"})
_CODEQL_SCAN_SCRIPTS = "skills/codeql-scan/scripts/"

#: CodeQL language names the ``codeql-scan`` wrapper accepts (``--languages`` choices
#: in ``codeql-scan/scripts/invoke_codeql_scan.py``) mapped from diff file types.
_PYTHON_SUFFIXES = (".py",)
_ACTIONS_DIR = ".github/workflows/"
_ACTIONS_SUFFIXES = (".yml", ".yaml")


class GitError(RuntimeError):
    """A git call needed by the pre-step failed. The message is safe to show."""


def run_git(repo_root: Path, args: Sequence[str]) -> str:
    """Run ``git -C repo_root args`` and return stdout.

    Raises:
        GitError: git is missing, times out, or exits non-zero.
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), *args],
            capture_output=True,
            encoding="utf-8",
            errors="surrogateescape",
            timeout=GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise GitError(f"git {args[0]} could not run") from exc
    if result.returncode != 0:
        raise GitError(f"git {args[0]} failed")
    return result.stdout


def repo_toplevel(start: Path) -> Path:
    """Return the worktree root that contains ``start``."""
    return Path(run_git(start, ["rev-parse", "--show-toplevel"]).strip())


def head_sha(repo_root: Path) -> str:
    return run_git(repo_root, ["rev-parse", "HEAD"]).strip()


def tree_is_clean(repo_root: Path) -> bool:
    """True when ``git status`` reports nothing, untracked files included."""
    status = run_git(repo_root, ["status", "--porcelain", "--untracked-files=all"])
    return status.strip() == ""


def resolve_base_ref(repo_root: Path, base_branch: str | None) -> str:
    """Return the remote-tracking ref for the default branch.

    An explicit ``base_branch`` wins. Otherwise ``refs/remotes/origin/HEAD``
    names it. There is no silent fallback to a guessed branch name: a wrong base
    would shrink the diff and let a guarded change through.

    Raises:
        GitError: the base ref cannot be resolved.
    """
    if base_branch:
        name = base_branch.removeprefix("origin/")
    else:
        pointer = run_git(repo_root, ["symbolic-ref", "--short", "refs/remotes/origin/HEAD"])
        name = pointer.strip().removeprefix("origin/")
    ref = f"origin/{name}"
    run_git(repo_root, ["rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"])
    return ref


def _split_z(output: str) -> list[str]:
    return [item for item in output.split("\0") if item]


def changed_files(repo_root: Path, base_ref: str) -> list[str]:
    """Return sorted repo-relative paths changed since the merge base.

    Covers committed, staged, unstaged, and untracked changes. Renames list both
    the old and the new path (``--no-renames``).

    Raises:
        GitError: the merge base or a diff cannot be computed.
    """
    merge_base = run_git(repo_root, ["merge-base", "HEAD", base_ref]).strip()
    tracked = _split_z(
        run_git(repo_root, ["diff", "--name-only", "--no-renames", "-z", merge_base])
    )
    untracked = _split_z(run_git(repo_root, ["ls-files", "--others", "--exclude-standard", "-z"]))
    return sorted(set(tracked) | set(untracked))


def is_guarded_path(path: str) -> bool:
    """True when ``path`` is a scanner input the amendment guards."""
    folded = posixpath.normpath(path.replace("\\", "/")).casefold()
    if folded in _GUARDED_FILES or folded.startswith(_GUARDED_PREFIXES):
        return True
    return f"/{_CODEQL_SCAN_SCRIPTS}" in f"/{folded}"


def guarded_paths(paths: Sequence[str]) -> list[str]:
    """Return the guarded paths among ``paths``, in input order."""
    return [path for path in paths if is_guarded_path(path)]


def languages_for(paths: Sequence[str]) -> list[str]:
    """Map diff file types to the CodeQL languages the wrapper can scan.

    ``.py`` maps to ``python``. A YAML file under ``.github/workflows/`` maps to
    ``actions``. Anything else maps to nothing, so an all-docs diff yields an empty
    list and the local scan is skipped instead of run on a guess.
    """
    languages: list[str] = []
    for path in paths:
        folded = path.casefold()
        if folded.endswith(_PYTHON_SUFFIXES) and "python" not in languages:
            languages.append("python")
        in_workflows = folded.startswith(_ACTIONS_DIR) and folded.endswith(_ACTIONS_SUFFIXES)
        if in_workflows and "actions" not in languages:
            languages.append("actions")
    return sorted(languages)
