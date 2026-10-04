"""Count ratchet whose ceiling is measured at the merge base (issue #5363).

A committed baseline integer has two costs. Two PRs that each lower it conflict
on one line (issue #4171), and a branch that clears violations without running
``--update`` leaves slack that a later regression spends silently. ADR-092
removed the same class for the plugin version by deleting the field. This
module does the same for the count baselines: nothing is recorded, and the
ceiling is derived when the check runs.

The ceiling is the count measured on the tree at ``git merge-base HEAD
<base-ref>``. The branch may not exceed it. Because the ceiling comes from the
fork point, a ``main`` that moves underneath the branch changes nothing here,
so the BEHIND BASE states the scalar comparison needed do not exist.
``scripts/ci/merge_tree_ratchet_check.py`` measures the merged tree against the
base tip, which is the other half of the stale-branch guard.

Three outcomes are explicit and blocking or non-blocking on purpose:

* No ``--base-ref``: exit 2. Without a ref there is no ceiling, and a run that
  silently skipped the comparison would read as a pass.
* No fork point (shallow clone, unrelated history): exit 3, the same class as
  a git read failure.
* Bootstrap: the registry at the fork point does not list the ratchet's label
  and the fork does not carry its script, so the branch introduces the ratchet
  and there is no earlier tree to hold it to. Exit 0 with a message that names
  the state. A label the fork registers that the branch removes or re-points
  exits 1 instead (``ratchet_registry_at_ref.py``).

Every other failure to measure the fork tree is exit 3. A ceiling that could not
be measured never becomes a pass.

Exit codes (AGENTS.md contract):
    0 - ok (count <= count at the merge base, or bootstrap)
    1 - regression (count > count at the merge base)
    2 - config error (no --base-ref)
    3 - external error (counter could not run, or no fork point)
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.ci.count_ratchet import (
    EXIT_CONFIG,
    EXIT_EXTERNAL,
    EXIT_OK,
    EXIT_REGRESSION,
    _fork_point,
    baseline_absent_at_ref,
    changed_files,
    git_environment,
    is_shallow_repository,
)
from scripts.ci.merge_tree_materialization import (
    init_scratch_repo,
    materialize_tree,
    remove_tree,
    run_git,
)
from scripts.ci.ratchet_registry_at_ref import (
    RegistryEntries,
    registry_drift,
    registry_labels_at,
)

__all__ = [
    "CommitScratch",
    "EXIT_CONFIG",
    "EXIT_EXTERNAL",
    "EXIT_OK",
    "EXIT_REGRESSION",
    "build_parser",
    "fork_registry_verdict",
    "introduced_at",
    "measure_commit",
    "run",
]

Counter = Callable[[Path], int | None]
Lister = Callable[[Path, frozenset[str]], list[str] | None]


def build_parser(description: str) -> argparse.ArgumentParser:
    """Argument parser shared by the base-derived ratchets."""
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path.cwd(),
        help="Repository root (default: current working directory).",
    )
    parser.add_argument(
        "--base-ref",
        help=(
            "Git ref whose merge base with HEAD supplies the ceiling. Required: "
            "the ceiling is the count measured on that tree."
        ),
    )
    return parser


class CommitScratch:
    """One commit's tree, materialized at most once and measured by many counters.

    The tree is materialized into a scratch repository on first use, because
    every counter reads tracked files through git and must not see the working
    tree of the branch under test. ``close`` removes the scratch and returns a
    cleanup error, or None; a caller that gets one must not trust a measurement.
    """

    def __init__(self, repo_root: Path, commit: str) -> None:
        self._repo_root = repo_root
        self._commit = commit
        self._scratch: Path | None = None
        self._ready: bool | None = None

    def _materialize(self) -> bool:
        proc = run_git(
            self._repo_root,
            "rev-parse",
            "--verify",
            f"{self._commit}^{{tree}}",
            env=git_environment(),
        )
        if proc.returncode != 0:
            sys.stderr.write(f"could not resolve the tree of {self._commit}: {proc.stderr}\n")
            return False
        tree_oid = proc.stdout.strip()
        try:
            self._scratch = Path(tempfile.mkdtemp(prefix="base-derived-ratchet-"))
        except OSError as exc:
            sys.stderr.write(f"scratch creation failed: {type(exc).__name__}: {exc}\n")
            return False
        return materialize_tree(self._repo_root, tree_oid, self._scratch) and init_scratch_repo(
            self._scratch
        )

    def measure(self, counter: Counter) -> int | None:
        """Count violations on the commit's tree, or None when it cannot be measured."""
        if self._ready is None:
            self._ready = self._materialize()
        if not self._ready or self._scratch is None:
            return None
        return counter(self._scratch)

    def close(self) -> str | None:
        """Remove the scratch directory. Returns a cleanup error, or None."""
        if self._scratch is None:
            return None
        return remove_tree(self._scratch, "base-derived ratchet scratch")


def measure_commit(repo_root: Path, commit: str, counter: Counter) -> int | None:
    """Count violations on the tree of ``commit``, or None when it cannot be measured.

    Scratch is removed on every exit path. A failed cleanup is not a
    measurement.
    """
    tip = CommitScratch(repo_root, commit)
    try:
        count = tip.measure(counter)
    finally:
        cleanup_error = tip.close()
    if cleanup_error:
        sys.stderr.write(f"{cleanup_error}\n")
        return None
    return count


def introduced_at(repo_root: Path, commit: str, script: str) -> bool:
    """True when ``commit`` does not carry ``script`` yet: the bootstrap state.

    Delegates to ``baseline_absent_at_ref``, an allowlist that answers True only
    when the ref resolves and the path is the one thing missing. A typo'd ref or
    an unlaunchable git answers False, so the caller goes on to measure and
    fails closed instead of reading a git error as "first run".
    """
    return baseline_absent_at_ref(repo_root, commit, repo_root / script)


def branch_registry() -> RegistryEntries:
    """Return label -> script path for the ratchets this branch registers."""
    import importlib

    registry = importlib.import_module("scripts.ci.merge_tree_ratchet_registry")
    return {r.label: r.script_path for r in registry.RATCHETS}


def fork_registry_verdict(
    repo_root: Path, fork: str
) -> tuple[RegistryEntries | None, list[str]]:
    """Read the registry at ``fork`` and compare it with the branch's.

    Returns the fork's entries (None when unreadable) and one message per label
    the branch removed or re-pointed. The fork is read through ``git show``,
    never from the working tree, so the branch cannot edit what it is held to.
    """
    entries = registry_labels_at(repo_root, fork)
    if entries is None:
        return None, []
    return entries, registry_drift(entries, branch_registry())


def _unreadable_fork_message(label: str, base_ref: str, *, shallow: bool) -> str:
    cause = (
        "this is a shallow clone, so there is no common history to read: run "
        "`git fetch --unshallow` (or re-checkout at full depth) and re-run"
        if shallow
        else f"{base_ref} is not fetched, is not a valid ref, or shares no history "
        f"with this checkout: fetch the real base branch and re-run"
    )
    return (
        f"{label}: FORK POINT UNREADABLE. git could not name the commit where "
        f"this branch left {base_ref}, so the ceiling cannot be measured and "
        f"the ratchet blocks rather than guess. Probable cause: {cause}."
    )


def _print_violations(lister: Lister, repo_root: Path, base_ref: str) -> None:
    violations = lister(repo_root, changed_files(repo_root, base_ref))
    if not violations:
        return
    max_lines = 40
    print("\nCurrent violations:", file=sys.stderr)
    for line in violations[:max_lines]:
        print(f"  {line}", file=sys.stderr)
    if len(violations) > max_lines:
        print(f"  ... and {len(violations) - max_lines} more", file=sys.stderr)


def _ceiling(
    root: Path, args: argparse.Namespace, label: str, counter: Counter, introduced_by: str
) -> tuple[int | None, int]:
    """Ceiling at the fork point and an exit code. Ceiling None means stop or skip."""
    fork = _fork_point(root, args.base_ref)
    if fork is None:
        message = _unreadable_fork_message(
            label, args.base_ref, shallow=is_shallow_repository(root)
        )
        print(message, file=sys.stderr)
        return None, EXIT_EXTERNAL
    entries, drift = fork_registry_verdict(root, fork)
    if entries is None:
        print(
            f"{label}: REGISTRY UNREADABLE. Could not read the ratchet registry at "
            f"the fork point {fork[:12]}, so a removed or moved ratchet cannot be "
            f"ruled out and the ratchet blocks.",
            file=sys.stderr,
        )
        return None, EXIT_EXTERNAL
    if drift:
        print("\n".join(drift), file=sys.stderr)
        return None, EXIT_REGRESSION
    if label not in entries and introduced_at(root, fork, introduced_by):
        if branch_registry().get(label) != introduced_by:
            print(
                f"{label}: BOOTSTRAP REFUSED. The branch registry does not map "
                f"this label to {introduced_by}, so the run arguments cannot "
                f"name their own bootstrap. Register the ratchet and re-run.",
                file=sys.stderr,
            )
            return None, EXIT_REGRESSION
        print(
            f"{label}: bootstrap. {args.base_ref} does not carry {introduced_by} "
            f"yet, so there is no earlier tree to hold this branch to. The "
            f"ceiling starts once the ratchet lands."
        )
        return None, EXIT_OK
    ceiling = measure_commit(root, fork, counter)
    if ceiling is None:
        print(
            f"error: {label}: could not measure the merge base {fork[:12]}",
            file=sys.stderr,
        )
        return None, EXIT_EXTERNAL
    return ceiling, EXIT_OK


def run(
    args: argparse.Namespace,
    *,
    label: str,
    counter: Counter,
    scan_error: str,
    regression_advice: str,
    introduced_by: str,
    lister: Lister | None = None,
) -> int:
    """Evaluate one ratchet. ``counter`` returns the current count, or None.

    ``introduced_by`` is the repo-relative path of the ratchet's own script. A
    fork point that lacks it is the bootstrap state.
    """
    if not args.base_ref:
        print(
            f"error: {label}: --base-ref is required. The ceiling is the count "
            f"measured at the merge base, so a run without a ref has nothing to "
            f"compare against.",
            file=sys.stderr,
        )
        return EXIT_CONFIG
    root = args.repo_root.resolve()
    count = counter(root)
    if count is None:
        print(f"error: {scan_error}", file=sys.stderr)
        return EXIT_EXTERNAL
    ceiling, code = _ceiling(root, args, label, counter, introduced_by)
    if ceiling is None:
        return code
    if count > ceiling:
        print(
            f"{label}: REGRESSION. {count} violations > {ceiling} at the merge "
            f"base (+{count - ceiling}). {regression_advice}",
            file=sys.stderr,
        )
        if lister is not None:
            _print_violations(lister, root, args.base_ref)
        return EXIT_REGRESSION
    if count < ceiling:
        print(
            f"{label}: OK. {count} violations, {ceiling - count} below the "
            f"merge base ({ceiling})."
        )
        return EXIT_OK
    print(f"{label}: OK (count == merge base {ceiling}).")
    return EXIT_OK
