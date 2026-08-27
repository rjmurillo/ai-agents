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
bare repository answers ``local\ttrue`` as well. The question the discriminator
has to answer is whether the repository's **main** work tree is meant to exist,
not whether the checkout being read has one.

The two are not the same, and reading the second is what made this gate print
destructive advice for a healthy layout. ``git clone --bare seed bareA.git``
followed by ``git -C bareA.git worktree add wtA master`` is an ordinary git
setup. ``wtA`` is a live checkout, ``git -C wtA status`` works, and ``wtA``
carries a ``gitdir:`` marker naming its own private git directory, so anchoring
on ``git rev-parse --absolute-git-dir`` finds a marker and calls the repository
corrupted. It is not: ``local\ttrue`` there is the bare parent's config, read
through the worktree, exactly as designed. Running the ``git config core.bare
false`` the gate printed writes into that shared config and breaks the bare
parent (``git -C bareA.git status`` then fails) along with every sibling
worktree.

So the anchor is ``git rev-parse --path-format=absolute --git-common-dir``,
which answers the same shared path from the main checkout and from every linked
worktree, and the main work tree is whichever of these names it:

* a checkout at the working directory or an ancestor whose ``.git`` marker
  resolves to the common directory. A ``.git`` directory in a normal checkout,
  or a ``gitdir:`` file in a ``git init --separate-git-dir`` checkout, which
  ``git worktree list`` no longer reports once the value is set.
* otherwise the first ``worktree`` line of ``git worktree list --porcelain``,
  which is the main worktree. This is the case a linked worktree needs, since
  the main checkout is usually not one of its ancestors. Only that path is read
  from the listing: its ``bare`` attribute is printed for the corrupted
  checkout, the separate-git-dir checkout, and the genuine bare repository
  alike, so it cannot carry the verdict.

That path still needs corroboration, because git derives a bare repository's
main-worktree path by stripping a trailing ``.git`` component: measured on git
2.43.0, a bare repository at ``dirD/.git`` reports ``worktree dirD`` and a
poisoned checkout at ``corrupt/seed`` reports ``worktree corrupt/seed``, so the
reported path is a pure function of the common directory and carries no
evidence of its own.

What separates them is repository metadata, not a directory listing. A checkout
has a staged index; a bare repository has none. Measured on git 2.43.0::

    seed/.git/index                    True    ordinary checkout
    corrupt/.git/index                 True    checkout later flagged bare
    dirD/.git/index                    False   git clone --bare seed dirD/.git
    holder/.git/index                  False   the same, with an unrelated
                                               README sitting beside it
    bareA.git/index                    False   bare repository that has handed
                                               out a linked worktree
    bareA.git/worktrees/wtA/index      True    that worktree's own index

The listing read stays as a second, independent condition, because a bare
repository that someone has run ``git read-tree`` inside does acquire an index
while its phantom work tree still holds nothing but ``.git``. Both conditions
have to hold: metadata proving a main work tree was ever staged, and content
proving one is there now. A directory holding files beside a bare repository's
``.git`` is neither, and reading content alone called that corrupted.

Ambiguity resolves toward "bare by design" on purpose. A miss leaves the reader
with the four confusing failures this gate front-runs, which is the pre-gate
status quo; a false alarm hands the reader a command that destroys a healthy
repository. Only the second is irreversible, so a main work tree that holds no
content is treated as absent.

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

# git resolves the repository's location from the environment before it reads
# any config, so an inherited value here makes every answer below describe a
# different repository than the one the gate was pointed at. Measured on git
# 2.43.0 against a corrupted checkout with GIT_DIR naming an unrelated bare
# repository: `rev-parse --git-common-dir` and `worktree list --porcelain` both
# answered for that other repository, turning live corruption into a verified
# pass. GIT_COMMON_DIR redirects the anchor the same way. GIT_CONFIG_KEY_n and
# its siblings are deliberately kept: a command-scoped core.bare arrives that
# way and this gate exists to report it.
_LOCATION_OVERRIDES = ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR")

# A `.git` marker file holds one short `gitdir:` line. Reading it unbounded lets
# a marker symlinked at a character device such as /dev/zero stream forever,
# which hangs the commit or push this gate runs inside.
_MAX_MARKER_BYTES = 8192


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
    # A `true` a later scope overrides. Reported so a usable verdict on a
    # repository whose config does contain `true` says which value was masked,
    # rather than the flat "none set true" that would read as a wrong summary.
    masked_scopes: tuple[tuple[str, str], ...] = ()


def _git(repo_root: Path, *args: str, missing_ok: bool = False) -> str | None:
    """Return stdout, preserving each failure mode as its own exception."""
    git = shutil.which("git")
    if git is None:
        raise GitExecutionError("git executable not found")
    env = os.environ.copy()
    env["LC_ALL"] = "C"
    for name in _LOCATION_OVERRIDES:
        env.pop(name, None)
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


def _scoped_core_bare(repo_root: Path) -> tuple[tuple[str, str], ...]:
    """Return every ``(scope, value)`` pair git holds for ``core.bare``.

    ``--type=bool`` makes git do the parsing, so each value arrives already
    normalized to ``true`` or ``false``. Reimplementing that reading here is
    what a membership test over a fixed list of spellings got wrong in both
    directions, measured on git 2.43.0: ``git_parse_maybe_bool`` falls through
    to integer parsing, so every nonzero integer is true and a repository whose
    ``git status`` already fatals on ``bare = 2`` passed the gate, while a
    healthy ``bare = `` (explicitly empty, which git reads as false) blocked
    every commit and push. The flag also separates the two spellings the untyped
    listing renders identically, since ``--get-all`` prints an empty field for
    both a valueless variable (``bare``, true) and an empty one (``bare = ``,
    false). Unset still exits 1 and an unparseable value still exits 128 with
    ``bad boolean config value``, leaving ``missing_ok`` and
    ``UnreadableCoreBareError`` untouched.
    """
    read = ("config", "--show-scope", "--type=bool", "--get-all", "core.bare")
    raw = _git(repo_root, *read, missing_ok=True)
    if not raw:
        return ()
    pairs = []
    for line in raw.splitlines():
        scope, separator, value = line.partition("\t")
        if separator:
            pairs.append((scope, value))
    return tuple(pairs)


def _marker_git_dir(marker: Path) -> Path | None:
    """Resolve the git directory a ``.git`` file points at, or None.

    Only a regular file of plausible size is read. ``is_file`` follows the
    symlink, so a ``.git`` symlinked at ``/dev/zero`` is rejected as a character
    device rather than read until the gate is killed, and an oversized regular
    file is refused before any of it reaches memory.
    """
    try:
        if not marker.is_file() or marker.stat().st_size > _MAX_MARKER_BYTES:
            return None
        with marker.open(encoding="utf-8", errors="replace") as handle:
            text = handle.read(_MAX_MARKER_BYTES)
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


def _work_tree_root(start: Path, common_dir: Path) -> Path | None:
    """Return the checkout whose ``.git`` marker names ``common_dir``, or None.

    Ancestors are walked so an invocation from a subdirectory still finds the
    checkout. Two comparisons matter and both are against the *common* git
    directory, never against this checkout's own ``--absolute-git-dir``:

    * a linked worktree's marker names its private git directory under
      ``<common>/worktrees/<name>``, so it does not match, which is what stops a
      healthy linked worktree of a genuinely bare repository being read as
      evidence that a main work tree exists.
    * a bare repository sitting inside an unrelated checkout does not match that
      checkout's marker either, so it is not attributed to it.

    A ``git init --separate-git-dir`` checkout does match, because its
    ``gitdir:`` file names the common directory itself. That case needs the
    walk: once ``core.bare`` is true, ``git worktree list`` names the git
    directory as the main worktree and never mentions the real checkout.
    """
    for candidate in (start, *start.parents):
        marker = candidate / ".git"
        if not marker.exists():
            continue
        target = marker.resolve() if marker.is_dir() else _marker_git_dir(marker)
        if target == common_dir:
            return candidate
    return None


def _common_git_dir(repo_root: Path) -> Path:
    """Return the repository's shared git directory, absolute.

    ``--path-format=absolute`` because the bare answer is relative to the
    working directory (``.git`` from a checkout's top level, ``.`` inside a bare
    repository), and lefthook already requires that flag of the git it runs.
    """
    raw = _git(repo_root, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if not raw:
        raise GitExecutionError("git returned an empty git directory")
    return Path(raw).resolve()


def _reported_main_worktree(repo_root: Path) -> Path | None:
    """Return the path on the first ``worktree`` line of the porcelain listing.

    That first entry is the main worktree. Later entries are linked worktrees,
    whose own health this gate does not decide.
    """
    raw = _git(repo_root, "worktree", "list", "--porcelain")
    for line in (raw or "").splitlines():
        before, separator, path = line.partition("worktree ")
        if separator and not before and path:
            return Path(path).resolve()
    return None


def _holds_checked_out_content(work_tree: Path) -> bool:
    """Report whether a directory holds anything besides its own ``.git`` entry.

    Measured on git 2.43.0: ``git clone --bare seed dirD/.git`` leaves ``dirD``
    holding ``.git`` and nothing else while git names ``dirD`` as the main
    worktree, which is indistinguishable by path from a poisoned checkout whose
    git directory sits at the same place. A checkout holds its tracked files.
    """
    try:
        with os.scandir(work_tree) as entries:
            return any(entry.name != ".git" for entry in entries)
    except OSError:
        return False


def _has_main_work_tree_index(common_dir: Path) -> bool:
    """Report whether git holds a staged index for this repository's main work tree.

    Repository metadata, which a directory listing is not. Measured on git
    2.43.0: ``git init --bare`` and ``git clone --bare`` create no ``index``
    entry, every checkout gains one from its first ``git add``, and a linked
    worktree keeps its own under ``<common>/worktrees/<name>/index``, so a bare
    repository that has handed out worktrees still has none of its own. The
    module docstring carries the full measurement table.

    Answering ``False`` for an unreadable path keeps ambiguity resolving toward
    "bare by design", which is the direction the module docstring justifies.
    """
    try:
        return (common_dir / "index").is_file()
    except OSError:
        return False


def _main_work_tree(repo_root: Path, common_dir: Path) -> Path | None:
    """Return the main work tree this repository is meant to have, or None.

    None is the "bare by design" verdict, and it is where every ambiguity
    lands: see the module docstring for why a false alarm costs more than a
    miss here. A candidate has to clear both the metadata condition and the
    content condition, because either alone admits a healthy layout: a file
    sitting beside a bare repository's ``.git`` passes the content read, and a
    bare repository someone ran ``git read-tree`` inside passes the metadata
    read.
    """
    candidate = _work_tree_root(repo_root, common_dir) or _reported_main_worktree(repo_root)
    if candidate is None or candidate.resolve() == common_dir:
        return None
    if not _has_main_work_tree_index(common_dir):
        return None
    return candidate if _holds_checked_out_content(candidate) else None


def _worktree_config_enabled(repo_root: Path) -> bool:
    """Report whether ``extensions.worktreeConfig`` permits a worktree-scoped fix."""
    value = _git(
        repo_root,
        "config",
        "--type=bool",
        "--get",
        "extensions.worktreeConfig",
        missing_ok=True,
    )
    return value == "true"


def _effective_pair(
    scoped: tuple[tuple[str, str], ...], *, ignore_worktree: bool = False
) -> tuple[str, str] | None:
    """Return the ``(scope, value)`` pair git resolves as effective, or None.

    ``core.bare`` is single-valued, so git answers it with one value however
    many scopes carry it: the last one wins. ``--show-scope --get-all`` emits
    values in git's own precedence order, system through command, and
    ``git config --get`` returns the final line. Measured on git 2.43.0, where
    the ``--get`` column is the fact this function reproduces::

        get-all                             --get    --is-bare-repository
        global true, local false            false    false
        local true, local false             false    false
        local false, local true             true     true
        local true, worktree false          false    false
        local true, worktree false,
          command false                     false    -

    ``ignore_worktree`` answers the second question this gate needs: what a
    sibling worktree carrying no override of its own sees. That is why the gate
    cannot simply read ``--is-bare-repository``; see the module docstring.
    """
    considered = [pair for pair in scoped if not (ignore_worktree and pair[0] == "worktree")]
    return considered[-1] if considered else None


def _active_bare_scopes(scoped: tuple[tuple[str, str], ...]) -> tuple[tuple[str, str], ...]:
    """Return the true-carrying scopes, but only when one of them is in force.

    A ``true`` git has already overridden is not a defect. ``global true`` under
    a ``local false``, or a stale ``local true`` followed by ``local false``,
    leaves every worktree of the repository usable, so reporting it would print
    a repair for a condition nobody has. Presence of the token is therefore not
    the test; the effective value is.

    Two effective values matter, because neither alone covers the incident:

    * this vantage point's own value, so a worktree-scoped ``true`` is caught.
    * the shared value a sibling without an override sees. The state issue
      #4698 left behind is ``local true`` plus the worktree-scoped ``false``
      GOTCHAS prescribes, where this checkout resolves usable while its
      siblings are dead.

    Every true-carrying scope is then reported, not only the governing one,
    because clearing the top scope can expose a lower one and the reader is
    better served seeing both repairs at once.
    """
    here = _effective_pair(scoped)
    shared = _effective_pair(scoped, ignore_worktree=True)
    in_force = (here is not None and here[1] == "true") or (
        shared is not None and shared[1] == "true"
    )
    if not in_force:
        return ()
    return tuple((scope, value) for scope, value in scoped if value == "true")


def diagnose(repo_root: Path) -> RepoHealth:
    """Classify the repository. Raises the typed errors above on failure."""
    scoped = _scoped_core_bare(repo_root)
    bare_scopes = _active_bare_scopes(scoped)
    if not bare_scopes:
        return RepoHealth(
            "usable",
            scopes_read=len(scoped),
            masked_scopes=tuple(pair for pair in scoped if pair[1] == "true"),
        )

    work_tree = _main_work_tree(repo_root, _common_git_dir(repo_root))
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
    scopes = ", ".join(f"{scope}={value}" for scope, value in health.bare_scopes)
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
        masked = ", ".join(f"{scope}={value}" for scope, value in health.masked_scopes)
        detail = f"{masked} overridden by a later scope" if masked else "none set true"
        print(
            f"repo health: core.bare read in {health.scopes_read} config scope(s), "
            f"{detail}, for {repo_root}"
        )
        return 0
    if health.status == "bare_by_design":
        print(
            f"repo health: skipped, {repo_root} belongs to a bare repository "
            f"with no work tree ({len(health.bare_scopes)} of "
            f"{health.scopes_read} read scope(s) bare by design)"
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
