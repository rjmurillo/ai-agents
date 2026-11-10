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

Guarded paths (the rules file's list; ``GUARDED_*`` below is the single copy):

* ``.codeql/**`` (and the ``.codeql`` entry itself)
* ``.github/codeql/**``
* every file under ``.github/workflows/``, ``.yml`` and ``.yaml`` alike (any workflow can
  upload SARIF; debate log 4)
* ``.github/actions/**`` (composite actions the workflow calls)
* the ``codeql-scan`` skill scripts, in any tree that carries them
  (``.claude/skills/``, ``src/*/skills/``, a vendored ``skills/``)

A changed symlink is guarded when its name is guarded or its resolved target is. A
bare directory entry (a symlink or file standing where a guarded directory was) is
guarded too.

Matching is case-insensitive, because the default macOS and Windows file systems
fold case and ``.CodeQL/`` would be the same directory there. That is stricter
than a byte comparison and never lets a guarded path through.

Standard library only: this module ships in the plugin tree.
"""

from __future__ import annotations

import os
import posixpath
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path

GIT_TIMEOUT_SECONDS = 20

#: The guarded paths, in one place. Directories match the directory entry itself and
#: everything under it. ``GUARDED_SCRIPT_DIR`` matches under any parent (every tree that
#: carries the ``codeql-scan`` skill). Change the guard here, nowhere else.
GUARDED_DIRS = (".codeql", ".github/codeql", ".github/workflows", ".github/actions")
GUARDED_SCRIPT_DIR = "skills/codeql-scan/scripts"
SYMLINK_MODE = "120000"

#: CodeQL language names the ``codeql-scan`` wrapper accepts (``--languages`` choices
#: in ``codeql-scan/scripts/invoke_codeql_scan.py``) mapped from diff file types.
_PYTHON_SUFFIXES = (".py",)
_ACTIONS_DIR = ".github/workflows/"
_ACTIONS_SUFFIXES = (".yml", ".yaml")


class GitError(RuntimeError):
    """A git call needed by the pre-step failed. The message is safe to show."""


def decode_path(raw: bytes) -> str:
    """Decode git output without losing bytes.

    ``os.fsdecode`` maps an undecodable byte to a surrogate escape, so the path
    round-trips and ``is_unreadable`` can see it. Where the platform codec raises
    instead (Windows), fall back to U+FFFD, which ``is_unreadable`` also catches.
    """
    try:
        return os.fsdecode(raw)
    except UnicodeDecodeError:
        return raw.decode("utf-8", errors="replace")


def is_unreadable(text: str) -> bool:
    """True when ``text`` holds U+FFFD or a surrogate: a path git gave in bytes we could
    not read. The guard cannot prove such a path is outside the guarded set, so it
    fails closed and treats it as guarded."""
    return any(ch == "\ufffd" or "\ud800" <= ch <= "\udfff" for ch in text)


def display(text: str) -> str:
    """A safe string for output: undecodable bytes shown as escapes."""
    return text.encode("utf-8", errors="backslashreplace").decode("ascii", errors="replace")


def run_git(repo_root: Path, args: Sequence[str]) -> str:
    """Run ``git -C repo_root args`` and return stdout decoded by ``decode_path``.

    Output is read as bytes, never through ``text=`` or ``errors="replace"``, so a
    non-UTF-8 path name is not rewritten into a different one.

    Raises:
        GitError: git is missing, times out, or exits non-zero.
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), *args],
            capture_output=True,
            timeout=GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise GitError(f"git {args[0]} could not run") from exc
    if result.returncode != 0:
        raise GitError(f"git {args[0]} failed")
    return decode_path(result.stdout)


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
    """True when ``path`` is a scanner input the amendment guards.

    A directory entry matches as well as the files under it: a change to ``.codeql``
    itself (a file or symlink replacing the directory) is a change to the scanner
    input. Case is folded, separators and ``./`` are normalized.
    """
    if is_unreadable(path):
        return True
    folded = posixpath.normpath(path.replace("\\", "/")).casefold().rstrip("/")
    if any(folded == d or folded.startswith(d + "/") for d in GUARDED_DIRS):
        return True
    return f"/{GUARDED_SCRIPT_DIR}/" in f"/{folded}/"


UNRESOLVABLE = "\ufffd"


def _symlink_target(repo_root: Path, path: str) -> str | None:
    """Repo-relative POSIX target of the symlink at ``path``.

    Resolves chains. Returns None when the link no longer exists in the working tree
    (a deletion: judged by name only) or points outside the repository. Returns
    ``UNRESOLVABLE`` when the link exists but its target cannot be read or resolved,
    or its path or target holds bytes that did not decode: ``is_guarded_path`` treats
    that as guarded.
    """
    link = repo_root / path
    try:
        if not link.is_symlink():
            return None
        os.readlink(link)
        real = Path(os.path.realpath(link, strict=False))
        relative = os.path.relpath(real, os.path.realpath(repo_root))
    except (OSError, ValueError):
        return UNRESOLVABLE
    if is_unreadable(relative):
        return UNRESOLVABLE
    if relative == ".." or relative.startswith(".." + os.sep):
        return None
    return Path(relative).as_posix()


def changed_symlinks(repo_root: Path, base_ref: str) -> dict[str, str | None]:
    """Map each changed symlink entry to its resolved repo-relative target.

    Reads ``git diff --raw`` modes: an entry whose old or new mode is ``120000`` is a
    symlink (so a symlink replaced by a file, or the reverse, is seen). Untracked
    symlinks are found on disk. A deleted or broken link maps to None.

    Raises:
        GitError: the merge base or the diff cannot be computed.
    """
    merge_base = run_git(repo_root, ["merge-base", "HEAD", base_ref]).strip()
    raw = run_git(repo_root, ["diff", "--raw", "--no-renames", "-z", merge_base])
    tokens = _split_z(raw)
    found: dict[str, str | None] = {}
    for header, path in zip(tokens[0::2], tokens[1::2], strict=False):
        modes = header.lstrip(":").split()[:2]
        if SYMLINK_MODE in modes:
            found[path] = _symlink_target(repo_root, path)
    for path in _split_z(run_git(repo_root, ["ls-files", "--others", "--exclude-standard", "-z"])):
        if (repo_root / path).is_symlink():
            found[path] = _symlink_target(repo_root, path)
    return found


def guarded_paths(
    paths: Sequence[str], symlink_targets: Mapping[str, str | None] | None = None
) -> list[str]:
    """Return the guarded paths among ``paths``, in input order.

    A path is guarded by its own name, or when it is a changed symlink whose resolved
    target is a guarded path.
    """
    links = symlink_targets or {}
    return [
        path
        for path in paths
        if is_guarded_path(path)
        or (links.get(path) is not None and is_guarded_path(str(links[path])))
    ]


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
