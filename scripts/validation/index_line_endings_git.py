#!/usr/bin/env python3
"""Running git for the line-ending gate, and refusing a git that cannot answer.

Split from `check_index_line_endings.py` at the 500-line `file-size` ceiling.
The seam is the subprocess boundary: everything here decides how git is invoked
and whether the running git is capable of the question, and nothing here knows
what a line-ending violation is. The gate that reads the answers, decides and
remediates is the other module; the record it decides over is
`index_line_endings_record.py`.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

_GIT_TIMEOUT_SECONDS = 120

# The git that first documented `GIT_ATTR_SOURCE`. See `require_attr_source`
# for the tagged-source evidence and for why 2.40 is not the floor.
_MINIMUM_GIT_VERSION = (2, 41)

def git_environment() -> dict[str, str]:
    """The ambient environment with every ``GIT_*`` variable removed.

    ``cwd=repo_root`` does not win against an exported ``GIT_DIR``,
    ``GIT_WORK_TREE`` or ``GIT_INDEX_FILE``. That matters twice here. The scan
    would read a repository nobody asked about and report its blobs under this
    root's name, and ``--fix`` would stage into that other repository after
    ``refuses_write_from_outside`` had already approved the current directory,
    which is exactly the disagreement that guard exists to stop. An ambient
    ``GIT_INDEX_FILE`` also collapses the two scopes: the working-index pass
    would read whatever index the variable names instead of the repository's.

    This is not hypothetical for this gate. ``git push`` exports ``GIT_DIR``
    into the pre-push hook from a linked worktree (issue #4914), and pre-push
    is one of the two places this gate runs.

    Mirrors ``scripts/ci/count_ratchet.py::git_environment``, whose rule is
    verbatim::

        return {
            name: value
            for name, value in os.environ.items()
            if not name.upper().startswith("GIT_")
        }

    ``name.upper()`` is kept, so a lowercased ``git_dir`` that a
    case-insensitive platform folds into ``GIT_DIR`` is stripped here too.

    Stricter/looser/different than canonical: identical in what it strips. The
    canonical helper's own docstring records the narrowing it already made
    against ``scripts/ci/merge_tree_materialization.py::isolated_git_environment``,
    which additionally drops ``GNUPGHOME``, ``HOME``, ``LEFTHOOK``,
    ``USERPROFILE`` and ``XDG_CONFIG_HOME``. This gate inherits that narrowing
    for the same reason the ratchet did: it runs git against the real checkout,
    where a global ``safe.directory`` entry written by ``actions/checkout`` is
    load-bearing.

    Returns a fresh dict; ``os.environ`` is never mutated.
    """
    return {
        name: value
        for name, value in os.environ.items()
        if not name.upper().startswith("GIT_")
    }


def run_git(
    repo_root: Path,
    args: list[str],
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a git command, raising RuntimeError on a non-zero exit.

    `env=None` means the stripped environment, never the ambient one: see
    `git_environment`. A caller that passes its own env has already built it
    on top of that helper.
    """
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=_GIT_TIMEOUT_SECONDS,
        check=False,
        env=git_environment() if env is None else env,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed ({result.returncode}): "
            f"{(result.stderr or '').strip()}"
        )
    return result


def run_git_paths(repo_root: Path, args: list[str], env: dict[str, str] | None = None) -> str:
    """Run a git command whose stdout carries pathnames, decoded losslessly.

    A pathname is bytes on POSIX, not text. Capturing this output through
    `encoding="utf-8", errors="replace"` maps every undecodable byte to
    U+FFFD, and that mapping cannot be reversed: the gate would report a name
    the repository does not hold, print a renormalize command for it, and hand
    `--fix` a path git cannot find. So stdout is captured raw and decoded once
    with `surrogateescape`, which round-trips. Python re-encodes argv with
    `os.fsencode`, which reverses the same escapes, so a path read here goes
    back to git as the exact bytes git emitted.

    Bytes mode is also why this call does not carry the repository's
    `errors="replace"` subprocess convention: there is no text decoding for
    that keyword to govern. `check_subprocess_encoding.py` scopes itself to
    calls that pin `encoding="utf-8"`, so this one is out of scope by
    construction rather than by suppression.

    `env=None` carries the same meaning as in `run_git`: the stripped
    environment, never the ambient one.
    """
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        capture_output=True,
        timeout=_GIT_TIMEOUT_SECONDS,
        check=False,
        env=git_environment() if env is None else env,
    )
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", "replace").strip()
        raise RuntimeError(f"git {' '.join(args)} failed ({result.returncode}): {stderr}")
    return result.stdout.decode("utf-8", "surrogateescape")



def git_version(repo_root: Path) -> tuple[int, int]:
    """The running git's `(major, minor)`.

    Only the first two components are read. Distributors append their own:
    `git version 2.39.5 (Apple Git-154)` and `git version 2.45.1.windows.1`
    are both real spellings, and neither parses as a plain three-part version.
    """
    text = run_git(repo_root, ["--version"]).stdout.strip()
    match = re.match(r"git version (\d+)\.(\d+)", text)
    if match is None:
        raise RuntimeError(f"could not read a version out of git --version: {text!r}")
    return int(match.group(1)), int(match.group(2))


def require_attr_source(repo_root: Path) -> None:
    """Refuse to answer on a git that does not know `GIT_ATTR_SOURCE`.

    Both scopes pin their attribute source with that variable. A git that does
    not know it ignores it: no error, no warning, no exit code, just the
    working tree's `.gitattributes` silently answering for a tree it does not
    describe. That is the failure `.claude/rules/ci-scripts.md` MUST-12 names,
    a run that did nothing reporting the same way as a run that succeeded, so
    this raises and reaches the exit-2 path in `main` and the False verdict in
    `validate_index_line_endings`.

    The floor is 2.41, read out of the tagged sources rather than recalled.
    `Documentation/git.txt` at `v2.40.0` contains neither `GIT_ATTR_SOURCE`
    nor `--attr-source`. At `v2.41.0` it contains both, the option verbatim::

        --attr-source=<tree-ish>::
            Read gitattributes from <tree-ish> instead of the worktree. See
            linkgit:gitattributes[5]. This is equivalent to setting the
            `GIT_ATTR_SOURCE` environment variable.

    and the variable verbatim::

        `GIT_ATTR_SOURCE`::
            Sets the treeish that gitattributes will be read from.

    2.40 is the wrong floor and an earlier revision of this file said so. Its
    release notes read "git check-attr" learned to take an optional tree-ish
    to read the .gitattributes file from, which is `git check-attr` only. The
    2.41 notes carry the general form, "git --attr-source=<tree> cmd $args" is
    a new way to have any command to read attributes not from the working tree
    but from the given tree object, and `git ls-files --eol` is one of those
    any-commands.

    The repository declares no git floor: no version constraint appears in
    `AGENTS.md` or `.agents/governance/PROJECT-CONSTRAINTS.md`, and a
    repository-wide search finds only measurements pinned to a version that
    was observed, never a minimum. So this gate carries its own.
    """
    version = git_version(repo_root)
    if version >= _MINIMUM_GIT_VERSION:
        return
    running = ".".join(str(part) for part in version)
    required = ".".join(str(part) for part in _MINIMUM_GIT_VERSION)
    raise RuntimeError(
        f"git {running} predates GIT_ATTR_SOURCE, which git {required} added. "
        "Both scopes of this check pin their attribute source with that "
        "variable, and an older git ignores it without saying so, judging "
        "stored blobs by whatever .gitattributes the working tree happens to "
        f"hold. Upgrade to git {required} or newer."
    )


def has_commits(repo_root: Path) -> bool:
    """Return True when HEAD resolves, False for an unborn branch."""
    result = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", "HEAD"],
        cwd=repo_root,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=_GIT_TIMEOUT_SECONDS,
        check=False,
        env=git_environment(),
    )
    return result.returncode == 0
