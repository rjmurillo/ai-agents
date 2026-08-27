#!/usr/bin/env python3
r"""Gate: no config scope flags a repository bare while it has a work tree.

Something during ``git push`` writes ``core.bare = true`` into the shared
``.git/config``. A bare repository cannot have a work tree, so every git
command needing one fails with ``fatal: this operation must be run in a work
tree``. Issue #4698 measured it twice in one session: it broke the main
checkout and three of five linked worktrees at once, and surfaced as four
unrelated-looking failures (two portability checks in the pre-PR gate, a
lefthook integration test, and plain ``git status``). Three wrong diagnoses
were attempted before the shared cause was found, including one issue filed
and retracted.

``.agents/governance/GOTCHAS.md`` records the same incident and the same
repair, quoted verbatim from its "Repair" and "Immunize" lines::

    git config core.bare false

    git config --worktree core.bare false          # in the main checkout
    git -C <each linked worktree> config --worktree core.bare false

What the gate reads, and why it is not ``--is-bare-repository``
--------------------------------------------------------------

The obvious probe is whether *this* checkout resolves bare. It is the wrong
one, because in that state nothing local can report anything: measured on
lefthook 2.1.10, lefthook runs ``git rev-parse --path-format=absolute
--show-toplevel ...`` before its first job and exits 128 on the same fatal
text, so a hook job can never speak from a bare-flagged worktree, and ``git
commit`` refuses before reaching a hook at all.

The state a hook CAN speak from is the mixed one GOTCHAS prescribes, and it is
also the state the incident left behind: the shared config says true while
this worktree carries a worktree-scoped false. Measured on git 2.43.0 with
``extensions.worktreeConfig`` enabled, an immunized checkout and its poisoned
linked worktree answer the same repository differently::

    immunized main    git config --show-scope --get-all core.bare
                      -> local\ttrue
                         worktree\tfalse
    poisoned linked   -> local\ttrue
    healthy clone     -> local\tfalse

So one scoped read answers for the whole repository, from any worktree that
still works, and it keeps working in a worktree that does not. Effective value
alone would report the immunized checkout healthy while three of its siblings
were dead.

Bareness is only a defect where a work tree is meant to exist, and a genuine
bare repository answers ``local\ttrue`` as well. The discriminator is a
``.git`` marker naming *this* repository's git directory at the working
directory or an ancestor: a directory in a normal checkout, a ``gitdir:`` file
in a linked worktree or a ``git init --separate-git-dir`` checkout. Comparing
the marker's target with ``git rev-parse --absolute-git-dir`` keeps a bare
repository nested inside an unrelated checkout out of scope.
``git worktree list --porcelain`` was probed as an alternative and rejected: it
prints ``bare`` for the corrupted checkout, the separate-git-dir checkout, and
the genuine bare repository alike.

Where it runs: first in the ``pre-commit`` and ``pre-push`` job lists, ahead of
``repair-packed-refs``. The incident produced four plausible and independent
diagnoses before the shared cause was found, so the value is one accurate
message arriving before any of the failures the corruption would otherwise be
blamed for. Run it by hand against a worktree that git already refuses; a hook
cannot, for the lefthook reason above.

Stricter/looser/different than canonical: GOTCHAS names one repair,
``git config core.bare false``. This gate reads ``--show-scope`` and names a
repair per scope that actually carries the value, because that one command
writes to the local config and cannot clear a worktree-scoped, global, or
system value. It adds the worktree-scoped immunization line only when
``extensions.worktreeConfig`` is enabled: measured, ``git config --worktree``
otherwise exits 128 with ``--worktree cannot be used with multiple working
trees unless the config extension worktreeConfig is enabled``, so printing it
unconditionally would hand the reader a command that fails.

Exit codes (ADR-035):
    0 - Success (no scope flags this work tree bare, or none applies here)
    1 - Logic error (a config scope flags a repository that has a work tree)
    2 - Config error (invalid repository root)
    3 - External failure (git missing, timed out, or failed unexpectedly)
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

# A hung git must not stall a commit or a push. Local config and rev-parse
# reads answer in milliseconds, so this only trips on a genuine hang, and the
# gate then fails closed with exit 3 rather than reporting a verified pass.
GIT_TIMEOUT_SECONDS = 5

# git refuses every command, including `git config --unset-all`, when core.bare
# holds a value it cannot parse as a boolean. Measured with core.bare=notabool:
# `git config --show-scope --get-all core.bare` exits 128 with this text.
_BAD_BOOLEAN_MARKER = "bad boolean config value"

# git reads a variable with no value as true, so an empty string belongs here.
_TRUE_VALUES = frozenset({"", "true", "yes", "on", "1"})

_SCOPE_REPAIRS = {
    "worktree": "git config --worktree core.bare false",
    "local": "git config core.bare false",
    "global": "git config --global --unset-all core.bare",
    "system": "git config --system --unset-all core.bare",
    "command": (
        "remove the command-scoped core.bare override "
        "(git -c core.bare=..., GIT_CONFIG_PARAMETERS, or GIT_CONFIG_KEY_n)"
    ),
}
_DEFAULT_REPAIR = _SCOPE_REPAIRS["local"]

_IMMUNIZATION = "git config --worktree core.bare false"

_WORK_TREE_FATAL = "fatal: this operation must be run in a work tree"


class GitExecutionError(RuntimeError):
    """Git was unavailable or failed before the gate could establish a fact."""


class NotGitRepositoryError(RuntimeError):
    """The target is explicitly outside a Git repository."""


class UnreadableCoreBareError(RuntimeError):
    """core.bare holds a value git refuses to parse, so no git command runs."""


@dataclass(frozen=True, slots=True)
class RepoHealth:
    """One health verdict for one repository."""

    status: str
    work_tree: Path | None = None
    bare_scopes: tuple[tuple[str, str], ...] = ()
    scopes_read: int = 0
    effective_bare: bool = False
    worktree_config: bool = False


def _git(repo_root: Path, *args: str, missing_ok: bool = False) -> str | None:
    """Return stdout, preserving each failure mode as its own exception."""
    git = shutil.which("git")
    if git is None:
        raise GitExecutionError("git executable not found")
    env = os.environ.copy()
    env["LC_ALL"] = "C"
    try:
        result = subprocess.run(
            [git, *args],
            cwd=str(repo_root),
            env=env,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise GitExecutionError(f"git command failed to execute: {exc}") from exc
    if result.returncode == 0:
        return result.stdout.strip("\n")
    stderr = result.stderr.strip()
    if missing_ok and result.returncode == 1:
        return None
    if _BAD_BOOLEAN_MARKER in stderr and "core.bare" in stderr:
        raise UnreadableCoreBareError(stderr)
    if "not a git repository" in stderr.lower():
        raise NotGitRepositoryError(stderr)
    raise GitExecutionError(f"git {' '.join(args)} exited {result.returncode}: {stderr}")


def _is_true(value: str) -> bool:
    """Apply git's boolean reading, where a valueless variable means true."""
    return value.strip().lower() in _TRUE_VALUES


def _scoped_core_bare(repo_root: Path) -> tuple[tuple[str, str], ...]:
    """Return every ``(scope, value)`` pair git holds for ``core.bare``."""
    raw = _git(
        repo_root, "config", "--show-scope", "--get-all", "core.bare", missing_ok=True
    )
    if not raw:
        return ()
    pairs = []
    for line in raw.splitlines():
        scope, separator, value = line.partition("\t")
        if separator:
            pairs.append((scope, value))
    return tuple(pairs)


def _marker_git_dir(marker: Path) -> Path | None:
    """Resolve the git directory a ``.git`` file points at, or None."""
    try:
        text = marker.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    for line in text.splitlines():
        before, separator, target = line.partition("gitdir:")
        if not separator or before.strip():
            continue
        path = Path(target.strip())
        if not path.is_absolute():
            path = marker.parent / path
        return path.resolve()
    return None


def _work_tree_root(start: Path, git_dir: Path) -> Path | None:
    """Return the checkout whose ``.git`` marker names ``git_dir``, or None.

    Ancestors are walked so an invocation from a subdirectory still finds the
    checkout. The marker's target is compared with the repository's own git
    directory so a bare repository sitting inside an unrelated checkout is not
    attributed to that checkout.
    """
    for candidate in (start, *start.parents):
        marker = candidate / ".git"
        if not marker.exists():
            continue
        target = marker.resolve() if marker.is_dir() else _marker_git_dir(marker)
        if target == git_dir:
            return candidate
    return None


def _worktree_config_enabled(repo_root: Path) -> bool:
    """Report whether ``extensions.worktreeConfig`` permits a worktree-scoped fix."""
    value = _git(
        repo_root, "config", "--get", "extensions.worktreeConfig", missing_ok=True
    )
    return value is not None and _is_true(value)


def diagnose(repo_root: Path) -> RepoHealth:
    """Classify the repository. Raises the typed errors above on failure."""
    scoped = _scoped_core_bare(repo_root)
    bare_scopes = tuple((scope, value) for scope, value in scoped if _is_true(value))
    if not bare_scopes:
        return RepoHealth("usable", scopes_read=len(scoped))

    raw_git_dir = _git(repo_root, "rev-parse", "--absolute-git-dir")
    if not raw_git_dir:
        raise GitExecutionError("git returned an empty git directory")

    work_tree = _work_tree_root(repo_root, Path(raw_git_dir).resolve())
    if work_tree is None:
        return RepoHealth("bare_by_design", bare_scopes=bare_scopes, scopes_read=len(scoped))

    return RepoHealth(
        "corrupted",
        work_tree=work_tree,
        bare_scopes=bare_scopes,
        scopes_read=len(scoped),
        effective_bare=_git(repo_root, "rev-parse", "--is-bare-repository") == "true",
        worktree_config=_worktree_config_enabled(repo_root),
    )


def _repair_lines(health: RepoHealth) -> list[str]:
    """One repair per scope that carries the value, plus the immunization."""
    lines = [
        _SCOPE_REPAIRS.get(scope, _DEFAULT_REPAIR) for scope, _value in health.bare_scopes
    ]
    if health.worktree_config and not any(
        scope == "worktree" for scope, _value in health.bare_scopes
    ):
        lines.append(
            f"{_IMMUNIZATION}   (in every worktree, so a later flip cannot break it)"
        )
    return lines


def _report_corruption(health: RepoHealth) -> None:
    """Name the condition, its blast radius, and a repair per poisoned scope."""
    scopes = ", ".join(f"{scope}={value or 'true'}" for scope, value in health.bare_scopes)
    print(
        f"[FAIL] core.bare is set true ({scopes}) for a repository whose work "
        f"tree is {health.work_tree}.",
        file=sys.stderr,
    )
    print(f"Every git command needing a work tree fails with: {_WORK_TREE_FATAL}.", file=sys.stderr)
    if not health.effective_bare:
        print(
            "This worktree still resolves usable, so the damage is in a config "
            "it overrides: any worktree without that override is already broken.",
            file=sys.stderr,
        )
    for line in _repair_lines(health):
        print(f"Fix: {line}", file=sys.stderr)
    print(
        "A push can write this value, so a rejected push is not by itself "
        "evidence that the branch is bad. Refs issue #4698 and "
        ".agents/governance/GOTCHAS.md.",
        file=sys.stderr,
    )


def _report_unreadable(repo_root: Path, detail: str) -> None:
    """Report a core.bare value git cannot parse, which no git command can clear."""
    print(f"[FAIL] {repo_root} has an unusable core.bare value: {detail}", file=sys.stderr)
    print(
        "git refuses every command in this repository, `git config --unset-all "
        "core.bare` included, so edit the core.bare line out of the config file "
        "by hand. Refs issue #4698.",
        file=sys.stderr,
    )


def _evaluate(repo_root: Path) -> int:
    """Evaluate once and return the ADR-035 exit code."""
    try:
        health = diagnose(repo_root)
    except NotGitRepositoryError:
        print(f"repo health: skipped, {repo_root} is not a git repository (0 scopes read)")
        return 0
    except UnreadableCoreBareError as exc:
        _report_unreadable(repo_root, str(exc))
        return 1
    except GitExecutionError as exc:
        print(f"[ERROR] Repository health could not be verified: {exc}", file=sys.stderr)
        return 3

    if health.status == "usable":
        print(
            f"repo health: core.bare read in {health.scopes_read} config scope(s), "
            f"none set true, for {repo_root}"
        )
        return 0
    if health.status == "bare_by_design":
        print(
            f"repo health: skipped, {repo_root} is a bare repository with no "
            "work tree (1 of 1 read scope expected to be bare)"
        )
        return 0

    _report_corruption(health)
    return 1


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns an ADR-035 exit code."""
    args = argv if argv is not None else sys.argv[1:]
    repo_root = Path(args[0]).resolve() if args else Path(__file__).resolve().parents[2]
    if not repo_root.is_dir():
        print(f"[FAIL] Invalid repository root: {repo_root}", file=sys.stderr)
        return 2
    return _evaluate(repo_root)


if __name__ == "__main__":
    raise SystemExit(main())
