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
from scripts.ci.merge_tree_ratchet_registry import RATCHETS

EXIT_OK = 0
EXIT_REGRESSION = 1
EXIT_CONFIG = 2
EXIT_EXTERNAL = 3
EXIT_CONFLICT = 100


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


def _remote_branch(base_ref: str) -> str | None:
    for prefix in ("origin/", "refs/remotes/origin/"):
        if base_ref.startswith(prefix):
            branch = base_ref[len(prefix) :]
            return branch if branch and "/" not in branch else None
    return None


def _refresh_base_ref(repo_root: Path, base_ref: str) -> bool:
    """Refresh a remote-tracking base before resolving its immutable OID."""
    branch = _remote_branch(base_ref)
    if branch is None:
        return True
    refspec = f"+refs/heads/{branch}:refs/remotes/origin/{branch}"
    proc = _git(repo_root, "fetch", "--no-tags", "--quiet", "origin", refspec)
    if proc.returncode == 0:
        return True
    detail = _sanitize_diagnostic(proc.stderr) or f"git fetch rc {proc.returncode}"
    print(
        f"merge-tree-ratchet: failed to refresh {base_ref}: {detail}",
        file=sys.stderr,
    )
    return False


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


def _merge_tree_oid(repo_root: Path, base_oid: str) -> tuple[str | None, bool]:
    """Return (tree-oid, conflicts). oid is None on git failure.

    Every None return writes its own explanation to stderr, so callers must not
    add a second generic one. Two messages for one failure make the specific
    diagnosis read like a guess (PR #4567 review).
    """
    proc = _git(repo_root, "merge-tree", "--write-tree", base_oid, "HEAD")
    if proc.returncode in (0, 1):
        # exit 1 means conflicts; stdout still has the partial tree oid on line 1
        lines = proc.stdout.strip().splitlines()
        conflicts = proc.returncode == 1
        if not lines:
            sys.stderr.write(
                f"merge-tree-ratchet: git merge-tree exited {proc.returncode} but wrote\n"
                "no tree OID, so there is no merged tree to evaluate.\n"
            )
            return None, conflicts
        return lines[0], conflicts
    sys.stderr.write(f"git merge-tree failed (rc {proc.returncode}):\n{proc.stderr}\n")
    if "unrelated histories" in proc.stderr:
        sys.stderr.write(
            "merge-tree-ratchet: no merge base was reachable. This is a shallow-fetch\n"
            "regression, not a ratchet breach: a `git fetch --depth=1` writes\n"
            ".git/shallow and cuts history traversal, so any branch behind the base\n"
            "aborts here. Fetch the base ref at full depth (issue #4518).\n"
        )
    return None, False


def _sanitize_diagnostic(text: str) -> str:
    cleaned = " ".join(text.replace("\x00", "").split())
    return cleaned[:500]


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
    repo_root: Path, base_oid: str, scratch_root: Path
) -> int:
    exit_code = EXIT_OK
    for ratchet in RATCHETS:
        base = _read_baseline_at_ref(repo_root, base_oid, ratchet.baseline_path)
        merged = _read_baseline_in_tree(scratch_root, ratchet.baseline_path)
        code, msg = _check_one(
            ratchet.label,
            ratchet.current_count(scratch_root),
            base,
            merged,
        )
        exit_code = max(exit_code, code)
        if code != EXIT_OK:
            print(f"merge-tree-ratchet: {msg}", file=sys.stderr)
        else:
            print(f"merge-tree-ratchet: {msg}")
    return exit_code


def _evaluate_merged_tree(repo_root: Path, base_ref: str) -> int:
    """Extract merged tree, run counters, compare. Returns an EXIT_* code."""
    base_oid, tree_oid, preparation_exit = _prepare_merged_tree(repo_root, base_ref)
    if preparation_exit != EXIT_OK:
        return preparation_exit
    assert base_oid is not None and tree_oid is not None

    try:
        scratch_root = Path(tempfile.mkdtemp(prefix="merge-tree-ratchet-"))
    except OSError as exc:
        print(f"scratch creation failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return EXIT_EXTERNAL

    primary_exit = EXIT_EXTERNAL
    cleanup_error: str | None = None
    try:
        if _materialize_tree(repo_root, tree_oid, scratch_root) and _init_scratch_repo(
            scratch_root
        ):
            primary_exit = _evaluate_registered_ratchets(
                repo_root, base_oid, scratch_root
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
        default="origin/main",
        help="Git ref to merge HEAD into and read baselines from (default: origin/main).",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path.cwd(),
        help="Repository root (default: cwd).",
    )
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    return _evaluate_merged_tree(args.repo_root.resolve(), args.base_ref)


if __name__ == "__main__":
    sys.exit(main())
