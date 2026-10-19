"""Resolve symlinked directories inside a git ref for the dispatch closure verifier.

Git object paths do not traverse a symlink, so a path below a linked directory is
absent from a ref (ADR-119). This module lives beside
scripts/ci/verify_dispatch_closure.py and is loaded from that file's own directory,
so the trusted verifier never imports anything from the pull request's tree.
"""

from __future__ import annotations

import subprocess
from pathlib import Path, PurePosixPath

MAX_LINK_HOPS = 8
SYMLINK_MODE = "120000"

# Git configuration that makes reading untrusted objects inert. No hook can run
# and no filesystem monitor is started. A `.gitattributes` in the head tree cannot
# name a filter driver, because a driver is defined in configuration and none is
# configured. It can still select the built-in conversions (`text`, `eol`,
# `ident`), which change the bytes written to the scratch tree, so a head SHA is
# compared by blob id and never by those written bytes.
INERT_GIT = ("-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false")


def _ref_entry(tool_root: Path, ref: str, path: str) -> tuple[str, str] | None:
    """The (mode, object id) of the entry at ``path`` in ``ref``, or None if absent."""
    listing = subprocess.run(
        ["git", *INERT_GIT, "ls-tree", "-z", ref, "--", path],
        cwd=tool_root,
        capture_output=True,
        check=False,
    )
    if listing.returncode != 0:
        return None
    text = listing.stdout.decode("utf-8", errors="replace").split("\0", 1)[0]
    meta, _, name = text.partition("\t")
    fields = meta.split()
    if len(fields) != 3 or name != path:
        return None
    return fields[0], fields[2]


def link_target(link_path: str, text: str) -> str | None:
    """Resolve a tracked link's text against its directory; None if it escapes the repo.

    Same contract as ``_link_target`` in scripts/validation/effective_context_sources.py,
    kept local so the trusted verifier imports nothing from the work tree under test.
    A test pins the two together.
    """
    if text.startswith("/"):
        return None
    parts = list(PurePosixPath(link_path).parent.parts)
    for part in PurePosixPath(text).parts:
        if part == "..":
            if not parts:
                return None
            parts.pop()
        elif part != ".":
            parts.append(part)
    return "/".join(parts)


def _read_link(tool_root: Path, sha: str) -> str:
    blob = subprocess.run(
        ["git", "cat-file", "blob", sha], cwd=tool_root, capture_output=True, check=False
    )
    return blob.stdout.decode("utf-8", errors="replace")


def resolve_in_ref(tool_root: Path, ref: str, path: str) -> str | None:
    """``path`` with every symlinked directory replaced by its target, read inside ``ref``.

    Git object paths do not traverse a symlink, so `.claude/skills/<name>/x` is
    absent from a ref where `.claude/skills/<name>` is a link (ADR-119). Walk one
    component at a time; at mode 120000 read the blob as the target and resolve it
    against the link's parent. A target that is absolute or leaves the repo, a
    missing entry, or more than ``MAX_LINK_HOPS`` links returns None (fail closed).
    The final component is never followed, so a leaf link keeps its own identity.
    """
    pending = list(PurePosixPath(path).parts)
    resolved: list[str] = []
    hops = 0
    while pending:
        candidate = "/".join([*resolved, pending.pop(0)])
        entry = _ref_entry(tool_root, ref, candidate)
        if entry is None:
            return None
        mode, sha = entry
        if mode != SYMLINK_MODE or not pending:
            resolved = candidate.split("/")
            continue
        hops += 1
        target = link_target(candidate, _read_link(tool_root, sha))
        if hops > MAX_LINK_HOPS or not target:
            return None
        resolved = []
        pending = [*PurePosixPath(target).parts, *pending]
    return "/".join(resolved)


def base_blob(tool_root: Path, base_ref: str, path: str) -> bytes | None:
    """The bytes of ``path`` at ``base_ref`` in the base checkout, or None if absent."""
    resolved = resolve_in_ref(tool_root, base_ref, path)
    if resolved is None:
        return None
    result = subprocess.run(
        ["git", "cat-file", "blob", f"{base_ref}:{resolved}"],
        cwd=tool_root,
        capture_output=True,
        check=False,
    )
    return result.stdout if result.returncode == 0 else None


def blob_id(tool_root: Path, ref: str, path: str) -> str | None:
    """The object id of ``path`` at ``ref`` in the base checkout, or None if absent.

    A symlinked directory on the path is followed inside the ref (ADR-119); a
    symlink at the leaf keeps its own blob id so link retargets stay visible.
    """
    resolved = resolve_in_ref(tool_root, ref, path)
    if resolved is None:
        return None
    result = subprocess.run(
        ["git", *INERT_GIT, "rev-parse", "--verify", "--quiet", f"{ref}:{resolved}"],
        cwd=tool_root,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def in_ref(tool_root: Path, ref: str, path: str) -> bool:
    """True when ``path`` exists at ``ref`` in the base checkout."""
    return blob_id(tool_root, ref, path) is not None
