#!/usr/bin/env python3
"""Block blobs whose line endings contradict their gitattributes.

A file declared `text ... eol=lf` is supposed to hold LF in its blob. A blob
that holds CRLF anyway is not a cosmetic problem: with `core.autocrlf=input`
the clean filter rewrites CRLF to LF on read, so the checked-out copy never
matches its own blob. Git's stat cache hides that right after checkout, then
reports the file modified the moment anything touches it, and any merge that
touches the path aborts with "Your local changes to the following files would
be overwritten by merge" in a worktree nobody edited.

Two such blobs reached `main` and broke merges in every worktree until
`git add --renormalize` cleaned them. Neither the clean filter nor any local
hook ran on them, because both commits were created through the GraphQL
`createCommitOnBranch` API, which uploads file contents verbatim. That path
stays available and is documented as the workaround when a sandbox cannot run
lefthook, so nothing upstream of the stored blob can be relied on to prevent a
repeat. This check reads the stored blobs, which is the one place the defect is
always visible.

Two scopes are read, because they answer different questions and can disagree:

- `HEAD`, through an isolated index, is what a push transmits. This is the
  scope that matters for the API path and for CI.
- the working index is what the next commit will create. Staging a fix without
  committing it leaves `HEAD` bad, and scanning only the index would call that
  clean.

Exit codes follow ADR-035: 0 clean, 1 violations found, 2 git unavailable.
"""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

from scripts.validation.index_line_endings_record import (
    Violation,
    is_spellable,
    parse_violations,
)

REMEDIATION = "git add --renormalize <path>, then commit the result"

_GIT_TIMEOUT_SECONDS = 120


def _git_environment() -> dict[str, str]:
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


def _git(
    repo_root: Path,
    args: list[str],
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a git command, raising RuntimeError on a non-zero exit.

    `env=None` means the stripped environment, never the ambient one: see
    `_git_environment`. A caller that passes its own env has already built it
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
        env=_git_environment() if env is None else env,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed ({result.returncode}): "
            f"{(result.stderr or '').strip()}"
        )
    return result


def _git_paths(repo_root: Path, args: list[str], env: dict[str, str] | None = None) -> str:
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

    `env=None` carries the same meaning as in `_git`: the stripped
    environment, never the ambient one.
    """
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        capture_output=True,
        timeout=_GIT_TIMEOUT_SECONDS,
        check=False,
        env=_git_environment() if env is None else env,
    )
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", "replace").strip()
        raise RuntimeError(f"git {' '.join(args)} failed ({result.returncode}): {stderr}")
    return result.stdout.decode("utf-8", "surrogateescape")


def _ls_files_eol(repo_root: Path, env: dict[str, str] | None = None) -> str:
    """Return NUL-terminated `git ls-files --eol` output.

    `-z` is required, not cosmetic. Without it git applies `core.quotePath` and
    C-quotes any non-ASCII or control character in a path, so a violation would
    be reported under its display spelling and the remediation would name a file
    that does not exist.
    """
    return _git_paths(repo_root, ["ls-files", "--eol", "-z"], env=env)


def _head_env(repo_root: Path, index_path: str) -> dict[str, str]:
    """Environment pointing git at a scratch index and attributes from HEAD.

    `GIT_INDEX_FILE` isolates the blobs, but git still reads `.gitattributes`
    from the working tree, so an uncommitted attribute edit would judge HEAD's
    blobs by rules HEAD does not carry: adding `-text` locally would hide a
    committed violation, and removing it would invent one. `GIT_ATTR_SOURCE`
    (git 2.40+) pins the attributes to the same tree as the blobs, so the HEAD
    scope answers one question about one commit.

    The base is `_git_environment()`, not `os.environ.copy()`. Copying the
    ambient environment would carry an exported `GIT_DIR` into the isolated
    scan, so the two variables set below would isolate the index of a
    repository other than `repo_root`.
    """
    env = _git_environment()
    env["GIT_INDEX_FILE"] = index_path
    env["GIT_ATTR_SOURCE"] = "HEAD"
    _git(repo_root, ["read-tree", "HEAD"], env=env)
    return env


def _has_commits(repo_root: Path) -> bool:
    """Return True when HEAD resolves, False for an unborn branch."""
    result = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", "HEAD"],
        cwd=repo_root,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=_GIT_TIMEOUT_SECONDS,
        check=False,
        env=_git_environment(),
    )
    return result.returncode == 0


def check_repository(repo_root: Path) -> tuple[list[Violation], int]:
    """Return violations across HEAD and the working index, plus files examined.

    A path bad in both scopes is reported once, under HEAD, because that is the
    scope a push transmits and one remediation fixes both.
    """
    violations: list[Violation] = []
    examined = 0

    if _has_commits(repo_root):
        # NamedTemporaryFile would hand git an existing empty file, which
        # read-tree rejects as a malformed index, so reserve a name instead.
        with tempfile.TemporaryDirectory() as scratch:
            index_path = str(Path(scratch) / "head.index")
            env = _head_env(repo_root, index_path)
            violations, examined = parse_violations(
                _ls_files_eol(repo_root, env=env), scope="HEAD"
            )

    seen = {violation.path for violation in violations}
    staged, staged_examined = parse_violations(
        _ls_files_eol(repo_root), scope="index"
    )
    violations.extend(v for v in staged if v.path not in seen)
    return violations, max(examined, staged_examined)


def _report(violations: list[Violation], examined: int) -> None:
    """Print each violation, and a runnable command only when one exists."""
    for violation in violations:
        print(f"  {violation.render()}")
    if violations:
        print(f"index-line-endings: {len(violations)} blob(s) contradict gitattributes")
        print(f"  Fix: {REMEDIATION}")
        print("  Or re-run this check with --fix, which calls git directly.")
        _print_paste_command(violations)
    print(f"index-line-endings: {len(violations)} violation(s) in {examined} tracked files")


def _print_paste_command(violations: list[Violation]) -> None:
    """Print the copy-paste renormalize command, or say why there is none.

    A command is only worth printing when it would work. `display_path`
    escapes bytes and control characters that have no safe text spelling, and
    `shlex.quote` then quotes that escaped spelling, so for such a path the
    printed command names a file that does not exist: it would exit non-zero
    or, worse, match something else. Promising an exact command and handing
    over one that cannot remediate the violation is the failure this branch
    avoids. `--fix` has no such limit; it passes the real bytes as argv.

    For the spellable paths the quoting still matters. A tracked path may
    carry shell syntax or a leading dash, and an unquoted join would print a
    command that runs attacker-controlled text if a maintainer pasted it
    (CWE-78). `--` stops a leading-dash path from parsing as a git option.
    The quoting is POSIX-shell specific, which is the other reason `--fix`
    exists: it never builds a string.
    """
    unspellable = [v for v in violations if not is_spellable(v.path)]
    if unspellable:
        print(
            f"  No copy-paste command: {len(unspellable)} of {len(violations)} path(s) "
            "carry bytes or control characters that no shell spelling reproduces. "
            "Use --fix, which hands git the exact bytes."
        )
        return
    paths = " ".join(shlex.quote(v.path) for v in violations)
    print(f"  git add --renormalize -- {paths}")


def refuses_write_from_outside(repo_root: Path) -> bool:
    """True when the process is not standing inside ``repo_root``.

    ``.claude/rules/ci-scripts.md`` MUST-7: a script that resolves the
    repository root and then writes to it MUST confirm the current directory
    is inside the resolved root before the first write. ``--fix`` stages into
    whatever ``--repo-root`` names, so without this a mistyped root
    renormalizes a checkout nobody was looking at and leaves staged changes
    there for someone else to find.
    """
    cwd = Path.cwd().resolve()
    if cwd.is_relative_to(repo_root):
        return False
    print(
        f"Refusing to renormalize {repo_root} while running from {cwd}. "
        "--fix stages into the resolved root, and a root that is not an "
        "ancestor of the current directory means the two disagree about "
        "which tree is being changed (.claude/rules/ci-scripts.md MUST-7).",
        file=sys.stderr,
    )
    return True


def renormalize(repo_root: Path, violations: list[Violation]) -> None:
    """Run `git add --renormalize` on the violating paths, without a shell.

    Paths reach git as argv entries, so a filename carrying shell syntax is
    inert. `--` stops a leading-dash filename from parsing as an option.
    """
    if not violations:
        return
    paths = sorted({violation.path for violation in violations})
    _git(repo_root, ["add", "--renormalize", "--", *paths])
    print(f"index-line-endings: renormalized {len(paths)} path(s); commit the result")


def validate_index_line_endings(repo_root: Path) -> bool:
    """Blocking pre-PR gate. Returns False when any blob contradicts its attrs."""
    try:
        violations, examined = check_repository(repo_root)
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"[FAIL] index line endings: {exc}", file=sys.stderr)
        return False
    _report(violations, examined)
    return not violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        default=".",
        help="Repository root to inspect (default: current directory)",
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Renormalize the violating paths via git argv instead of printing a command",
    )
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    # Separate from validate_index_line_endings so a broken git invocation
    # exits 2 (config error) instead of 1 (violations found). Collapsing the
    # two would report "line endings are wrong" when git never ran.
    try:
        if args.fix and refuses_write_from_outside(repo_root):
            return 2
        violations, examined = check_repository(repo_root)
        _report(violations, examined)
        if args.fix:
            renormalize(repo_root, violations)
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"[FAIL] index line endings: {exc}", file=sys.stderr)
        return 2

    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
