# Skill: Fix integrity gate noise with a STALE class, not an exemption (90%)

## Statement

In `scripts/ci/verify_dispatch_closure.py`, a noisy integrity gate tempts the fix "exempt what the PR did not change" by comparing to the merge base. That fails open. A stale-but-unchanged verifier still differs from trusted main, and a silent exemption hides that mismatch.

Add a visible STALE outcome instead. It is listed per file with a count, so the mismatch is never hidden, but it does not fail the check: a PR cannot be required to sit on the latest main (user decision, 2026-10-24). Every other category still exits 1. Commit 070e4017e (PR #6488, 2026-10-13) first made STALE fail.

## Evidence

- Issue #6415 (closed). PR #6418 merged the skip-untouched-files approach. PR #6488 (2026-10-13) added STALE as a failing class.
- `verify_dispatch_closure.py`: the `_differs` helper, the removed-root check, and `_unchanged_symlinks`.
- The pre-push security review caught the fail-open before it shipped.
