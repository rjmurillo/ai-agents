"""Grant parsing and path classification for bootstrap_boundary verify.

Split from bootstrap_boundary.py to keep that script under the file-size limit. Stdlib
only, so it runs from any plugin root beside the script that imports it.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path, PurePosixPath
from typing import Any

Payload = dict[str, Any]


class ConfigError(Exception):
    """Bad input: exit 2."""


def posix(value: str) -> PurePosixPath:
    return PurePosixPath(value.replace("\\", "/").strip("/"))


def parse_grants(
    root: Path, values: list[str], skills_roots: tuple[str, ...], flag: str = "--also-allow"
) -> list[tuple[PurePosixPath, bool]]:
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


def covered(posix: PurePosixPath, grants: list[tuple[PurePosixPath, bool]]) -> bool:
    """Return whether any grant covers the path: an exact file or a directory grant above it."""
    return any(posix == extra or (is_dir and extra in posix.parents) for extra, is_dir in grants)


def new_untracked(before: Payload, after: Payload, git: Callable[..., str]) -> set[str]:
    """Return paths absent from the snapshot that are untracked now, the only create-only writes.

    A path in the snapshot was dirty or untracked already, so it is not new. A path HEAD
    tracks is never new either: `git rm --cached` on a clean file, then an edit, reports
    both `D ` and `??` for it, and the status map keeps only the last code. `git` runs a
    git command in the repository and returns its stdout.
    """
    fresh = {
        path
        for path, state in after["paths"].items()
        if path not in before["paths"] and state.startswith("??|")
    }
    if not fresh or not before["head"]:
        return fresh
    listed = git(
        "--literal-pathspecs",
        "ls-tree",
        "-z",
        "--name-only",
        "--full-tree",
        before["head"],
        "--",
        *sorted(fresh),
    )
    return fresh - set(listed.split("\0"))


def classify(path: str, rel: PurePosixPath, grants: Payload, ignored: bool = False) -> str | None:
    """Return the violation kind for one changed path, or None when authorized.

    An `--also-allow` grant wins over an `--also-create` grant. A path under a create grant
    is authorized only when it is a new untracked file; an ignored one never ships.
    """
    posix = PurePosixPath(path)
    if covered(posix, grants["also_allow"]):
        return None
    if covered(posix, grants["also_create"]):
        if ignored:
            return "ignored-in-boundary"
        return None if path in grants["created"] else "create-only-changed"
    if rel not in posix.parents or len(posix.relative_to(rel).parts) < 2:
        return "outside-boundary"
    skill = posix.relative_to(rel).parts[0]
    if skill in grants["updates"]:
        return None
    if skill in grants["existing"]:
        return "unauthorized-update"
    return None if skill in grants["names"] else "outside-boundary"
