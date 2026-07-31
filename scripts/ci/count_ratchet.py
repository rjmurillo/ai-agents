"""Shared machinery for whole-repo violation-count ratchets.

A count ratchet freezes a repository-wide violation total in a baseline file.
The measured count must equal the baseline. ``--update`` records an improvement;
an unrecorded decrease fails because it leaves slack for later regressions.

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
``tests/ci/test_count_ratchet_against_real_git.py``.

Stdlib only: these gates run by path in CI (``python scripts/ci/<name>.py``) and
must not depend on the project's import graph.

Exit codes (AGENTS.md contract):
    0 - ok (count == baseline, or --update records a decrease)
    1 - regression (count != baseline, or baseline raised vs --base-ref)
    2 - config error (baseline missing or malformed, bad args)
    3 - external error (the underlying linter could not run)
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

EXIT_OK = 0
EXIT_REGRESSION = 1
EXIT_CONFIG = 2
EXIT_EXTERNAL = 3

# Windows CreateProcess caps a command line at 32767 characters; POSIX raises
# E2BIG well above that. Batching at 24000 bytes keeps a single scan below both
# without needing a platform check.
ARGV_BUDGET_BYTES = 24000


def tracked_files(repo_root: Path, globs: Sequence[str]) -> list[str] | None:
    """Git-tracked paths matching ``globs``, or None when git could not run."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_root), "ls-files", "-z", "--", *globs],
            capture_output=True,
            text=True,
            errors="replace",
            encoding="utf-8",
            check=False,
        )
    except (FileNotFoundError, OSError) as exc:
        sys.stderr.write(f"git could not be launched: {exc}\n")
        return None
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr)
        return None
    return [path for path in proc.stdout.split("\0") if path]


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


def _baseline_rel(repo_root: Path, baseline: Path) -> str:
    """Repo-relative POSIX path of ``baseline``, for addressing it inside a ref."""
    try:
        return baseline.resolve().relative_to(repo_root).as_posix()
    except ValueError:
        return baseline.as_posix()


def _git_run(
    repo_root: Path, argv: Sequence[str]
) -> subprocess.CompletedProcess[str] | None:
    """Run a git command, or None when git could not be launched."""
    try:
        return subprocess.run(
            ["git", "-C", str(repo_root), *argv],
            capture_output=True,
            text=True,
            errors="replace",
            encoding="utf-8",
            check=False,
        )
    except (FileNotFoundError, OSError) as exc:
        sys.stderr.write(f"git could not be launched: {exc}\n")
        return None


def _git_rc(repo_root: Path, argv: Sequence[str]) -> int | None:
    """Exit status of a git command, or None when git could not be launched."""
    proc = _git_run(repo_root, argv)
    return None if proc is None else proc.returncode


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
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_root), "show", f"{ref}:{rel}"],
            capture_output=True,
            text=True,
            errors="replace",
            encoding="utf-8",
            check=False,
        )
    except (FileNotFoundError, OSError) as exc:
        sys.stderr.write(f"git could not be launched: {exc}\n")
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


def _above_base_message(
    base_ref: str, *, label: str, baseline: int, base: int, count: int
) -> str:
    """Report a baseline above the base ref without guessing who raised it.

    Two histories land on identical numbers here: a branch cut before the base
    ref lowered its baseline, and a branch that raised the baseline itself. A
    branch behind a base ref that dropped three violations reads
    ``baseline 334, base 331, count 334``, and so does a branch that added
    three violations and widened the allowance to cover them. Telling either
    author which one they are needs the fork point, and two endpoint reads
    cannot supply it. The base ref also arrives via ``git fetch --depth=1``
    (``.github/workflows/pytest.yml``), so its history is not guaranteed to be
    there to read. Naming a cause anyway is the defect issue #4066 was filed
    for, so this states what was measured and carries both remedies.

    The count is worth stating on its own: when it is one the base ref already
    allows, nothing in this tree added a violation, and that much IS measured.
    """
    measured = f"The measured count is {count}. "
    if count <= base:
        measured = (
            f"The measured count is {count}, which {base_ref} already allows, "
            f"so nothing in this tree added a violation. "
        )
    return (
        f"{label}: BASELINE ABOVE BASE. This tree records {baseline}, "
        f"{base_ref} records {base} (+{baseline - base}). {measured}"
        f"The baseline may only fall. If this branch did not edit the "
        f"baseline, it is behind {base_ref}: merge or rebase to pick up the "
        f"lowered value. If it did raise the baseline, restore {base} and fix "
        f"the violations instead of widening the allowance."
    )


def _base_ref_verdict(
    args: argparse.Namespace, *, label: str, baseline: int, count: int
) -> int | None:
    """Exit code when ``--base-ref`` blocks the run, or None to keep going.

    A baseline above the one at the base ref always blocks. ``count`` has to be
    measured before this runs so the verdict can report it (issue #4066).
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
    print(
        _above_base_message(
            args.base_ref, label=label, baseline=baseline, base=base, count=count
        ),
        file=sys.stderr,
    )
    return EXIT_REGRESSION


def run(
    args: argparse.Namespace,
    *,
    label: str,
    counter: Callable[[Path], int | None],
    scan_error: str,
    regression_advice: str,
) -> int:
    """Evaluate one ratchet. ``counter`` returns the current count, or None."""
    baseline = read_baseline(args.baseline)
    if baseline is None:
        print(f"error: baseline missing or malformed: {args.baseline}", file=sys.stderr)
        return EXIT_CONFIG

    count = counter(args.repo_root.resolve())
    if count is None:
        print(f"error: {scan_error}", file=sys.stderr)
        return EXIT_EXTERNAL

    if args.base_ref:
        verdict = _base_ref_verdict(args, label=label, baseline=baseline, count=count)
        if verdict is not None:
            return verdict

    if count > baseline:
        print(
            f"{label}: REGRESSION. {count} violations > baseline {baseline} "
            f"(+{count - baseline}). {regression_advice}",
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
        print(
            f"{label}: BASELINE STALE. {count} violations < baseline {baseline} "
            f"(-{baseline - count}). Run with --update to lower the baseline and "
            f"close the slack. Nothing here can see why the count fell, so the "
            f"cause is not measured: the usual one is two changes that each "
            f"lowered this baseline to the same value and merged without "
            f"conflict, leaving the tree improved twice while the file fell "
            f"once. The remedy is the same whatever the cause: a baseline-only "
            f"commit recording the true count.",
            file=sys.stderr,
        )
        return EXIT_REGRESSION

    print(f"{label}: OK (count == baseline {baseline}).")
    return EXIT_OK
