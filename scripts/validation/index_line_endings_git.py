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

from scripts.validation.index_line_endings_record import display_path

_GIT_TIMEOUT_SECONDS = 120

# Windows CreateProcess caps a command line at 32767 characters; POSIX raises
# E2BIG well above that. Mirrors `scripts/ci/count_ratchet.py`, whose comment
# and value are verbatim::
#
#     # Windows CreateProcess caps a command line at 32767 characters; POSIX
#     # raises E2BIG well above that. Batching at 24000 bytes keeps a single
#     # scan below both without needing a platform check.
#     ARGV_BUDGET_BYTES = 24000
ARGV_BUDGET_BYTES = 24000

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


def _failure(args: list[str], returncode: int, stderr: str) -> RuntimeError:
    """The error a failed git call raises, with nothing raw left in it.

    Both halves are contributor-controlled. `args` carries the tracked path
    `--fix` is renormalizing, and git echoes that path back in `stderr`. This
    message reaches a maintainer's terminal and a CI log through `main`, so a
    newline in a filename forges a line here exactly as it would in the report
    (CWE-117) and a bidi control disguises one (CWE-451). `display_path` is
    the same escaping the report uses, applied at the other end of the gate.
    """
    rendered = " ".join(display_path(arg) for arg in args)
    return RuntimeError(
        f"git {rendered} failed ({returncode}): {display_path(stderr.strip())}"
    )


def run_git(
    repo_root: Path,
    args: list[str],
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a git command, raising RuntimeError on a non-zero exit.

    `env=None` means the stripped environment, never the ambient one: see
    `git_environment`. A caller that passes its own env has already built it
    on top of that helper.

    Every call sets `GIT_LITERAL_PATHSPECS`. A tracked filename is a path, and
    git reads a trailing argument as a pathspec: `*.md` globs and
    `:(exclude)handoff.md` is magic. `--` stops option parsing and does nothing
    about either. Measured on git 2.51.0 against a repository holding a file
    literally named `*.md` plus an unrelated `other.md` with an uncommitted
    edit, `git add --renormalize -- '*.md'` staged both. Setting it here rather
    than at the two call sites that pass pathspecs means a third one cannot
    forget.
    """
    resolved = dict(git_environment() if env is None else env)
    resolved["GIT_LITERAL_PATHSPECS"] = "1"
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=_GIT_TIMEOUT_SECONDS,
        check=False,
        env=resolved,
    )
    if result.returncode != 0:
        raise _failure(args, result.returncode, result.stderr or "")
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
    environment, never the ambient one, and `GIT_LITERAL_PATHSPECS` is set for
    the same reason.
    """
    resolved = dict(git_environment() if env is None else env)
    resolved["GIT_LITERAL_PATHSPECS"] = "1"
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        capture_output=True,
        timeout=_GIT_TIMEOUT_SECONDS,
        check=False,
        env=resolved,
    )
    if result.returncode != 0:
        raise _failure(args, result.returncode, result.stderr.decode("utf-8", "replace"))
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

    The HEAD scope pins its attribute source with that variable, and only that
    scope: the index scope points `GIT_WORK_TREE` at an empty directory
    instead, so git falls back to the staged attributes with no variable
    involved. A git that does not know `GIT_ATTR_SOURCE` ignores it: no error,
    no warning, no exit code, just the working tree's `.gitattributes` silently
    answering for the committed tree it does not describe. That is the failure
    `.claude/rules/ci-scripts.md` MUST-12 names, a run that did nothing
    reporting the same way as a run that succeeded, so
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
        "The HEAD scope of this check pins its attribute source with that "
        "variable, and an older git ignores it without saying so, judging "
        "committed blobs by whatever .gitattributes the working tree happens "
        f"to hold. Upgrade to git {required} or newer."
    )


def has_commits(repo_root: Path) -> bool:
    """True when HEAD resolves. False only for a repository with no commits.

    `git rev-parse --verify --quiet HEAD` answers non-zero and empty for three
    different repositories: one that has never been committed to, one whose
    HEAD names a branch somebody deleted, and one whose HEAD is unreadable.
    Reading that single answer as "no commits" skips the HEAD scope silently,
    which halves the gate on a repository that does have commits to check.

    Mirrors `scripts/validation/portability_git.py::_no_commits_or_refuse`,
    whose reasoning is verbatim::

        Refs are only the reachable half of the answer. Deleting every ref
        leaves the commits sitting in the object database, where a pseudoref
        such as `ORIG_HEAD` still names them, so no refs is not yet proof that
        nothing was committed. The object database is the question with an
        answer, and it is only asked in the state no healthy repository
        reaches.

    Stricter/looser/different than canonical: same two probes in the same
    order, different failure channel. That function returns a reason string to
    a caller that decides; this raises, because `check_repository`'s callers
    already turn a `RuntimeError` into the ADR-035 exit 2 and the False gate
    verdict, and there is no third outcome for this gate to report.
    """
    resolved = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", "HEAD"],
        cwd=repo_root,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=_GIT_TIMEOUT_SECONDS,
        check=False,
        env=git_environment(),
    )
    if resolved.returncode == 0:
        return True

    refs = run_git(repo_root, ["for-each-ref", "--format=%(objectname)", "--count=1"])
    if refs.stdout.strip():
        raise RuntimeError(
            "HEAD does not resolve but the repository has refs, so it holds "
            "commits this check cannot read. Refusing rather than reporting "
            "the committed scope clean."
        )

    objects = run_git(
        repo_root, ["cat-file", "--batch-check=%(objecttype)", "--batch-all-objects"]
    )
    if "commit" in objects.stdout.split():
        raise RuntimeError(
            "HEAD does not resolve and no ref survives it, but the object "
            "database still holds commits, so this is a repository whose refs "
            "were removed rather than one that was never committed to. "
            "Refusing rather than reporting the committed scope clean."
        )
    return False


def top_level(repo_root: Path) -> Path:
    """The root of the whole working tree, whatever directory was named.

    `git ls-files` lists the subtree under its current directory, so a scan
    started from a subdirectory silently covers only that subtree. Measured on
    git 2.51.0 in a repository holding one bad blob under `other/`:
    `git ls-files --eol` returns 2 rows from the top level and 0 from `sub/`.
    `--repo-root` defaults to `.`, so running the CLI from anywhere but the
    root would exit 0 over a repository this gate exists to fail.

    This is also the value `refuses_write_from_outside` compares against, so
    resolving it here keeps the read scope and the write target the same tree.
    """
    return Path(run_git(repo_root, ["rev-parse", "--show-toplevel"]).stdout.strip()).resolve()


def git_path(repo_root: Path, relative: str) -> Path:
    """Where git keeps `relative`, as an absolute path.

    `git rev-parse --git-path` is the only thing that knows. It routes the
    per-worktree names to the worktree-private directory and the shared ones,
    `objects` and `info/attributes` among them, to the common directory. Its
    answer can be relative, and it is relative to the git invocation's working
    directory, which is `repo_root` and not this process's.
    """
    answer = Path(run_git(repo_root, ["rev-parse", "--git-path", relative]).stdout.strip())
    return (repo_root / answer).resolve()


def refuse_local_attribute_overrides(repo_root: Path) -> None:
    """Refuse when `$GIT_DIR/info/attributes` can outrank the pinned source.

    Git's attribute precedence puts `$GIT_DIR/info/attributes` above the
    per-tree `.gitattributes`, and `GIT_ATTR_SOURCE` replaces only the tree
    source. Measured on git 2.51.0 against a repository holding a committed
    CRLF blob under `*.md text`: with `GIT_ATTR_SOURCE=HEAD` alone the row
    reads `attr/text eol=lf` and the blob is a violation; adding
    `h.md -text` to `.git/info/attributes` turns the same row into
    `attr/-text` and the violation disappears. `docs/autonomous-pr-monitor.md`
    records the same precedence for the merge attribute, naming
    "`.gitattributes`, `.git/info/attributes`, or a global attributes file".

    That file is local and unversioned, so pre-push would report clean on a
    blob a fresh CI clone still fails on: the split-verdict this gate exists
    to prevent, pointed the other way. Git offers no environment override for
    it, so the honest move is to stop rather than answer a question the local
    checkout has already changed. An empty file changes nothing and is
    allowed.

    The path is asked for with `--git-path`, not assembled from
    `--absolute-git-dir`. In a linked worktree those differ and only the first
    is right: measured in this repository's own worktree,
    `--absolute-git-dir` returns `.git/worktrees/claude-fix-crlf-renormalize`
    while `--git-path info/attributes` returns the main checkout's
    `.git/info/attributes`. Git routes that file through the common directory,
    so a check that looked in the worktree-private directory would never find
    the file git actually reads, in exactly the setup this repository works in.

    `actions/checkout` writes no such file, so CI never reaches this.
    """
    attributes = git_path(repo_root, "info/attributes")
    if not attributes.is_file() or attributes.stat().st_size == 0:
        return
    raise RuntimeError(
        f"{attributes} outranks the attribute source this check pins. Git reads "
        "$GIT_DIR/info/attributes above the per-tree .gitattributes, and "
        "GIT_ATTR_SOURCE replaces only the tree source, so a `-text` line there "
        "hides a committed violation from this run while a fresh clone still "
        "carries it. Move or empty that file and re-run."
    )


def attribute_isolation(empty_attributes: Path) -> dict[str, str]:
    """Environment entries that take the global and system files out of the answer.

    Both are lower precedence than the pinned tree source, so neither can hide
    a violation whose attributes the tree already states. Measured on git
    2.51.0: a global `core.attributesFile` saying `h.md -text` does not change
    a row the tree already marks `text`. They are reachable in the other
    direction, where the tree says nothing about `text` or `eol` for a path and
    a local file supplies `eol=lf`, which invents a violation the commit does
    not carry. Removing both leaves the verdict a function of the repository
    alone.

    `core.attributesFile` is redirected through `GIT_CONFIG_COUNT` rather than
    `-c`, which keeps every isolation knob in the environment dict instead of
    splitting them across argv. `git_environment` has already stripped any
    ambient `GIT_CONFIG_*`, so index 0 is free. `tests/conftest.py` uses the
    same mechanism for `commit.gpgsign` and records why: it "gives it
    command-line precedence over host config".
    """
    return {
        "GIT_ATTR_NOSYSTEM": "1",
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "core.attributesFile",
        "GIT_CONFIG_VALUE_0": str(empty_attributes),
    }


def argv_batches(paths: list[str], budget: int | None = None) -> list[list[str]]:
    """Split `paths` into batches sized in UTF-8 bytes.

    Every path the gate hands git goes on one command line, and the violating
    set has no bound: a repository that took a hook-free path once can take it
    for a thousand files. Mirrors `scripts/ci/count_ratchet.py::chunk`, whose
    rule is verbatim::

        A batch holding more than one path stays under ``budget``. A single
        path that exceeds the budget on its own gets a batch to itself and is
        still scanned, because dropping it would silently shrink the count.

    Stricter/looser/different than canonical: the same rule, including the
    over-budget single path. Dropping one here would leave a violation
    unremediated while the run reported the rest fixed, which is the same
    silent shrink under a different name. One mechanical difference: the
    canonical binds the budget as a default argument, and this reads the module
    constant at call time, so a test that lowers `ARGV_BUDGET_BYTES` actually
    reaches the batching. Bound as a default, a monkeypatched constant does not,
    and the integration test for this was inert until the mutation check caught
    it.
    """
    limit = ARGV_BUDGET_BYTES if budget is None else budget
    batches: list[list[str]] = []
    current: list[str] = []
    size = 0
    for path in paths:
        cost = len(path.encode("utf-8", "surrogateescape")) + 1
        if current and size + cost > limit:
            batches.append(current)
            current = []
            size = 0
        current.append(path)
        size += cost
    if current:
        batches.append(current)
    return batches


def worktree_edits(repo_root: Path, paths: list[str]) -> list[str]:
    """Targets whose working copy differs from the index by more than CR.

    `git add --renormalize <path>` stages the working copy, not a normalized
    copy of the index blob, so any other uncommitted change to that file rides
    along into the index. Measured on git 2.51.0: with an unstaged
    `UNRELATED EDIT` line added to a violating file, `--fix` exits 0 and the
    staged blob then contains that line. A file deleted from the working tree
    is worse: `git add --renormalize` exits 128 with `unable to stat`.

    `--numstat -z --ignore-cr-at-eol` is the predicate that separates the two
    cases, and `--name-only` is not. Measured on the same git: for a working
    copy that differs from the index only in CR at end of line, which is every
    legitimate target of this gate, `--name-only --ignore-cr-at-eol` still
    lists the path while `--numstat --ignore-cr-at-eol` emits nothing. The
    unrelated edit emits `1\t0\thandoff.md` and the local deletion
    `0\t2\thandoff.md`.
    """
    edited: list[str] = []
    for batch in argv_batches(paths):
        output = run_git_paths(
            repo_root, ["diff", "--numstat", "-z", "--ignore-cr-at-eol", "--", *batch]
        )
        edited.extend(record.split("\t", 2)[2] for record in output.split("\0") if record)
    return edited
