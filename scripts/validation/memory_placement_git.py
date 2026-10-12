"""Git and index reads for check_memory_placement.py.

Every function here talks to git or the filesystem; the classifier in
check_memory_placement.py stays pure. A git failure under ``--staged`` is a
``ConfigError`` (exit 2), never a silent fallback to working-tree content.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from checks_common import _git_subprocess_env, _run_subprocess  # noqa: E402

GIT_READ_TIMEOUT = 30
MEMORY_PATHSPEC = ".serena/memories"


class ConfigError(Exception):
    """Raised for a usage or environment problem; ``main`` turns it into exit 2."""


def _git_env() -> dict[str, str]:
    """Return the clean Git environment while preserving an active index."""
    env = _git_subprocess_env()
    if index_file := os.environ.get("GIT_INDEX_FILE"):
        env["GIT_INDEX_FILE"] = str(Path(index_file).absolute())
    return env


def repo_root() -> Path | None:
    """Return the repository root for the current directory, or None."""
    code, out, _ = _run_subprocess(
        ["git", "rev-parse", "--show-toplevel"],
        timeout=GIT_READ_TIMEOUT,
        cwd=Path.cwd(),
        env=_git_env(),
    )
    if code != 0:
        return None
    return Path(out.strip()).resolve()


def valid_ref(base: str) -> bool:
    """Reject a blank, control-character, or option-shaped (leading ``-``) ref."""
    return bool(base.strip()) and not base.startswith("-") and base.isprintable()


def base_tree_paths(repo_root: Path, base: str) -> set[str] | None:
    """Return every path git tracks at ``base``, or None if the ref is unusable."""
    if not valid_ref(base):
        return None
    code, out, _ = _run_subprocess(
        ["git", "ls-tree", "-r", "-z", "--name-only", base],
        timeout=GIT_READ_TIMEOUT,
        cwd=repo_root,
        env=_git_env(),
    )
    if code != 0:
        return None
    return {entry for entry in out.split("\0") if entry}


def index_paths(repo_root: Path) -> dict[str, tuple[str, str] | None]:
    """Return indexed paths with immutable modes and blob IDs."""
    code, out, err = _run_subprocess(
        ["git", "ls-files", "--stage", "-z"],
        timeout=GIT_READ_TIMEOUT,
        cwd=repo_root,
        env=_git_env(),
    )
    if code != 0:
        raise ConfigError(f"git ls-files failed ({code}): {err.strip()}")
    indexed: dict[str, tuple[str, str] | None] = {}
    for entry in out.split("\0"):
        if not entry:
            continue
        header, path = entry.split("\t", 1)
        mode, object_id, stage = header.split()
        if stage == "0":
            indexed[path] = (mode, object_id)
        else:
            indexed.setdefault(path, None)
    return indexed


def read_candidate(
    repo_root: Path,
    relpath: str,
    abspath: Path,
    index: dict[str, tuple[str, str] | None] | None,
) -> str:
    """Return the index blob when ``relpath`` is staged, else the tree file.

    Under ``--staged`` a git failure is an infrastructure error, never a
    silent fallback to working-tree content. Git symlinks are rejected because
    their index blob contains only the target path, not the target content.
    The blob ID comes from the same index snapshot as the mode, so later index
    changes cannot switch the content being validated.
    """
    if index is None:
        return abspath.read_text(encoding="utf-8", errors="replace")
    if relpath not in index:
        raise ConfigError(f"staged path is not in the index: {relpath}")
    entry = index[relpath]
    if entry is None:
        raise ConfigError(f"staged path has unresolved index entries: {relpath}")
    mode, object_id = entry
    if mode == "120000":
        raise ConfigError(f"staged symlink cannot be validated: {relpath}")
    code, out, err = _run_subprocess(
        ["git", "cat-file", "blob", object_id],
        timeout=GIT_READ_TIMEOUT,
        cwd=repo_root,
        env=_git_env(),
    )
    if code != 0:
        raise ConfigError(f"git cat-file {object_id} failed ({code}): {err.strip()}")
    return str(out)


@dataclass(frozen=True, slots=True)
class DiffEntry:
    """One added, copied, modified, or renamed path from ``git diff --name-status``.

    ``old_path`` is set only for a rename: it is the path the content had at
    the base, so an unchanged file surviving a move keeps its base class.
    """

    path: str
    old_path: str | None


def merge_base(repo_root: Path, ref: str) -> str:
    """Return the merge base of ``ref`` and HEAD, the commit a PR branched from."""
    if not valid_ref(ref):
        raise ConfigError(f"invalid --changed-since ref: {ref!r}")
    code, out, err = _run_subprocess(
        ["git", "merge-base", ref, "HEAD"],
        timeout=GIT_READ_TIMEOUT,
        cwd=repo_root,
        env=_git_env(),
    )
    if code != 0:
        raise ConfigError(
            f"git merge-base {ref} HEAD failed ({code}): {err.strip()}; "
            "fetch full history for the base ref"
        )
    return out.strip()


def parse_name_status(out: str) -> list[DiffEntry]:
    """Parse ``git diff --name-status -z`` output into entries.

    A rename or copy record is ``R<score>``, old path, new path, each NUL-separated;
    every other record is the status letter then the path. A copy is treated as
    an add because its content is new at the new path.
    """
    tokens = [token for token in out.split("\0") if token]
    entries: list[DiffEntry] = []
    position = 0
    while position < len(tokens):
        status = tokens[position]
        if status[0] in "RC":
            old, new = tokens[position + 1], tokens[position + 2]
            entries.append(DiffEntry(new, old if status[0] == "R" else None))
            position += 3
        else:
            entries.append(DiffEntry(tokens[position + 1], None))
            position += 2
    return entries


def _name_status(repo_root: Path, diff_args: list[str]) -> list[DiffEntry]:
    """Run a rename-aware ``git diff --name-status`` limited to the memory tree."""
    code, out, err = _run_subprocess(
        [
            "git",
            "diff",
            "--name-status",
            "--find-renames",
            "--diff-filter=ACMRT",
            "-z",
            *diff_args,
            "--",
            MEMORY_PATHSPEC,
        ],
        timeout=GIT_READ_TIMEOUT,
        cwd=repo_root,
        env=_git_env(),
    )
    if code != 0:
        raise ConfigError(f"git diff failed ({code}): {err.strip()}")
    return parse_name_status(out)


def staged_entries(repo_root: Path, base: str) -> list[DiffEntry]:
    """Return the index-vs-``base`` memory changes, with rename sources."""
    if not valid_ref(base):
        raise ConfigError(f"invalid --base ref: {base!r}")
    return _name_status(repo_root, ["--cached", base])


def range_entries(repo_root: Path, ref: str) -> list[DiffEntry]:
    """Return the memory changes ``ref...HEAD`` introduces, with rename sources."""
    if not valid_ref(ref):
        raise ConfigError(f"invalid --changed-since ref: {ref!r}")
    return _name_status(repo_root, [f"{ref}...HEAD"])


def read_base_blob(repo_root: Path, base: str, relpath: str) -> str:
    """Return the content of ``relpath`` as committed at ``base``."""
    code, out, err = _run_subprocess(
        ["git", "cat-file", "blob", f"{base}:{relpath}"],
        timeout=GIT_READ_TIMEOUT,
        cwd=repo_root,
        env=_git_env(),
    )
    if code != 0:
        raise ConfigError(f"git cat-file {base}:{relpath} failed ({code}): {err.strip()}")
    return str(out)
