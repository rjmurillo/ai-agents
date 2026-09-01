#!/usr/bin/env python3
"""Merge-tree ratchet: evaluate all count ratchets on the merged result.

Issue #4398. Closes the stale-branch hole: a PR branch can pass every ratchet
individually, yet the merged result still breaches the ceiling, because the
branch is measured against an old target branch that held a looser baseline.

PR #4272 is the canonical example: it grew a file past the taste-lint 500-line
ceiling and merged green because strict_required_status_checks_policy is false
on this repository's ruleset. A stale-base merge can pass while the merged
result fails.

DOES NOT CLOSE the concurrent-admission hole (issue #4345, reserve-band
mechanism). Three PRs each passing against the same current main all show a
clean merge-tree individually; the union breaches only when all three land.
These two fixes are complementary. Say so in any PR that ships this gate.

Mechanism:
    git merge-tree --write-tree <base> <head>
    git read-tree <tree-oid> through a temporary index
    git checkout-index every entry into <scratch>
    git init <scratch>, git -C <scratch> add -A, git -C <scratch> commit
    run each registered current_count() against <scratch>
    compare against min(baseline at <base>, baseline in the merged tree)

The ceiling is the LOWER of the base's baseline and the one the merged tree
would install (issue #4538). Reading only the base's value left the gate blind
to a branch that LOWERS a baseline: PR #4208 rewrote the ruff baseline
308 -> 126 while activating RUF100, its merged tree measured 140, and 140 <= 308
passed here. main merged red. Taking the minimum also keeps a RAISED baseline
from buying headroom. See _effective_baseline.

Conflict policy: fail closed with a distinct exit because no complete merged
tree exists to evaluate. The diagnostic tells the caller to resolve conflicts
and rerun the ratchet.

Scratch cleanup: always, on every exit path including exceptions.

Exit codes (AGENTS.md contract):
    0 - ok (all counts <= baselines)
    1 - regression (at least one count > baseline)
    2 - config error (baseline missing, bad args)
    3 - external error (git, ruff, or taste-lints could not run)
    100 - merge conflict (ratchets were not evaluated)
"""

from __future__ import annotations

import argparse
import sys
import tempfile
import time
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.ci.merge_tree_materialization import (
    init_scratch_repo as _init_scratch_repo,
)
from scripts.ci.merge_tree_materialization import materialize_tree as _materialize_tree
from scripts.ci.merge_tree_materialization import remove_tree as _remove_tree
from scripts.ci.merge_tree_materialization import run_git as _git
from scripts.ci.merge_tree_ratchet_baseline_direction import (
    raised_baseline as _one_directional_baseline_failure,
)
from scripts.ci.merge_tree_ratchet_preparation import (
    _merge_tree_oid,
    _refresh_base_ref,
    _sanitize_diagnostic,
    is_fast_forward_clean,
)
from scripts.ci.merge_tree_ratchet_preparation import (
    resolve_default_base_ref as _resolve_default_base_ref,
)
from scripts.ci.merge_tree_ratchet_registry import RATCHETS

EXIT_OK = 0
EXIT_REGRESSION = 1
EXIT_CONFIG = 2
EXIT_EXTERNAL = 3
EXIT_CONFLICT = 100

# Measured 2026-09-01 (issue #5441): the slowest of the five registered
# ratchets, the CLI exit-contract scan, alone took ~27s on a warm checkout;
# the full materialize-and-recount path (the non-fast-forward fallback) took
# ~64s. 90s leaves real headroom over that without being open-ended; a
# ratchet that cannot finish inside it reports "not run" instead of leaving
# the caller to be killed by the outer Lefthook timeout with no diagnostic.
#
# Pinned to 90s rather than a larger number that would fit a slower machine
# with more room to spare: the standalone merge-tree-ratchet Lefthook job's
# outer timeout is capped at the fast parallel group's existing 2m ceiling
# (scripts/validation/checks_ratchet.py's sibling job docstring explains why
# tests/ci/test_lefthook_declared_budget.py forbids raising it), which needs
# _MINIMUM_MARGIN_SECONDS (30s, tests/test_lefthook_integration.py) of
# headroom over this constant. A machine too slow to finish inside 90s hits
# this deadline and reports a clear per-ratchet "not run" instead of Lefthook
# silently killing the process, which is strictly better than the pre-#5441
# behavior even though it does not raise the ceiling further.
_TIMEOUT_SECONDS = 90


class BaselineState(Enum):
    VALUE = auto()
    MISSING = auto()
    MALFORMED = auto()
    EXTERNAL = auto()


@dataclass(frozen=True, slots=True)
class BaselineRead:
    state: BaselineState
    value: int | None = None
    diagnostic: str = ""


def _resolve_base_oid(repo_root: Path, base_ref: str) -> str | None:
    """Resolve the mutable base ref once, or report why it cannot be pinned."""
    if not _refresh_base_ref(repo_root, base_ref):
        return None
    proc = _git(
        repo_root,
        "rev-parse",
        "--verify",
        "--end-of-options",
        f"{base_ref}^{{commit}}",
    )
    oid = proc.stdout.strip()
    if proc.returncode == 0 and oid:
        return oid
    sys.stderr.write(
        f"merge-tree-ratchet: cannot resolve base ref {base_ref!r} to a commit OID.\n"
        f"{proc.stderr}\n"
    )
    return None


def _parse_baseline(text: str) -> BaselineRead:
    try:
        return BaselineRead(BaselineState.VALUE, int(text.strip()))
    except ValueError:
        return BaselineRead(BaselineState.MALFORMED)


def _read_baseline_at_ref(
    repo_root: Path, ref: str, rel_path: str
) -> BaselineRead:
    """Read one baseline while distinguishing absence from Git failure."""
    listed = _git(repo_root, "ls-tree", "--name-only", ref, "--", rel_path)
    if listed.returncode != 0:
        detail = _sanitize_diagnostic(listed.stderr) or f"git ls-tree rc {listed.returncode}"
        return BaselineRead(BaselineState.EXTERNAL, diagnostic=detail)
    if rel_path not in listed.stdout.splitlines():
        return BaselineRead(BaselineState.MISSING)
    shown = _git(repo_root, "show", f"{ref}:{rel_path}")
    if shown.returncode != 0:
        detail = _sanitize_diagnostic(shown.stderr) or f"git show rc {shown.returncode}"
        return BaselineRead(BaselineState.EXTERNAL, diagnostic=detail)
    return _parse_baseline(shown.stdout)


def _read_baseline_in_tree(tree_root: Path, rel_path: str) -> BaselineRead:
    """Read an integer baseline from a materialized tree.

    The merged tree carries the baseline file the merge would install on the
    target branch identified by the base ref. Reading it from the materialized
    snapshot (rather than from either input ref) is what makes the ceiling
    reflect the post-merge repository.
    """
    try:
        text = (tree_root / rel_path).read_text(encoding="utf-8")
    except FileNotFoundError:
        return BaselineRead(BaselineState.MISSING)
    except OSError as exc:
        return BaselineRead(
            BaselineState.EXTERNAL,
            diagnostic=_sanitize_diagnostic(f"{type(exc).__name__}: {exc}"),
        )
    return _parse_baseline(text)


def _effective_baseline(base_value: int | None, merged_value: int | None) -> int | None:
    """The ceiling the merged tree must satisfy: the lower of the two.

    Issue #4538. Comparing only against the baseline at the base ref left the
    gate blind in one direction. A PR that LOWERS a baseline is measured
    against the base's older, looser number, so the branch can install a
    ceiling the post-merge tree does not meet. PR #4208 is the worked example:
    it enabled RUF100 and rewrote the ruff baseline 308 -> 126 in one commit.
    Its own tree measured exactly 126, but between its base (``ca5deebe8``) and
    its merge, PR #4448 landed 14 more dead ``noqa`` directives. The merged
    tree measured 140 and still passed here, because 140 <= the base's 308.
    main merged red and blocked every unrelated push (issue #4538).

    Taking the minimum closes both directions at once and needs no knowledge of
    which side moved:

    - The PR lowers the baseline -> the merged (proposed) value wins, so the
      post-merge tree must actually meet the ceiling it ships.
    - The PR raises the baseline -> the base value wins, so widening the
      allowance cannot buy headroom for merged-tree debt.
    - Neither side moves -> both values agree and the minimum is that value.

    ``None`` propagates: an unreadable baseline on either side is a config
    error, never a silently skipped check.
    """
    if base_value is None or merged_value is None:
        return None
    return min(base_value, merged_value)


def _baseline_failure(
    label: str, base: BaselineRead, merged: BaselineRead
) -> tuple[int, str] | None:
    for source, result in (("base ref", base), ("merged tree", merged)):
        if result.state is BaselineState.EXTERNAL:
            return (
                EXIT_EXTERNAL,
                f"{label}: EXTERNAL ERROR - {source} baseline read failed: "
                f"{result.diagnostic}",
            )
        if result.state is BaselineState.MALFORMED:
            return EXIT_CONFIG, f"{label}: CONFIG ERROR - malformed baseline in {source}"
    if merged.state is BaselineState.MISSING:
        return EXIT_CONFIG, f"{label}: CONFIG ERROR - baseline missing in merged tree"
    return None


def _check_one(
    label: str,
    count: int | None,
    base: BaselineRead,
    merged: BaselineRead,
) -> tuple[int, str]:
    """Return (exit code, message)."""
    if count is None:
        return EXIT_EXTERNAL, f"{label}: EXTERNAL ERROR - counter returned None"

    failure = _baseline_failure(label, base, merged)
    if failure is not None:
        return failure
    assert merged.value is not None
    if base.state is BaselineState.MISSING:
        baseline = merged.value
    else:
        assert base.value is not None
        baseline = min(base.value, merged.value)
    if count > baseline:
        return (
            EXIT_REGRESSION,
            f"{label}: REGRESSION. {count} > effective baseline {baseline} "
            f"(+{count - baseline}); base ref records {base.value}, "
            f"merged tree records {merged.value}.",
        )
    return EXIT_OK, f"{label}: OK. {count} <= {baseline}."


def _prepare_merged_tree(
    repo_root: Path, base_ref: str
) -> tuple[str | None, str | None, int]:
    """Pin the base and construct a conflict-free merged tree."""
    base_oid = _resolve_base_oid(repo_root, base_ref)
    if base_oid is None:
        return None, None, EXIT_EXTERNAL
    tree_oid, conflicts = _merge_tree_oid(repo_root, base_oid)
    if tree_oid is None:
        return base_oid, None, EXIT_EXTERNAL
    if conflicts:
        sys.stderr.write(
            f"merge-tree-ratchet: merge has conflicts against {base_ref} "
            f"({base_oid[:12]}). Ratchets were not evaluated; resolve the conflicts "
            "and rerun the ratchet.\n"
        )
        return base_oid, tree_oid, EXIT_CONFLICT
    return base_oid, tree_oid, EXIT_OK


def _evaluate_registered_ratchets(
    repo_root: Path,
    base_oid: str,
    scratch_root: Path,
    *,
    base_ref: str,
    deadline: float | None = None,
) -> int:
    """Run every registered ratchet against ``scratch_root``.

    ``deadline`` (absolute ``time.monotonic()``) reports a clear "not run"
    verdict for a ratchet whose turn arrives after it, instead of risking an
    outer-timeout kill with no diagnostic (issue #5441). ``base_ref`` is the
    original ref string, not ``base_oid``: ``raised_baseline`` below reads the
    fork point between it and HEAD.
    """
    exit_code = EXIT_OK
    for ratchet in RATCHETS:
        if deadline is not None and time.monotonic() >= deadline:
            exit_code = max(exit_code, EXIT_EXTERNAL)
            print(
                f"merge-tree-ratchet: {ratchet.label}: FAIL. Not run: aggregate "
                "timeout exhausted.",
                file=sys.stderr,
            )
            continue
        base = _read_baseline_at_ref(repo_root, base_oid, ratchet.baseline_path)
        merged = _read_baseline_in_tree(scratch_root, ratchet.baseline_path)
        count = ratchet.current_count(scratch_root)
        code, msg = _check_one(ratchet.label, count, base, merged)
        if code == EXIT_OK and _one_directional_baseline_failure(
            repo_root, base_ref, ratchet, count
        ):
            # _one_directional_baseline_failure already printed its own
            # diagnostic (count_ratchet's _base_ref_verdict does), so the
            # merge-tree "OK" message below would contradict it; skip it.
            exit_code = max(exit_code, EXIT_REGRESSION)
            continue
        exit_code = max(exit_code, code)
        if code != EXIT_OK:
            print(f"merge-tree-ratchet: {msg}", file=sys.stderr)
        else:
            print(f"merge-tree-ratchet: {msg}")
    return exit_code


def _evaluate_merged_tree(
    repo_root: Path,
    base_ref: str,
    *,
    deadline: float | None = None,
) -> int:
    """Extract merged tree, run counters, compare. Returns an EXIT_* code.

    ``deadline`` lets a caller that already spent part of its own budget (for
    example ``checks_ratchet.py``'s aggregate) hand down the remaining share
    instead of this function measuring a fresh ``_TIMEOUT_SECONDS`` on top of
    it. Standalone callers, including ``main()``, leave it unset and get the
    module default.
    """
    base_oid, tree_oid, preparation_exit = _prepare_merged_tree(repo_root, base_ref)
    if preparation_exit != EXIT_OK:
        return preparation_exit
    assert base_oid is not None and tree_oid is not None
    effective_deadline = deadline if deadline is not None else time.monotonic() + _TIMEOUT_SECONDS

    if is_fast_forward_clean(repo_root, base_oid):
        # The working tree IS the merged tree (see is_fast_forward_clean), so
        # there is nothing to materialize: read baselines and count straight
        # off repo_root instead of a scratch copy, which is both faster and
        # what makes this the single authoritative pass for a caller that
        # already needs these same counts (issue #5441).
        primary_exit = _evaluate_registered_ratchets(
            repo_root, base_oid, repo_root, base_ref=base_ref, deadline=effective_deadline
        )
    else:
        try:
            scratch_root = Path(tempfile.mkdtemp(prefix="merge-tree-ratchet-"))
        except OSError as exc:
            print(f"scratch creation failed: {type(exc).__name__}: {exc}", file=sys.stderr)
            return EXIT_EXTERNAL

        primary_exit = EXIT_EXTERNAL
        cleanup_error: str | None = None
        try:
            if _materialize_tree(
                repo_root, tree_oid, scratch_root, deadline=effective_deadline
            ) and _init_scratch_repo(scratch_root, deadline=effective_deadline):
                primary_exit = _evaluate_registered_ratchets(
                    repo_root,
                    base_oid,
                    scratch_root,
                    base_ref=base_ref,
                    deadline=effective_deadline,
                )
        finally:
            cleanup_error = _remove_tree(scratch_root, "merge-tree scratch")
        if cleanup_error:
            print(cleanup_error, file=sys.stderr)
            if primary_exit == EXIT_OK:
                primary_exit = EXIT_EXTERNAL
    exit_code = primary_exit

    if exit_code == EXIT_REGRESSION:
        print(
            "\nmerge-tree-ratchet: BLOCKED. The merged result breaches a ratchet ceiling.\n"
            f"This means your branch is measured against a stale base ref ({base_ref}), "
            "or your changes\n"
            f"genuinely exceed the baseline. Merge or rebase from {base_ref} and re-check.\n"
            "If the ceiling is still breached after rebasing, fix the violations\n"
            "rather than raising the baseline: the ceiling here is the LOWER of the\n"
            "base's baseline and the one this branch would install.\n"
            "(See issues #4398 and #4538 for context.)",
            file=sys.stderr,
        )

    if exit_code != EXIT_OK:
        return exit_code

    print(
        f"merge-tree-ratchet: OK. Merged tree passes all registered ratchets "
        f"(base: {base_ref})."
    )
    return EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate registered count ratchets on the result of merging HEAD into "
            "base-ref. Closes the stale-branch hole (issue #4398)."
        )
    )
    parser.add_argument(
        "--base-ref",
        default=None,
        help=(
            "Git ref to merge HEAD into. Defaults to the same dynamic "
            "resolution checks_ratchet.py uses (PR base, then origin/HEAD, "
            "then origin/main): a hardcoded origin/main here measured a "
            "branch on a non-main base wrongly (issue #5441 review)."
        ),
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path.cwd(),
        help="Repository root (default: cwd).",
    )
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    repo_root = args.repo_root.resolve()
    base_ref = args.base_ref or _resolve_default_base_ref(repo_root)
    if base_ref is None:
        print(
            "merge-tree-ratchet: could not resolve a default base ref "
            "(no PR base, no origin/HEAD, no origin/main); pass --base-ref.",
            file=sys.stderr,
        )
        return EXIT_EXTERNAL
    return _evaluate_merged_tree(repo_root, base_ref)


if __name__ == "__main__":
    sys.exit(main())
