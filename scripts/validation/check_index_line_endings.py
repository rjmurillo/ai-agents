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
from dataclasses import dataclass
from pathlib import Path

# `git ls-files --eol` prefixes the stored state with `i/`. `mixed` is included
# because a blob holding both endings is broken the same way a pure-CRLF one
# is; `none` means no line endings at all and cannot contradict anything.
_BAD_INDEX_STATES = frozenset({"i/crlf", "i/mixed"})

# Only these attribute values promise LF in the blob. A path marked `-text` is
# exempt by declaration, and `eol=crlf` asks for CRLF on purpose, so neither is
# a contradiction.
_LF_ATTRIBUTES = ("eol=lf",)

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


@dataclass(frozen=True)
class Violation:
    """One tracked path whose stored blob contradicts its attributes."""

    path: str
    index_state: str
    attributes: str
    scope: str = "HEAD"

    def render(self) -> str:
        return (
            f"[CRLF] {display_path(self.path)}: {self.scope} blob is "
            f"{self.index_state} but attributes say {self.attributes}"
        )


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


def display_path(path: str) -> str:
    """A path rendered for a UTF-8 stream, with undecodable bytes escaped.

    The surrogates that keep a path reversible cannot be written to stdout:
    `print` raises `UnicodeEncodeError` on them. Only the human-facing output
    is escaped. `--fix` still receives the reversible form, so the path the
    operator reads and the path git receives can differ by exactly the bytes
    that have no text spelling.
    """
    return path.encode("utf-8", "surrogateescape").decode("utf-8", "backslashreplace")


def _ls_files_eol(repo_root: Path, env: dict[str, str] | None = None) -> str:
    """Return NUL-terminated `git ls-files --eol` output.

    `-z` is required, not cosmetic. Without it git applies `core.quotePath` and
    C-quotes any non-ASCII or control character in a path, so a violation would
    be reported under its display spelling and the remediation would name a file
    that does not exist.
    """
    return _git_paths(repo_root, ["ls-files", "--eol", "-z"], env=env)


def parse_violations(output: str, scope: str = "HEAD") -> tuple[list[Violation], int]:
    """Parse NUL-terminated `git ls-files --eol -z` output.

    Each record is `i/<state> w/<state> attr/<attrs><TAB><path>`. The attribute
    field carries several space-separated values, so the path is split on the
    tab rather than on whitespace: a path containing spaces would otherwise be
    truncated and silently drop a real violation.

    Newline-separated input is accepted too, so a caller holding output from a
    git that predates `-z` still parses. A path containing a literal newline is
    only safe under `-z`, which is why the producer above always passes it.
    """
    violations: list[Violation] = []
    examined = 0
    # Do not strip newlines from a NUL record. A tracked path may legally
    # begin or end with one, and `-z` exists precisely so those survive; a
    # strip here would report a path that does not exist and hand it to --fix.
    nul_terminated = "\0" in output
    records = output.split("\0") if nul_terminated else output.splitlines()
    for record in records:
        line = record if nul_terminated else record.rstrip("\n")
        # `-z` terminates rather than separates, so the split always yields a
        # trailing empty string. That is the one record with nothing in it and
        # the only one worth passing over.
        if not line:
            continue
        # Everything else must be a row this parser understands. Skipping a
        # malformed row would let a producer change turn a broken scan into
        # "0 violations" and exit 0, which is the failure ci-scripts.md MUST-12
        # names: a run that did nothing must not report the same way as a run
        # that succeeded. Raising here reaches the exit-2 path in `main` and
        # the False verdict in the gate, so a format change fails loudly.
        if "\t" not in line:
            raise RuntimeError(
                f"git ls-files --eol emitted a row with no tab: {line!r}. "
                "The parser expects `i/<state> w/<state> attr/<attrs><TAB><path>`."
            )
        head, path = line.split("\t", 1)
        fields = head.split()
        if len(fields) < 3:
            raise RuntimeError(
                f"git ls-files --eol emitted a row with {len(fields)} field(s) "
                f"before the tab, expected at least 3: {line!r}."
            )
        examined += 1
        index_state = fields[0]
        attributes = " ".join(fields[2:])
        if index_state not in _BAD_INDEX_STATES:
            continue
        if not any(token in attributes for token in _LF_ATTRIBUTES):
            continue
        violations.append(
            Violation(
                path=path,
                index_state=index_state,
                attributes=attributes,
                scope=scope,
            )
        )
    return violations, examined


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
    """Print each violation plus the exact renormalize command that fixes it."""
    for violation in violations:
        print(f"  {violation.render()}")
    if violations:
        print(f"index-line-endings: {len(violations)} blob(s) contradict gitattributes")
        print(f"  Fix: {REMEDIATION}")
        print("  Or re-run this check with --fix, which calls git directly.")
        # shlex.quote per path, and `--` before them. A tracked path may carry
        # shell syntax or a leading dash, and an unquoted join would print a
        # command that runs attacker-controlled text if a maintainer pasted it
        # (CWE-78). The quoting is POSIX-shell specific, which is why --fix
        # exists: it passes an argument list to git and never builds a string.
        paths = " ".join(shlex.quote(display_path(v.path)) for v in violations)
        print(f"  git add --renormalize -- {paths}")
    print(f"index-line-endings: {len(violations)} violation(s) in {examined} tracked files")


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
