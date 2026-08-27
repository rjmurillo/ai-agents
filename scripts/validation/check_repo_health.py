#!/usr/bin/env python3
r"""Gate: no config scope flags a repository bare while it has a work tree.

Something during ``git push`` writes ``core.bare = true`` into the shared
``.git/config``. A bare repository cannot have a work tree, so every git
command needing one fails with ``fatal: this operation must be run in a work
tree``. Issue #4698 measured it twice in one session: it broke the main
checkout and three of five linked worktrees at once and surfaced as four
unrelated-looking failures, and three wrong diagnoses were attempted before the
shared cause was found. ``.agents/governance/GOTCHAS.md`` records the incident
and the repair, quoted verbatim from its "Repair" and "Immunize" lines::

    git config core.bare false

    git config --worktree core.bare false          # in the main checkout
    git -C <each linked worktree> config --worktree core.bare false

Three questions decide the verdict, and each has a counterintuitive answer.

**Which value counts.** Not ``--is-bare-repository``. In the state that answer
reports bare, nothing local can report anything: measured on lefthook 2.1.10,
lefthook runs ``git rev-parse --path-format=absolute --show-toplevel`` before
its first job and exits 128 on the same fatal text, and ``git commit`` refuses
even earlier. The state a hook CAN speak from is the mixed one GOTCHAS
prescribes, where the shared config says true and this worktree carries a
worktree-scoped false; there the effective answer calls this checkout healthy
while its siblings are dead. So the gate reads ``--show-scope`` and asks
:func:`_effective_pair` twice, once for here and once for what a sibling
without an override sees. Presence of a ``true`` is not the test either, since
git overrides one scope with another: see :func:`_active_bare_scopes`.

**Whether a work tree is meant to exist.** A genuine bare repository answers
``local true`` as well, so bareness alone is not the defect. The question is
about the repository's *main* work tree, not about the checkout being read, and
conflating the two made an earlier version of this gate print destructive
advice: ``git clone --bare seed bareA.git`` then ``git -C bareA.git worktree
add wtA`` is ordinary git, ``wtA`` is a live checkout carrying a ``gitdir:``
marker, and running the ``git config core.bare false`` the gate printed writes
into the bare parent's shared config and breaks it and every sibling at once.
The anchor is therefore ``rev-parse --path-format=absolute --git-common-dir``,
which answers the same shared path from every worktree, corroborated by the
staged index. :func:`_main_work_tree` carries the measurements.

Ambiguity resolves toward "bare by design" on purpose. A miss returns the
reader to the pre-gate status quo; a false alarm hands them a command that
destroys a healthy repository, and only the second is irreversible.

**How long the gate may take.** Long enough to finish, and less than lefthook
allows, or the diagnosis is replaced by a timeout line. See
``GIT_BUDGET_SECONDS``.

Where it runs: first in the ``pre-commit`` and ``pre-push`` job lists, ahead of
``repair-packed-refs``, so one accurate message precedes every failure the
corruption would otherwise be blamed for. Run it by hand against a worktree git
already refuses; a hook cannot, for the lefthook reason above.

Stricter/looser/different than canonical: GOTCHAS names one repair, ``git
config core.bare false``. That command writes to the local config and cannot
clear a worktree-scoped, global, or system value, so this gate names a repair
per scope that carries the value. It adds the immunization line only when
``extensions.worktreeConfig`` is enabled: measured, ``git config --worktree``
otherwise exits 128 with ``--worktree cannot be used with multiple working
trees unless the config extension worktreeConfig is enabled``.

Exit codes (ADR-035):
    0 - Success (no scope flags this work tree bare, or none applies here)
    1 - Logic error (a config scope flags a repository that has a work tree)
    2 - Config error (invalid repository root)
    3 - External failure (git missing, timed out, budget exhausted, or failed)
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

# Flat import, not `scripts.validation.*`: lefthook and the docs invoke this by
# file path, so `sys.path[0]` is this directory and an absolute import fails.
# `tests/validation/test_validation_entry_point_imports.py` reproduces that.
from check_repo_health_report import (
    RepoHealth,
    report_bare_by_design,
    report_corruption,
    report_invalid_root,
    report_not_a_repository,
    report_unreadable,
    report_unverifiable,
    report_usable,
)

# A hung git must not stall a commit or a push. Local config and rev-parse
# reads answer in milliseconds, so this only trips on a genuine hang, and the
# gate then fails closed with exit 3 rather than reporting a verified pass.
GIT_TIMEOUT_SECONDS = 5

# One deadline for the whole evaluation, because the per-call watchdog does not
# bound the run: the corrupted path issues five sequential git calls, so it
# allows 25s against the 10s `timeout:` the `repo-health` job declares in
# `lefthook.yml`. Which cap fires decides what the reader gets. Measured on
# lefthook 2.1.10 (`.claude/rules/ci-scripts.md` MUST-19), a `timeout:` kill
# lands on the job's shell before any guard runs, replacing the repair guidance
# with a generic timeout line, which is the one failure this gate exists to
# prevent. So 7s here, plus `uv run` startup measured at 0.077s and 0.130s warm
# and 0.944s cold, leaves the 10s cap unreached. Exhausting the budget still
# blocks, with exit 3 naming the command that ran out.
# `tests/validation/test_check_repo_health_budget.py` pins the two together.
GIT_BUDGET_SECONDS = 7

# git refuses every command, including `git config --unset-all`, when core.bare
# holds a value it cannot parse as a boolean. Measured with core.bare=notabool:
# `git config --show-scope --get-all core.bare` exits 128 with this text.
_BAD_BOOLEAN_MARKER = "bad boolean config value"

# git resolves the repository's location from the environment before reading
# any config, so an inherited value makes every answer below describe a
# different repository. Measured on git 2.43.0 against a corrupted checkout with
# GIT_DIR naming an unrelated bare repository: `rev-parse --git-common-dir` and
# `worktree list --porcelain` both answered for that other repository, turning
# live corruption into a verified pass. GIT_COMMON_DIR redirects the anchor the
# same way. GIT_CONFIG_KEY_n and its siblings are deliberately kept: a
# command-scoped core.bare arrives that way and this gate reports it.
_LOCATION_OVERRIDES = ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR")

# A `.git` marker file holds one short `gitdir:` line. Reading it unbounded lets
# a marker symlinked at a character device such as /dev/zero stream forever,
# which hangs the commit or push this gate runs inside.
_MAX_MARKER_BYTES = 8192


@dataclass(slots=True)
class GitBudget:
    """The shared deadline every git call in one evaluation draws down.

    Threaded rather than read from module state, so two evaluations in one
    process do not share a clock.
    """

    total: float = field(default_factory=lambda: float(GIT_BUDGET_SECONDS))
    started: float = field(default_factory=time.monotonic)

    def remaining(self) -> float:
        """Seconds left before the gate must report rather than run more git."""
        return self.total - (time.monotonic() - self.started)


class GitExecutionError(RuntimeError):
    """Git was unavailable or failed before the gate could establish a fact."""


class NotGitRepositoryError(RuntimeError):
    """The target is explicitly outside a Git repository."""


class UnreadableCoreBareError(RuntimeError):
    """core.bare holds a value git refuses to parse, so no git command runs."""


def _git(
    repo_root: Path, budget: GitBudget, *args: str, missing_ok: bool = False
) -> str | None:
    """Return stdout, preserving each failure mode as its own exception.

    The per-call watchdog is clamped by what the shared budget has left, so slow
    successful calls report rather than being killed. See ``GIT_BUDGET_SECONDS``.
    """
    remaining = budget.remaining()
    if remaining <= 0:
        raise GitExecutionError(
            f"the {budget.total:.0f}s git budget ran out before `git "
            f"{' '.join(args)}`; see GIT_BUDGET_SECONDS in this script"
        )
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
            timeout=min(GIT_TIMEOUT_SECONDS, remaining),
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


def _scoped_core_bare(repo_root: Path, budget: GitBudget) -> tuple[tuple[str, str], ...]:
    """Return every ``(scope, value)`` pair git holds for ``core.bare``.

    ``--type=bool`` makes git parse, so values arrive normalized. Reimplementing
    that was wrong in both directions, measured on git 2.43.0:
    ``git_parse_maybe_bool`` falls through to integer parsing, so ``bare = 2`` is
    true to git and passed a spelling-list gate whose repository already fataled,
    while an explicitly empty ``bare = `` is false to git and blocked every
    commit. The flag also separates the two spellings ``--get-all`` prints
    identically, a valueless ``bare`` (true) and an empty one (false). Unset
    still exits 1 and an unparseable value still exits 128, leaving ``missing_ok``
    and ``UnreadableCoreBareError`` untouched.
    """
    read = ("config", "--show-scope", "--type=bool", "--get-all", "core.bare")
    raw = _git(repo_root, budget, *read, missing_ok=True)
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
    symlink, so a ``.git`` symlinked at ``/dev/zero`` is refused as a character
    device rather than streamed until the gate is killed.
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
    checkout. The comparison is against the *common* git directory, never this
    checkout's own ``--absolute-git-dir``, which is what keeps two healthy
    layouts out: a linked worktree's marker names a private directory under
    ``<common>/worktrees/<name>``, and a bare repository nested inside an
    unrelated checkout does not match that checkout's marker. A ``git init
    --separate-git-dir`` checkout does match, and needs this walk, because once
    ``core.bare`` is true ``git worktree list`` names the git directory as the
    main worktree and never mentions the real checkout.
    """
    for candidate in (start, *start.parents):
        marker = candidate / ".git"
        if not marker.exists():
            continue
        target = marker.resolve() if marker.is_dir() else _marker_git_dir(marker)
        if target == common_dir:
            return candidate
    return None


def _common_git_dir(repo_root: Path, budget: GitBudget) -> Path:
    """Return the repository's shared git directory, absolute.

    ``--path-format=absolute`` because the bare answer is relative to the
    working directory: ``.git`` from a checkout's top level, ``.`` inside a bare
    repository.
    """
    raw = _git(repo_root, budget, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if not raw:
        raise GitExecutionError("git returned an empty git directory")
    return Path(raw).resolve()


def _reported_main_worktree(repo_root: Path, budget: GitBudget) -> Path | None:
    """Return the path on the first ``worktree`` line of the porcelain listing.

    The first entry is the main worktree; later entries are linked worktrees,
    whose own health this gate does not decide.
    """
    raw = _git(repo_root, budget, "worktree", "list", "--porcelain")
    for line in (raw or "").splitlines():
        before, separator, path = line.partition("worktree ")
        if separator and not before and path:
            return Path(path).resolve()
    return None


def _holds_checked_out_content(work_tree: Path) -> bool:
    """Report whether a directory holds anything besides its own ``.git`` entry.

    Measured on git 2.43.0: ``git clone --bare seed dirD/.git`` leaves ``dirD``
    holding ``.git`` alone while git names ``dirD`` the main worktree, which by
    path is indistinguishable from a poisoned checkout. A checkout holds files.
    """
    try:
        with os.scandir(work_tree) as entries:
            return any(entry.name != ".git" for entry in entries)
    except OSError:
        return False


def _has_main_work_tree_index(common_dir: Path) -> bool:
    """Report whether git holds a staged index for the main work tree.

    Repository metadata, which a directory listing is not. Measured on git
    2.43.0::

        seed/.git/index                True   ordinary checkout
        corrupt/.git/index             True   checkout later flagged bare
        dirD/.git/index                False  git clone --bare seed dirD/.git
        holder/.git/index              False  the same, with an unrelated
                                              README sitting beside it
        bareA.git/index                False  bare repository that handed out
                                              a linked worktree
        bareA.git/worktrees/wtA/index  True   that worktree's own index

    An unreadable path answers ``False``, keeping ambiguity on the
    bare-by-design side the module docstring justifies.
    """
    try:
        return (common_dir / "index").is_file()
    except OSError:
        return False


def _main_work_tree(repo_root: Path, common_dir: Path, budget: GitBudget) -> Path | None:
    """Return the main work tree this repository is meant to have, or None.

    None is the "bare by design" verdict, where every ambiguity lands. A
    candidate clears both the metadata and the content condition, because either
    alone admits a healthy layout: an unrelated file beside a bare repository's
    ``.git`` passes the content read, and a bare repository someone ran ``git
    read-tree`` inside passes the metadata read.
    """
    candidate = _work_tree_root(repo_root, common_dir) or _reported_main_worktree(
        repo_root, budget
    )
    if candidate is None or candidate.resolve() == common_dir:
        return None
    if not _has_main_work_tree_index(common_dir):
        return None
    return candidate if _holds_checked_out_content(candidate) else None


def _worktree_config_enabled(repo_root: Path, budget: GitBudget) -> bool:
    """Report whether ``extensions.worktreeConfig`` permits a worktree-scoped fix."""
    value = _git(
        repo_root,
        budget,
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

    ``core.bare`` is single-valued: however many scopes carry it, the last one
    wins. ``--show-scope --get-all`` emits in git's precedence order, system
    through command, and ``git config --get`` returns the final line. Measured
    on git 2.43.0, where ``--get`` is the column this reproduces::

        get-all                       --get   --is-bare-repository
        global true, local false      false   false
        local true, local false       false   false
        local false, local true       true    true
        local true, worktree false    false   false

    ``ignore_worktree`` answers the gate's second question: what a sibling
    worktree carrying no override of its own sees.
    """
    considered = [pair for pair in scoped if not (ignore_worktree and pair[0] == "worktree")]
    return considered[-1] if considered else None


def _active_bare_scopes(scoped: tuple[tuple[str, str], ...]) -> tuple[tuple[str, str], ...]:
    """Return the true-carrying scopes, but only when one of them is in force.

    A ``true`` git has already overridden is not a defect. ``global true`` under
    a ``local false``, or a stale ``local true`` followed by ``local false``,
    leaves every worktree usable, so reporting it prints a repair for a condition
    nobody has. Presence is not the test; the effective value is.

    Two effective values matter, because neither alone covers the incident: this
    vantage point's own, so a worktree-scoped ``true`` is caught, and the shared
    value a sibling without an override sees, which is the state issue #4698 left
    behind. Every true-carrying scope is then reported, not only the governing
    one, because clearing the top scope can expose a lower one.
    """
    here = _effective_pair(scoped)
    shared = _effective_pair(scoped, ignore_worktree=True)
    in_force = (here is not None and here[1] == "true") or (
        shared is not None and shared[1] == "true"
    )
    if not in_force:
        return ()
    return tuple((scope, value) for scope, value in scoped if value == "true")


def diagnose(repo_root: Path, budget: GitBudget | None = None) -> RepoHealth:
    """Classify the repository, on a fresh budget unless one is supplied."""
    budget = budget or GitBudget()
    scoped = _scoped_core_bare(repo_root, budget)
    bare_scopes = _active_bare_scopes(scoped)
    if not bare_scopes:
        return RepoHealth(
            "usable",
            scopes_read=len(scoped),
            masked_scopes=tuple(pair for pair in scoped if pair[1] == "true"),
        )

    work_tree = _main_work_tree(repo_root, _common_git_dir(repo_root, budget), budget)
    if work_tree is None:
        return RepoHealth("bare_by_design", bare_scopes=bare_scopes, scopes_read=len(scoped))

    return RepoHealth(
        "corrupted",
        work_tree=work_tree,
        bare_scopes=bare_scopes,
        scopes_read=len(scoped),
        effective_bare=_git(repo_root, budget, "rev-parse", "--is-bare-repository") == "true",
        worktree_config=_worktree_config_enabled(repo_root, budget),
    )


def _evaluate(repo_root: Path) -> int:
    """Evaluate once and return the ADR-035 exit code."""
    try:
        health = diagnose(repo_root)
    except NotGitRepositoryError:
        report_not_a_repository(repo_root)
        return 0
    except UnreadableCoreBareError as exc:
        report_unreadable(repo_root, str(exc))
        return 1
    except GitExecutionError as exc:
        report_unverifiable(str(exc))
        return 3

    if health.status == "usable":
        report_usable(repo_root, health)
        return 0
    if health.status == "bare_by_design":
        report_bare_by_design(repo_root, health)
        return 0

    report_corruption(health)
    return 1


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns an ADR-035 exit code."""
    args = argv if argv is not None else sys.argv[1:]
    repo_root = Path(args[0]).resolve() if args else Path(__file__).resolve().parents[2]
    if not repo_root.is_dir():
        report_invalid_root(repo_root)
        return 2
    return _evaluate(repo_root)


if __name__ == "__main__":
    raise SystemExit(main())
