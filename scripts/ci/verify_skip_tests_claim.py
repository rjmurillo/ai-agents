#!/usr/bin/env python3
"""Independently verify the `python-changed == false` claim the skip-tests job acts on.

ADR-101 (`.project-toolkit/architecture/ADR-101-enforcement-planes.md`, "The same
pattern is live on a context that IS required") names the fail-open this
script closes: `test-result` and `skip-tests` in `pytest.yml` both publish
`name: Run Python Tests`, a required status context, and are mutually
exclusive on `needs.check-paths.outputs.python-changed`. Whichever leg runs
satisfies the required check. If `python-changed` is ever wrong in the false
direction, `skip-tests` reports success for a change no test ever ran.

Scope of what this closes: a bug in the filter *mechanism*, meaning
`dorny/paths-filter`'s own matching, `determine_should_run_from_filters.py`, or
the wiring between them. It does not close a gap in the policy *document*: this
script reads the same `path_policy.yml` the filter reads, so a path the policy
fails to name is invisible to both. Do not cite this script as protection
against that.

`check-paths` computes `python-changed` from `dorny/paths-filter` fed by
`scripts/test_selection/path_policy.yml`, via
`scripts/workflows/determine_should_run_from_filters.py`. This script does not
trust that computation. It recomputes the same policy match, independently,
from the repository's own path policy module
(`scripts.test_selection.path_policy`), against the same changed-file set
`scripts.test_selection.select_tests.changed_from_git` produces for test
selection elsewhere in this workflow. If any changed file matches the policy,
the `python-changed == false` claim `skip-tests` is acting on was wrong, and
this script fails the job that would otherwise report the required check
green.

Exit codes follow the repository contract (root `AGENTS.md` Standards):
  0  - ok: no changed file matches the policy (or nothing was examined)
  1  - logic: the claim disagrees with a recomputation, or the base/head
       inputs cannot support a verified claim
  2  - config: the path policy could not be loaded
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]

try:
    from scripts.test_selection import path_policy
    from scripts.test_selection.select_tests import changed_from_git
except ModuleNotFoundError:  # pragma: no cover - exercised via direct file execution
    sys.path.insert(0, str(_PROJECT_ROOT))
    from scripts.test_selection import path_policy
    from scripts.test_selection.select_tests import changed_from_git

EXIT_OK = 0
EXIT_LOGIC = 1
EXIT_CONFIG = 2

# `git` sends this all-zero SHA for `before` on a newly created branch pushed
# for the first time. It names no real commit, so a diff against it cannot be
# computed and the skip cannot be verified against an unknowable changed set.
_ALL_ZERO_SHA = "0" * 40

# Cap the per-file listing so a wide accidental match stays readable. The
# count of examined files lives in the OK message instead, which is what
# `.claude/rules/ci-scripts.md` MUST 12 asks for: a run that examined nothing
# must be distinguishable from a run that found nothing wrong.
_MAX_LISTED_MATCHES = 20


def _missing_sha_message(base: str, head: str) -> str:
    return (
        "REFUSED: cannot verify the python-changed=false claim without both "
        f"base and head SHAs (base={base!r}, head={head!r}). Approving the "
        "skip against an unknowable changed set would be the fail-open this "
        "check exists to close."
    )


def _unreadable_diff_message(base: str, head: str) -> str:
    return (
        f"REFUSED: could not diff {base}...{head}. A checkout too shallow "
        "to hold both commits cannot be verified, so the skip is not "
        "confirmed. Fetch full history (fetch-depth: 0) and retry."
    )


def _matches_message(matched: list[tuple[str, str]]) -> str:
    lines = [
        "FAIL: python-changed was reported false, but these changed files "
        "match the python path policy:"
    ]
    shown = matched[:_MAX_LISTED_MATCHES]
    lines.extend(f"  {rel} (matched {glob})" for rel, glob in shown)
    if len(matched) > len(shown):
        lines.append(f"  ... and {len(matched) - len(shown)} more")
    return "\n".join(lines)


def verify(repo_root: Path, base: str, head: str) -> tuple[int, str]:
    """Recompute the policy match for ``base...head`` and return (exit code, message).

    Order matches the module docstring: refuse on missing/unknowable SHAs,
    refuse on an undiffable range, fail on any policy match, otherwise pass.
    """
    if not base or not head or base == _ALL_ZERO_SHA:
        return EXIT_LOGIC, _missing_sha_message(base, head)

    changed = changed_from_git(repo_root, base, head)
    # `select_tests`'s own callers (run_pytest_selected.py) treat a None diff
    # as "run everything", which is fail-closed FOR THEM: an unreadable range
    # falls back to the full suite, so nothing is skipped. A verifier's job is
    # the opposite: it exists to confirm a skip is safe, not to compensate for
    # an unreadable one by running more tests itself. It has no test run to
    # widen, so "cannot verify" must be REFUSED, never silently treated as
    # "safe to skip". Do not collapse this branch into the other caller's
    # fallback; that would readmit the exact fail-open this script exists to
    # close.
    if changed is None:
        return EXIT_LOGIC, _unreadable_diff_message(base, head)

    patterns = path_policy.load_patterns()
    matched = [
        (rel, glob)
        for rel in changed
        if (glob := path_policy.matched_pattern(rel, patterns)) is not None
    ]
    if matched:
        return EXIT_LOGIC, _matches_message(matched)

    return EXIT_OK, f"OK: 0 policy matches in {len(changed)} changed files"


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        default=str(Path.cwd()),
        help="Repository root to diff and load the path policy from (default: cwd).",
    )
    parser.add_argument("--base", required=True, help="Base SHA the skip claim compares against.")
    parser.add_argument("--head", required=True, help="Head SHA the skip claim compares against.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    repo_root = Path(args.repo_root)
    try:
        exit_code, message = verify(repo_root, args.base, args.head)
    except ValueError as exc:
        print(f"CONFIG ERROR: could not load the python path policy: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    print(message)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
