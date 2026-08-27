"""Shared machinery for whole-repo violation-count ratchets.

A count ratchet freezes a repository-wide violation ceiling in a baseline file.
The measured count must not exceed the baseline. An improvement (count <
baseline) passes without rewriting the baseline, which keeps concurrent cleanup
PRs from conflicting on a shared line. ``--update`` explicitly lowers the
baseline when a maintainer chooses to close slack. A regression (count >
baseline) blocks.

Two gates use this: ``ruff_count_ratchet.py`` (issue #2993) and
``taste_count_ratchet.py`` (issue #3779). Only the counting differs. Everything
else, which is where the actual policy lives, is identical between them: the
baseline may only fall, a regression blocks, ``--update`` lowers, and
``--base-ref`` catches a PR that widens the allowance instead of fixing code.
Holding that policy in one place is the point. When the semantics change they
must change for every gate at once, and two copies would drift.

Scope is git-TRACKED files, never a directory walk. ``os.walk`` also visits
untracked scratch, nested worktrees, and vendored caches that a contributor
happens to have on disk, which inflated a local ruff run to 767 against a real
tracked count of 361 and made that gate report a phantom regression outside CI.
Tracked files are the only thing a PR can change, so they are the only thing a
baseline should freeze.

The baseline is a committed absolute number, so two branches can each remove one
violation and write the same lowered value. Git merges the identical one-line
edits without a conflict, and the merged tree is then improved twice against a
baseline that fell once, which reads as STALE on the default branch (issue
#4057). Nothing in this module can see the other branch, so the failure text
offers that as the usual cause and the fix stays a baseline-only commit.
Blocking the second merge is a branch-policy gate, not a code change here: the
enforcement point chosen for issue #4057, and the alternatives rejected, are
recorded in ``.github/AGENTS.md`` under "Ratchet Baselines and the Concurrent
Merge Race". The regression test that proves the gate blocks lives in
``tests/ci/test_count_ratchet_concurrent_merge.py``.

Every git subprocess here runs under ``git_environment()``, never the ambient
environment. A ``git push`` from a linked worktree exports ``GIT_DIR`` into the
pre-push hook, and an exported ``GIT_DIR`` outranks the ``-C <root>`` argument,
so the counters read the pushing worktree instead of the root they were handed
(issue #4914). See that helper for the measurement.

Stdlib only: these gates run by path in CI (``python scripts/ci/<name>.py``) and
must not depend on the project's import graph. That is why the ``GIT_*`` strip
below is a local copy of the rule in ``merge_tree_materialization.py`` rather
than an import of it: that module imports ``scripts.cli_exec``, and reaching it
from here would put the project's import graph behind every ratchet.

Exit codes (AGENTS.md contract):
    0 - ok (count <= baseline, or --update records a decrease)
    1 - regression (count > baseline, or this branch moved the baseline above
        the one at --base-ref; a branch merely behind the base ref is reported
        and not blocked, but only for a ratchet whose caller declares
        ``merge_tree_backed=True``, issue #5065)
    2 - config error (baseline missing or malformed, bad args)
    3 - external error (the underlying linter could not run)
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

EXIT_OK = 0
EXIT_REGRESSION = 1
EXIT_CONFIG = 2
EXIT_EXTERNAL = 3

# Windows CreateProcess caps a command line at 32767 characters; POSIX raises
# E2BIG well above that. Batching at 24000 bytes keeps a single scan below both
# without needing a platform check.
ARGV_BUDGET_BYTES = 24000


def git_environment() -> dict[str, str]:
    """The ambient environment with every ``GIT_*`` variable removed.

    ``git -C <root>`` does not win against an exported ``GIT_DIR``. Measured on
    git 2.43.0 against a scratch repo holding only ``keep.py``, with ``GIT_DIR``
    pointed at a linked worktree that also tracks
    ``scripts/validation/only_on_branch.py``::

        $ git -C <scratch> ls-files                        # clean environment
        keep.py
        $ GIT_DIR=<worktree gitdir> git -C <scratch> ls-files
        keep.py
        scripts/validation/only_on_branch.py               # the WRONG tree

    That second listing is issue #4914. ``git push`` exports ``GIT_DIR`` into
    the pre-push hook from a linked worktree and not from an ordinary checkout
    (measured on git 2.43.0: ``GIT_DIR=<main>/.git/worktrees/<name>`` present in
    the hook environment for the linked push, absent for the main-checkout
    push). ``merge_tree_ratchet_check`` then calls ``current_count(<scratch>)``,
    ``tracked_files`` lists the pushing worktree's index instead of the scratch
    index, and the linter is handed scratch paths that do not exist. The
    counter returns None and the push is blocked with a message that names a
    file the branch legitimately carries. Five pushes on PR #4912 were spent
    before the cause was found.

    Mirrors the ``GIT_*`` half of
    ``scripts/ci/merge_tree_materialization.py::isolated_git_environment``,
    whose rule is verbatim::

        env = os.environ.copy()
        isolated_names = {"GNUPGHOME", "HOME", "LEFTHOOK", "USERPROFILE", "XDG_CONFIG_HOME"}
        for name in tuple(env):
            normalized = name.upper()
            if normalized.startswith("GIT_") or normalized in isolated_names:
                env.pop(name)

    ``normalized = name.upper()`` is kept, so a lowercased ``git_dir`` that a
    case-insensitive platform folds into ``GIT_DIR`` is stripped here too.

    Stricter/looser/different than canonical: narrower on purpose. That helper
    also drops ``HOME``, ``USERPROFILE``, ``XDG_CONFIG_HOME``, ``GNUPGHOME`` and
    ``LEFTHOOK``, and repoints them at a scratch home with an empty global
    config. It may, because it only ever runs git against a repository it just
    created and owns. These ratchets run git against the real checkout, where
    the global config is load-bearing: ``actions/checkout`` records
    ``safe.directory`` there, and blanking it invites "detected dubious
    ownership" on a runner. Measured with that helper's own environment, a
    global ``safe.directory`` entry that ``git config --get-all`` returns under
    the ambient environment (rc 0) is invisible under the isolated one (rc 1).
    So this strips the variable that causes the defect and nothing else. It also
    takes no scratch directory and needs no cleanup, which keeps a read-only
    path free of the temporary-tree failure modes that isolation carries.

    Returns a fresh dict; ``os.environ`` is never mutated.
    """
    return {
        name: value
        for name, value in os.environ.items()
        if not name.upper().startswith("GIT_")
    }


def _git_run(repo_root: Path, argv: Sequence[str]) -> subprocess.CompletedProcess[str] | None:
    """Run a git command, or None when git could not be launched."""
    try:
        return subprocess.run(
            ["git", "-C", str(repo_root), *argv],
            capture_output=True,
            text=True,
            errors="replace",
            encoding="utf-8",
            check=False,
            env=git_environment(),
        )
    except (FileNotFoundError, OSError) as exc:
        sys.stderr.write(f"git could not be launched: {exc}\n")
        return None


def _git_rc(repo_root: Path, argv: Sequence[str]) -> int | None:
    """Exit status of a git command, or None when git could not be launched."""
    proc = _git_run(repo_root, argv)
    return None if proc is None else proc.returncode


def tracked_files(repo_root: Path, globs: Sequence[str]) -> list[str] | None:
    """Git-tracked paths matching ``globs``, or None when git could not run."""
    proc = _git_run(repo_root, ["ls-files", "-z", "--", *globs])
    if proc is None:
        return None
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr)
        return None
    return [path for path in proc.stdout.split("\0") if path]


def _diff_paths(repo_root: Path, spec: str, scope: str) -> frozenset[str]:
    """Paths named by one ``git diff`` form, or empty with the cause on stderr.

    ``scope`` names what could not be resolved, so the two probes in
    ``changed_files`` stay distinguishable on stderr when only one fails. Empty
    on failure: this orders a diagnostic and must never block a push.
    """
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_root), "diff", "--name-only", "-z", spec],
            capture_output=True,
            text=True,
            errors="replace",
            encoding="utf-8",
            check=False,
            env=git_environment(),
        )
    except (FileNotFoundError, OSError) as exc:
        sys.stderr.write(f"diagnostic ordering degraded: git could not be launched: {exc}\n")
        return frozenset()
    if proc.returncode != 0:
        sys.stderr.write(f"diagnostic ordering degraded: git could not resolve {scope}\n")
        sys.stderr.write(proc.stderr)
        return frozenset()
    return frozenset(path for path in proc.stdout.split("\0") if path)


def changed_files(repo_root: Path, base_ref: str | None) -> frozenset[str]:
    """Repo-relative paths this checkout changed, or empty when unknown.

    Used only to order the regression diagnostic, never to change a count. A
    whole-repo ratchet trips on a total, so the printed list is dominated by
    historical violations the branch never touched: on issue #3902's own PR the
    single added violation sat at index 596 of 601 and the 40-line cap hid it.
    Showing branch-touched files first puts the actionable line on screen.

    Two probes, unioned, because the priority set has to cover the same surface
    the scan reads. ``tracked_files`` lists the index and the linter then reads
    each path off disk, so a staged or unstaged edit is counted like any other
    content. ``base_ref...HEAD`` names committed work only, so a violation
    introduced by a dirty file was counted, tripped the ratchet, and then
    sorted in with the historical bulk it was supposed to lead: the exact
    burying this ordering exists to prevent, and its likeliest local shape,
    since the pre-push hook scans whatever is on disk. ``git diff HEAD`` closes
    that. It names staged and unstaged edits to tracked files, including a
    staged addition, and omits untracked paths, which ``git ls-files`` never
    offers the linter anyway.

    Three-dot on the committed leg so a branch behind ``base_ref`` is compared
    against the merge base and does not inherit every file the base changed
    meanwhile, which would degenerate the priority set to "everything".

    Empty on any failure, which degrades to the previous emission order rather
    than blocking. The legs fail independently, so one unusable probe still
    leaves the other probe's paths prioritised. A failure writes the cause to
    stderr, matching ``tracked_files`` above; an unordered list is
    indistinguishable from an untouched tree otherwise.

    An absent ``base_ref`` is the documented no-op, not a failure, and stays
    quiet, the working-tree probe included. A caller that omits ``--base-ref``
    asked for no ordering at all, and probing anyway would print a degradation
    note on every run outside a repository.
    """
    if not base_ref:
        return frozenset()
    committed = _diff_paths(repo_root, f"{base_ref}...HEAD", base_ref)
    uncommitted = _diff_paths(repo_root, "HEAD", "HEAD")
    return committed | uncommitted


def chunk(paths: Sequence[str], budget: int = ARGV_BUDGET_BYTES) -> list[list[str]]:
    """Split ``paths`` into batches sized in UTF-8 bytes.

    A batch holding more than one path stays under ``budget``. A single path
    that exceeds the budget on its own gets a batch to itself and is still
    scanned, because dropping it would silently shrink the count.
    """
    batches: list[list[str]] = []
    current: list[str] = []
    size = 0
    for path in paths:
        cost = len(path.encode("utf-8")) + 1
        if current and size + cost > budget:
            batches.append(current)
            current = []
            size = 0
        current.append(path)
        size += cost
    if current:
        batches.append(current)
    return batches


def read_baseline(path: Path) -> int | None:
    """Baseline integer, or None when the file is missing or not an integer."""
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


MAX_BASELINE_SLACK = 6
"""How far a baseline may sit above the tree before it must be trued up.

Zero is wrong here, and that is not a style preference. Issue #4057 recorded
the concurrent-lowering race: two branches each remove one violation and each
write the same lowered baseline, git merges the identical one-line edits
without a conflict, and the merged tree has improved twice while the file fell
once. PR #4214 accepted slack as the resolution, so that "concurrent cleanup
PRs never conflict on the shared line and the default branch does not go red on
a change none of them made" (``test_count_ratchet_concurrent_merge``).

Demanding equality re-opens that outage at the test layer: every collision
reddens the default branch for every contributor until a human notices and
edits the scalar. The gap is bounded instead, so the accepted slack cannot
grow into unbounded dead allowance. Six covers a seven-PR merge queue group
where each branch removes one violation and all seven write the same lowered
baseline: the merged tree has improved seven times while the scalar fell once,
leaving six slack. Any pull request may close the gap by writing the measured
count.
"""


def baseline_health(actual: int, baseline: int, max_slack: int = MAX_BASELINE_SLACK) -> str | None:
    """Why ``baseline`` fails to describe a tree measuring ``actual``, or None.

    Two distinct failures, because they need opposite fixes. A baseline below
    the tree means the branch regressed and the violations must go. A baseline
    too far above it means real improvements were never recorded, and the
    scalar must be trued up before the gap absorbs a future regression.
    """
    if actual > baseline:
        return (
            f"baseline is {baseline} but the tree measures {actual}: "
            f"{actual - baseline} violation(s) were added. Remove them rather "
            f"than raising the baseline."
        )
    slack = baseline - actual
    if slack > max_slack:
        return (
            f"baseline is {baseline} but the tree measures {actual}, a gap of "
            f"{slack} above the permitted {max_slack}. Improvements went "
            f"unrecorded; write {actual} into the baseline file."
        )
    return None


def _baseline_rel(repo_root: Path, baseline: Path) -> str:
    """Repo-relative POSIX path of ``baseline``, for addressing it inside a ref."""
    try:
        return baseline.resolve().relative_to(repo_root).as_posix()
    except ValueError:
        return baseline.as_posix()


def baseline_absent_at_ref(repo_root: Path, ref: str, baseline: Path) -> bool:
    """True when ``ref`` resolves but records no baseline file yet.

    This is the bootstrap case. The PR that introduces a ratchet is also the PR
    that adds its baseline file, so the base branch has none and there is no
    earlier value that could be raised. Comparing against a ref that predates
    the gate is not an error, it is the first run.

    Every other read failure stays external. The check is an allowlist -- the
    ref must resolve AND the path must be the only thing missing -- because a
    gate that reads any git error as "nothing to compare against" would fail
    open on a typo'd ref or a missing git binary, which is the one outcome a
    ratchet must never produce.

    The lookup reads ``ls-tree`` because it is the only form measured here that
    keeps that promise. On git 2.43.0, ``git cat-file -e`` and
    ``git rev-parse --verify`` both answer 128 for a path that is merely
    absent and for a path expression git refuses outright, and adding
    ``--quiet`` to ``rev-parse`` collapses both to 1 instead. Either way the
    two cases are indistinguishable, so a baseline path that escapes the
    worktree would read as "first run" and skip the raise check. ``ls-tree``
    exits 0 with empty output for an absent path and non-zero for a path it
    will not look up, which is the split this function needs.
    """
    if _git_rc(repo_root, ["rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"]) != 0:
        return False
    rel = _baseline_rel(repo_root, baseline)
    proc = _git_run(repo_root, ["ls-tree", ref, "--", rel])
    if proc is None or proc.returncode != 0:
        return False
    return proc.stdout.strip() == ""


def baseline_at_ref(repo_root: Path, ref: str, baseline: Path) -> int | None:
    """Baseline value recorded at ``ref``, or None when it cannot be read."""
    rel = _baseline_rel(repo_root, baseline)
    proc = _git_run(repo_root, ["show", f"{ref}:{rel}"])
    if proc is None:
        return None
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr)
        return None
    try:
        return int(proc.stdout.strip())
    except ValueError:
        return None


def build_parser(description: str, default_baseline: Path) -> argparse.ArgumentParser:
    """Argument parser shared by every count ratchet."""
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path.cwd(),
        help="Repository root (default: current working directory).",
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        default=default_baseline,
        help="Baseline count file (default: alongside this script).",
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="Lower the baseline to the current count when the count improved.",
    )
    parser.add_argument(
        "--base-ref",
        help=(
            "Git ref to compare the baseline against. Fails when the working "
            "baseline is higher than the one at this ref, which is what keeps "
            "the ratchet one-directional."
        ),
    )
    return parser


@dataclass(frozen=True, slots=True)
class _BaseRefFacts:
    """The four numbers and two names every ``--base-ref`` message reports.

    Bundled because five message builders take the same set, and a five-argument
    signature repeated five times drifts one argument at a time.
    """

    base_ref: str
    label: str
    baseline: int
    base: int
    count: int

    @property
    def excess(self) -> int:
        """How far the recorded baseline sits above the one at the base ref."""
        return self.baseline - self.base


def _above_base_message(facts: _BaseRefFacts) -> str:
    """Report a baseline this branch itself raised above the base ref.

    Reached only when ``baseline_move`` reports ``BASELINE_RAISED``, so the
    raise is measured rather than guessed. Both remedies stay in the text
    because both can apply at once: a branch that raised its own baseline can
    also be behind a base ref that lowered one, and merging is what makes the
    restore value meaningful. What issue #4066 forbids is naming a cause the
    code did not measure, not offering a second remedy the reader may need.

    The count is worth stating on its own: when it is one the base ref already
    allows, nothing in this tree added a violation, and that much IS measured.
    """
    measured = f"The measured count is {facts.count}. "
    if facts.count <= facts.base:
        measured = (
            f"The measured count is {facts.count}, which {facts.base_ref} "
            f"already allows, so nothing in this tree added a violation. "
        )
    return (
        f"{facts.label}: BASELINE ABOVE BASE. This tree records "
        f"{facts.baseline}, {facts.base_ref} records {facts.base} "
        f"(+{facts.excess}). {measured}"
        f"The baseline may only fall. If this branch did not edit the "
        f"baseline, it is behind {facts.base_ref}: merge or rebase to pick up "
        f"the lowered value. If it did raise the baseline, restore "
        f"{facts.base} and fix the violations instead of widening the "
        f"allowance."
    )


def _fork_point(repo_root: Path, base_ref: str) -> str | None:
    """Commit where this branch left ``base_ref``, or None when git cannot say."""
    proc = _git_run(repo_root, ["merge-base", "--", base_ref, "HEAD"])
    if proc is None or proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


def is_shallow_repository(repo_root: Path) -> bool:
    """True when ``repo_root`` is a shallow clone, per git's own answer.

    ``git rev-parse --is-shallow-repository`` prints ``true`` or ``false`` and
    exits 0 in a repository. Only used to pick which remedy an unreadable fork
    point prints, so an unlaunchable git degrades to the unrelated-history
    wording rather than raising: the verdict is already decided by then.
    """
    proc = _git_run(repo_root, ["rev-parse", "--is-shallow-repository"])
    if proc is None or proc.returncode != 0:
        return False
    return proc.stdout.strip() == "true"


BASELINE_RAISED = "raised"
BASELINE_LOWERED = "lowered"
BASELINE_UNCHANGED = "unchanged"


@dataclass(frozen=True, slots=True)
class BaselineMove:
    """Which way this checkout moved the baseline, and from what value."""

    direction: str
    at_fork: int


def baseline_move(
    repo_root: Path, base_ref: str, baseline: Path, recorded: int
) -> BaselineMove | None:
    """How this checkout moved the baseline number, or None when git cannot say.

    ``recorded`` comes from ``read_baseline`` on the working tree, so a staged
    or unstaged edit counts exactly like a committed one: the pre-push hook
    scans whatever is on disk.

    Direction matters, not merely difference. An earlier version returned a
    bare ``recorded != at_fork``, which collapsed two opposite histories: a
    branch that widened the allowance, and a cleanup branch that lowered the
    baseline while the base ref lowered it further. The second was then told to
    "restore" the base value, a number it never recorded, and to stop widening
    an allowance it had just narrowed. That is the same
    accusation-without-measurement defect issue #4066 was filed for, one level
    down: the fork point was in hand and the direction was thrown away.

    Failure is None rather than a direction so the caller fails closed. A gate
    that read an unlaunchable git as "this branch changed nothing" would wave
    through the widened allowance it exists to catch.
    """
    fork = _fork_point(repo_root, base_ref)
    if fork is None:
        return None
    at_fork = baseline_at_ref(repo_root, fork, baseline)
    if at_fork is None:
        return None
    if recorded > at_fork:
        return BaselineMove(BASELINE_RAISED, at_fork)
    if recorded < at_fork:
        return BaselineMove(BASELINE_LOWERED, at_fork)
    return BaselineMove(BASELINE_UNCHANGED, at_fork)


def _lowered_here_message(facts: _BaseRefFacts, *, at_fork: int) -> str:
    """Report a branch that lowered the baseline while the base ref went lower.

    Blocks, deliberately. The recorded value is still above the base ref's, so
    passing it would install a ceiling the base branch has already fallen
    below. The one-line baseline file conflicts on merge anyway, so blocking
    here costs the author nothing beyond the merge they already owe, and it
    keeps the recorded scalar one-directional against the base.

    Names all three numbers it measured. It never says "restore", because this
    branch lowered the value: there is nothing to undo, only a merge to take.
    """
    return (
        f"{facts.label}: BASELINE LOWERED BEHIND BASE. The fork point records "
        f"{at_fork}, this tree records {facts.baseline}, and {facts.base_ref} "
        f"records {facts.base}. This branch lowered {at_fork} to "
        f"{facts.baseline} while {facts.base_ref} lowered it further to "
        f"{facts.base}, so the recorded value still sits {facts.excess} above "
        f"the base. The measured count is {facts.count}. Merge or rebase from "
        f"{facts.base_ref} and re-run with --update so the recorded value is "
        f"measured against the current tree."
    )


def _unreadable_fork_message(facts: _BaseRefFacts, *, shallow: bool) -> str:
    """Report that git could not name a fork point, and block.

    Its own state, never ``_above_base_message``. That message offers "if it
    did raise the baseline, restore {base}", an accusation this branch of the
    code explicitly could not verify: with no fork point there is no evidence
    about who moved the number. Reusing it told contributors who never touched
    the baseline to restore a value they never held.
    """
    cause = (
        "this is a shallow clone, so there is no common history to read: run "
        "`git fetch --unshallow` (or re-checkout at full depth) and re-run"
        if shallow
        else f"this checkout's history is unrelated to {facts.base_ref}: fetch "
        f"the real base branch and re-run"
    )
    return (
        f"{facts.label}: FORK POINT UNREADABLE. This tree records "
        f"{facts.baseline}, {facts.base_ref} records {facts.base} "
        f"(+{facts.excess}). The measured count is {facts.count}. git could "
        f"not name the commit where this branch left {facts.base_ref}, so "
        f"whether this tree moved the baseline cannot be determined and the "
        f"ratchet blocks rather than guess. Probable cause: {cause}."
    )


def _behind_base_message(facts: _BaseRefFacts) -> str:
    """Report a stale branch that never moved the number, without blocking it.

    Only printed for a caller that declared ``merge_tree_backed=True``, which
    is what makes the closing sentence true rather than decorative.
    """
    return (
        f"{facts.label}: BEHIND BASE (not blocking). This tree records "
        f"{facts.baseline}, {facts.base_ref} records {facts.base} "
        f"(+{facts.excess}), and the fork point records {facts.baseline} as "
        f"well, so this branch never moved the number: it is behind "
        f"{facts.base_ref}. The measured count is {facts.count}. "
        f"Merge or rebase from {facts.base_ref} to clear this notice. This "
        f"ratchet's baseline is registered in "
        f"scripts/ci/merge_tree_ratchet_registry.py, so what the merged result "
        f"would measure is gated by scripts/ci/merge_tree_ratchet_check.py, "
        f"not by this comparison."
    )


def _behind_base_unbacked_message(facts: _BaseRefFacts) -> str:
    """Report a stale branch on a ratchet with no merge-tree backstop, blocking.

    The relaxation above trades this comparison for the merge-tree gate. A
    ratchet whose baseline is absent from
    ``scripts/ci/merge_tree_ratchet_registry.py`` has no such gate, so trading
    it away leaves nothing measuring the merged result: the branch's stale
    ceiling absorbs violations that land above the base's real one.
    """
    return (
        f"{facts.label}: BEHIND BASE. This tree records {facts.baseline}, "
        f"{facts.base_ref} records {facts.base} (+{facts.excess}), and the "
        f"fork point records {facts.baseline} as well, so this branch never "
        f"moved the number: it is behind {facts.base_ref}. The measured count "
        f"is {facts.count}. Merge or rebase from {facts.base_ref} and re-run. "
        f"This is blocking because this ratchet's baseline is NOT registered "
        f"in scripts/ci/merge_tree_ratchet_registry.py: nothing else would "
        f"measure the merged result, so the stale ceiling cannot be waived "
        f"here."
    )


def _verdict_for_move(
    move: BaselineMove | None,
    facts: _BaseRefFacts,
    *,
    shallow: bool,
    merge_tree_backed: bool,
) -> int | None:
    """Pick the message and exit code for one measured fork-point direction."""
    if move is None:
        print(_unreadable_fork_message(facts, shallow=shallow), file=sys.stderr)
        return EXIT_REGRESSION
    if move.direction == BASELINE_RAISED:
        print(_above_base_message(facts), file=sys.stderr)
        return EXIT_REGRESSION
    if move.direction == BASELINE_LOWERED:
        print(_lowered_here_message(facts, at_fork=move.at_fork), file=sys.stderr)
        return EXIT_REGRESSION
    if not merge_tree_backed:
        print(_behind_base_unbacked_message(facts), file=sys.stderr)
        return EXIT_REGRESSION
    print(_behind_base_message(facts))
    return None


def _base_ref_verdict(
    args: argparse.Namespace,
    *,
    label: str,
    baseline: int,
    count: int,
    merge_tree_backed: bool,
) -> int | None:
    """Exit code when ``--base-ref`` blocks the run, or None to keep going.

    A baseline above the one at the base ref blocks when this branch is what
    moved it, in either direction, and when git cannot say. ``count`` has to be
    measured before this runs so the verdict can report it (issue #4066).

    Issue #5065. The check used to block on ``baseline > base`` alone, which is
    a property of the base ref moving rather than of anything the branch
    authored: the moment ``main`` lowers a baseline, every branch cut before
    that lowering fails. Measured 2026-08-03 against
    ``scripts/ci/taste_count_baseline.txt`` at 598 on ``main``: 31 of 33 open
    non-draft PRs recorded a higher number, and the queue was blocked on a
    bookkeeping value none of those branches had touched.

    ``merge_tree_backed`` is what makes passing that branch safe, and it is a
    per-caller fact rather than a property of this module. The relaxation
    trades this endpoint comparison for a gate that measures the merged tree,
    so it may only be taken by a ratchet that HAS that gate:
    ``scripts/ci/merge_tree_ratchet_check.py::_effective_baseline`` takes the
    lower of the two sides, verbatim::

        if base_value is None or merged_value is None:
            return None
        return min(base_value, merged_value)

    That gate evaluates exactly the ratchets listed in
    ``scripts/ci/merge_tree_ratchet_registry.py::RATCHETS``, which at the time
    of writing is five of the six count ratchets in ``scripts/ci``; the
    subprocess-encoding ratchet is not among them. A caller that is not
    registered passes ``merge_tree_backed=False`` and keeps the old blocking
    behaviour, because for it this comparison was the whole guard.
    ``tests/ci/test_merge_tree_backing_declarations.py`` pins each caller's
    declaration against the registry so the two cannot drift.

    Stricter/looser/different than canonical: this check reads the fork point,
    which the merge-tree gate never does, and it evaluates the branch's own
    tree rather than the merged one. Neither subsumes the other. This one keeps
    the recorded scalar one-directional; that one keeps the merged count under
    the lower of the two ceilings.
    """
    root = args.repo_root.resolve()
    if baseline_absent_at_ref(root, args.base_ref, args.baseline):
        print(
            f"{label}: bootstrap. {args.base_ref} records no baseline yet, "
            f"so there is no earlier value to raise. The one-directional "
            f"check starts once this baseline lands."
        )
        return None
    base = baseline_at_ref(root, args.base_ref, args.baseline)
    if base is None:
        print(f"error: could not read the baseline at {args.base_ref}", file=sys.stderr)
        return EXIT_EXTERNAL
    if baseline <= base:
        return None
    facts = _BaseRefFacts(
        base_ref=args.base_ref, label=label, baseline=baseline, base=base, count=count
    )
    move = baseline_move(root, args.base_ref, args.baseline, baseline)
    return _verdict_for_move(
        move,
        facts,
        shallow=is_shallow_repository(root),
        merge_tree_backed=merge_tree_backed,
    )


def run(
    args: argparse.Namespace,
    *,
    label: str,
    counter: Callable[[Path], int | None],
    scan_error: str,
    regression_advice: str,
    lister: Callable[[Path, frozenset[str]], list[str] | None] | None = None,
    merge_tree_backed: bool = False,
) -> int:
    """Evaluate one ratchet. ``counter`` returns the current count, or None.

    ``lister`` is an optional function that returns the full violation list,
    given the repo root and the set of paths the branch changed. When provided
    and a regression is detected, the violations are printed to stderr so
    contributors can see what needs fixing without a separate run (issue #3902).
    A lister is expected to order branch-touched files first so the 40-line cap
    cannot hide the violation that caused the regression.

    ``merge_tree_backed`` states whether this ratchet's baseline is listed in
    ``scripts/ci/merge_tree_ratchet_registry.py::RATCHETS``. Only a registered
    ratchet may pass a branch that is merely behind the base ref, because only
    a registered ratchet has a gate measuring the merged result. It defaults to
    False so a ratchet added without thinking about this gets the strict, safe
    behaviour rather than a silent hole; see ``_base_ref_verdict``.
    """
    baseline = read_baseline(args.baseline)
    if baseline is None:
        print(f"error: baseline missing or malformed: {args.baseline}", file=sys.stderr)
        return EXIT_CONFIG

    count = counter(args.repo_root.resolve())
    if count is None:
        print(f"error: {scan_error}", file=sys.stderr)
        return EXIT_EXTERNAL

    if args.base_ref:
        verdict = _base_ref_verdict(
            args,
            label=label,
            baseline=baseline,
            count=count,
            merge_tree_backed=merge_tree_backed,
        )
        if verdict is not None:
            return verdict

    if count > baseline:
        print(
            f"{label}: REGRESSION. {count} violations > baseline {baseline} "
            f"(+{count - baseline}). {regression_advice}",
            file=sys.stderr,
        )
        if lister is not None:
            root = args.repo_root.resolve()
            violations = lister(root, changed_files(root, args.base_ref))
            if violations:
                max_lines = 40
                lines = violations[:max_lines]
                print("\nCurrent violations:", file=sys.stderr)
                for line in lines:
                    print(f"  {line}", file=sys.stderr)
                if len(violations) > max_lines:
                    print(
                        f"  ... and {len(violations) - max_lines} more",
                        file=sys.stderr,
                    )
        return EXIT_REGRESSION

    if count < baseline:
        if args.update:
            args.baseline.write_text(f"{count}\n", encoding="utf-8")
            print(
                f"{label}: improved {baseline} -> {count} (-{baseline - count}). Baseline lowered."
            )
            return EXIT_OK
        problem = baseline_health(count, baseline)
        if problem is not None:
            print(f"{label}: STALE BASELINE. {problem}", file=sys.stderr)
            return EXIT_REGRESSION
        print(
            f"{label}: OK. {count} violations <= baseline {baseline} (-{baseline - count} slack)."
        )
        return EXIT_OK

    print(f"{label}: OK (count == baseline {baseline}).")
    return EXIT_OK
