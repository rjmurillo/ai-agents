#!/usr/bin/env python3
"""Build the pre-push file list from the ref lines git writes to stdin (issue #6884).

Lefthook builds its pre-push file list from ``git diff --name-only HEAD
@{push}``. When that list is empty it skips every job, including the jobs that
read the ref lines from stdin, such as the protected-branch guard. So a branch
level with its upstream could push ``HEAD:main`` with no local check.

Probed on 2026-10-23 against Lefthook 2.2.2 (tag v2.2.2, commit eb4e504b):

- A ``files:`` setting does not change that skip. It only fills ``{files}``.
- The ``files:`` command gets no stdin, so it cannot see the pushed refs.
- ``lefthook run pre-push --file <path>`` replaces the list. Jobs still get
  the stdin, globs still filter, and missing paths are kept.

``lefthook_runner.py`` therefore reads the ref lines, calls
:func:`lefthook_file_args`, and passes the result to Lefthook.

Each ref line is ``<local ref> <local sha> <remote ref> <remote sha>``:

- Delete (local sha all zeros): no files. The ref line still reaches stdin jobs.
- Update: the files that differ between the remote sha and the local sha.
- A tag on a tree: every file in the tree. A tag on a blob: no files.
- New ref (remote sha all zeros), or a remote sha this clone lacks: the files
  changed since the merge-base with the remote's default branch. With no known
  default branch, or no common history, every file in the local commit.

Renames count both paths, and deleted paths count. A push whose file union is
empty still passes :data:`PLACEHOLDER`, so the jobs that take no file list run.
No pre-push glob may match it (``tests/ci/test_lefthook_prepush_tiering.py``).
A list too long for one command line becomes ``--all-files``, so every job
still runs, over all tracked files. So does a list with a comma in a path,
because Lefthook's ``--file`` flag (urfave/cli v3.14.0) splits its value on
commas: ``--file=a,b.txt`` arrived as ``a`` and ``b.txt`` in the same probe.

Standard library only: the runner must work when the project environment is broken.
"""

from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass

# A path no pre-push glob matches. It names a push that changes no file, such as
# a branch delete, so Lefthook still runs the jobs that read the ref lines.
PLACEHOLDER = ".lefthook-push-changes-no-files"
ALL_FILES = "--all-files"
# Flags with which the caller already chose the file list. The runner then
# leaves the call alone. --files-from-stdin also needs the stdin for itself.
CALLER_FILE_FLAGS = ("--file", "--all-files", "--files-from-stdin", "--force")
# Windows has no SC_ARG_MAX. CreateProcess allows 32767 characters.
_WINDOWS_ARG_BUDGET = 30_000
_POINTER_BYTES = 8
_HEX_SHA = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")
_DEFAULT_BRANCHES = ("HEAD", "main", "master")
_GIT_TIMEOUT_SECONDS = 120

GitRunner = Callable[[Sequence[str]], subprocess.CompletedProcess[bytes]]


class PushFileListError(Exception):
    """The file list cannot be built. The push must stop, not skip its checks."""


@dataclass(frozen=True)
class RefUpdate:
    """One line of the pre-push stdin."""

    local_ref: str
    local_sha: str
    remote_ref: str
    remote_sha: str

    @property
    def is_delete(self) -> bool:
        return _is_zero(self.local_sha)

    @property
    def is_new(self) -> bool:
        return _is_zero(self.remote_sha)


def _is_zero(sha: str) -> bool:
    return set(sha) == {"0"}


def run_git(arguments: Sequence[str]) -> subprocess.CompletedProcess[bytes]:
    """Run git with ``arguments`` and capture its output as bytes."""
    try:
        return subprocess.run(
            ["git", *arguments],
            capture_output=True,
            check=False,
            timeout=_GIT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise PushFileListError(f"cannot run git {' '.join(arguments)}: {error}") from error


def parse_ref_lines(data: bytes) -> list[RefUpdate]:
    """Parse the pre-push stdin. A malformed line raises :class:`PushFileListError`.

    Only the local ref can hold a space: git writes the refspec source as typed,
    such as ``main@{1 day ago}``, while a remote ref name cannot hold one. So
    each line splits from the right. Ref names may be any bytes; only the object
    ids must be ASCII hex.
    """
    updates: list[RefUpdate] = []
    for number, line in enumerate(data.splitlines(), start=1):
        if not line.strip():
            continue
        fields = line.rsplit(b" ", 3)
        if len(fields) != 4:
            raise PushFileListError(
                f"pre-push stdin line {number} has {len(fields)} fields, expected 4: {line!r}"
            )
        local_ref, local_sha, remote_ref, remote_sha = (
            field.decode("utf-8", errors="replace") for field in fields
        )
        for sha in (local_sha, remote_sha):
            if not _HEX_SHA.fullmatch(sha):
                raise PushFileListError(
                    f"pre-push stdin line {number} has an invalid object id: {sha!r}"
                )
        updates.append(RefUpdate(local_ref, local_sha, remote_ref, remote_sha))
    return updates


def _paths(output: bytes) -> list[str]:
    return [os.fsdecode(item) for item in output.split(b"\0") if item]


def _git_paths(git: GitRunner, arguments: Sequence[str]) -> list[str]:
    result = git(arguments)
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise PushFileListError(f"git {' '.join(arguments)} failed: {detail}")
    return _paths(result.stdout)


def _object_type(git: GitRunner, sha: str) -> str | None:
    """Return the object's type after peeling tags, or None when it is missing."""
    result = git(["cat-file", "-t", f"{sha}^{{}}"])
    return (
        result.stdout.decode("ascii", errors="replace").strip() if result.returncode == 0 else None
    )


def _is_commit(git: GitRunner, sha: str) -> bool:
    """Return True when ``sha`` is a commit, or a tag that peels to one."""
    return git(["rev-parse", "--verify", "--quiet", f"{sha}^{{commit}}"]).returncode == 0


def _default_branch_sha(git: GitRunner, remote: str | None) -> str | None:
    """Return the commit of the remote's default branch, from local tracking refs."""
    # A URL or an option-like name has no tracking refs and must not reach git as a ref.
    if not remote or remote.startswith("-") or ":" in remote or any(c.isspace() for c in remote):
        return None
    for branch in _DEFAULT_BRANCHES:
        result = git(
            ["rev-parse", "--verify", "--quiet", f"refs/remotes/{remote}/{branch}^{{commit}}"]
        )
        if result.returncode == 0:
            return result.stdout.decode("ascii").strip()
    return None


def _merge_base(git: GitRunner, first: str, second: str) -> str | None:
    result = git(["merge-base", first, second])
    if result.returncode == 0:
        return result.stdout.decode("ascii").strip()
    if result.returncode == 1:
        return None  # No common history.
    detail = result.stderr.decode("utf-8", errors="replace").strip()
    raise PushFileListError(f"git merge-base {first} {second} failed: {detail}")


def _changed(git: GitRunner, old: str, new: str) -> list[str]:
    # diff-tree is plumbing, so user diff config cannot change its output.
    return _git_paths(git, ["diff-tree", "-r", "-z", "--name-only", "--no-renames", old, new])


def _ref_files(git: GitRunner, update: RefUpdate, remote: str | None) -> list[str]:
    if update.is_delete:
        return []
    if not _is_commit(git, update.local_sha):
        kind = _object_type(git, update.local_sha)
        if kind == "tree":
            # A tag on a tree has no history, so every file in the tree is new.
            return _git_paths(git, ["ls-tree", "-r", "-z", "--name-only", update.local_sha])
        if kind is not None:
            return []  # A tag on a blob names no path.
        raise PushFileListError(f"the pushed object {update.local_sha} is not in this clone")
    if not update.is_new and _is_commit(git, update.remote_sha):
        return _changed(git, update.remote_sha, update.local_sha)
    default = _default_branch_sha(git, remote)
    base = _merge_base(git, default, update.local_sha) if default else None
    if base is not None:
        return _changed(git, base, update.local_sha)
    return _git_paths(git, ["ls-tree", "-r", "-z", "--name-only", update.local_sha])


def pushed_files(
    updates: Sequence[RefUpdate], remote: str | None, git: GitRunner = run_git
) -> list[str]:
    """Return the sorted union of the files every ref update in the push changes."""
    files: set[str] = set()
    for update in updates:
        files.update(_ref_files(git, update, remote))
    return sorted(files)


def arg_budget() -> int:
    """Return the bytes the ``--file`` arguments may use on this platform."""
    try:
        limit = os.sysconf("SC_ARG_MAX")
    except (AttributeError, ValueError, OSError):
        return _WINDOWS_ARG_BUDGET
    if limit <= 0:
        return _WINDOWS_ARG_BUDGET
    # The environment shares ARG_MAX with argv on POSIX. The quarter cut leaves
    # room for Lefthook's own arguments and any later growth of the environment.
    environment = sum(
        len(os.fsencode(k)) + len(os.fsencode(v)) + 2 + _POINTER_BYTES
        for k, v in os.environ.items()
    )
    return max(limit // 4 - environment, 0)


def _arg_bytes(arguments: Sequence[str]) -> int:
    return sum(len(os.fsencode(item)) + 1 + _POINTER_BYTES for item in arguments)


def caller_chose_files(arguments: Sequence[str]) -> bool:
    """Return True when the Lefthook arguments already set the file list."""
    return any(
        item == flag or item.startswith(f"{flag}=")
        for item in arguments
        for flag in CALLER_FILE_FLAGS
    )


def lefthook_file_args(
    stdin: bytes,
    remote: str | None,
    git: GitRunner = run_git,
    budget: int | None = None,
) -> list[str]:
    """Return the Lefthook arguments that set the file list for this push.

    An empty stdin is no push, so it returns no arguments and Lefthook behaves
    as before. Raises :class:`PushFileListError` when the list cannot be built.
    """
    updates = parse_ref_lines(stdin)
    if not updates:
        return []
    files = pushed_files(updates, remote, git) or [PLACEHOLDER]
    if any("," in path for path in files):
        return [ALL_FILES]
    arguments = [f"--file={path}" for path in files]
    if _arg_bytes(arguments) > (arg_budget() if budget is None else budget):
        return [ALL_FILES]
    return arguments
