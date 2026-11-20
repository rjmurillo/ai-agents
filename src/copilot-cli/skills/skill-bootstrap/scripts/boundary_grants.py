"""Grant parsing and path classification for bootstrap_boundary verify.

Split from bootstrap_boundary.py to keep that script under the file-size limit. Stdlib
only, so it runs from any plugin root beside the script that imports it.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from pathlib import Path, PurePosixPath
from typing import Any

Payload = dict[str, Any]
Grants = list[tuple[PurePosixPath, bool]]


class ConfigError(Exception):
    """Bad input: exit 2."""


def posix(value: str) -> PurePosixPath:
    return PurePosixPath(value.replace("\\", "/").strip("/"))


def parse_grants(
    root: Path, values: list[str], skills_roots: tuple[str, ...], flag: str = "--also-allow"
) -> Grants:
    """Return each grant with whether it is a directory grant (written with a trailing `/`).

    `skills_roots` are the repo-relative skills roots a grant may not overlap. `flag` names the
    option in error messages, so `--also-create` grants share the same
    checks and report their own flag.
    """
    allowed = []
    for value in values:
        rel = posix(value)
        target = (root / Path(*rel.parts)).resolve()
        if not rel.parts or ".." in rel.parts or root not in target.parents:
            raise ConfigError(f"{flag} {value!r} is not a path inside the repository")
        if rel.parts[0] == ".git":
            raise ConfigError(f"{flag} {value!r} names git internals")
        for skills_root in map(PurePosixPath, skills_roots):
            if rel == skills_root or rel in skills_root.parents or skills_root in rel.parents:
                raise ConfigError(
                    f"{flag} {value!r} overlaps {skills_root}; use --name or --update"
                )
        allowed.append((rel, value.replace("\\", "/").endswith("/")))
    return allowed


# A created file must be a regular file: `_hash` in bootstrap_boundary writes
# `<sha256>:<mode>` for one, and `symlink:` or `dir:` for a link or nested repository.
_REGULAR_FILE_STATE = re.compile(r"\?\?\|[0-9a-f]{64}:")
# Files that change what git reports for their directory. A new one could hide later
# writes, because verify does not hash ignored files under a grant.
_GIT_CONTROL_FILES = frozenset({".gitignore", ".gitattributes"})
_LS_TREE_BATCH = 100


def covered(candidate: PurePosixPath, grants: Grants) -> bool:
    """Return whether any grant covers the path: an exact file or a directory grant above it."""
    return any(
        candidate == extra or (is_dir and extra in candidate.parents) for extra, is_dir in grants
    )


def new_untracked(
    before: Payload, after: Payload, create_grants: Grants, git: Callable[..., str]
) -> set[str]:
    """Return the paths under a create grant that are new regular files, untracked now.

    A path in the snapshot was dirty or untracked already, so it is not new. A path HEAD
    tracks is never new either: `git rm --cached` on a clean file, then an edit, reports
    both `D ` and `??` for it, and the status map keeps only the last code. A new symlink
    or nested repository is not a created file. `git` runs a git command in the
    repository and returns its stdout. With no create grant, git is not called.
    """
    fresh = sorted(
        path
        for path, state in after["paths"].items()
        if path not in before["paths"]
        and _REGULAR_FILE_STATE.match(state)
        and covered(PurePosixPath(path), create_grants)
    )
    if not fresh or not before["head"]:
        return set(fresh)
    tracked: set[str] = set()
    for start in range(0, len(fresh), _LS_TREE_BATCH):
        batch = fresh[start : start + _LS_TREE_BATCH]
        listed = git(
            "--literal-pathspecs",
            "ls-tree",
            "-z",
            "--name-only",
            "--full-tree",
            before["head"],
            "--",
            *batch,
        )
        tracked.update(listed.split("\0"))
    return set(fresh) - tracked


def is_git_control_file(path: str) -> bool:
    """Return whether the path is a `.gitignore` or `.gitattributes`, in any letter case.

    git honors `.GITIGNORE` on a case-insensitive filesystem, so the match ignores case.
    """
    return PurePosixPath(path).name.casefold() in _GIT_CONTROL_FILES


def hidden_control_files(
    ignored: Iterable[str], grants: Payload, reported: set[str]
) -> list[Payload]:
    """Return one violation per ignored `.gitignore` or `.gitattributes` under a create grant.

    A `.gitignore` that ignores itself never shows in `git status`, so `classify` never sees
    it. Verify lists the ignored file names under the create grants and passes them here. A
    path an `--also-allow` grant covers, or one already reported, is skipped. The snapshot
    does not record these files, so a self-ignoring control file that predates the run
    also fails; that is the safe side.
    """
    return [
        {"kind": "create-only-changed", "path": path}
        for path in sorted(set(ignored) - reported)
        if is_git_control_file(path) and not covered(PurePosixPath(path), grants["also_allow"])
    ]


def classify(path: str, rel: PurePosixPath, grants: Payload) -> str | None:
    """Return the violation kind for one changed path, or None when authorized.

    An `--also-allow` grant wins over an `--also-create` grant. A path under a create grant
    is authorized only when it is a new regular file that is not a `.gitignore` or
    `.gitattributes`.
    """
    candidate = PurePosixPath(path)
    if covered(candidate, grants["also_allow"]):
        return None
    if covered(candidate, grants["also_create"]):
        if is_git_control_file(path) or path not in grants["created"]:
            return "create-only-changed"
        return None
    if rel not in candidate.parents or len(candidate.relative_to(rel).parts) < 2:
        return "outside-boundary"
    skill = candidate.relative_to(rel).parts[0]
    if skill in grants["updates"]:
        return None
    if skill in grants["existing"]:
        return "unauthorized-update"
    return None if skill in grants["names"] else "outside-boundary"
