# Skill: Fix integrity gate noise with a STALE class, not an exemption (90%)

## Statement

EUREKA. A noisy integrity gate tempts the fix "exempt what the PR did not change" by comparing to the merge base. That fails open. A stale-but-unchanged verifier still differs from trusted main, so the exemption hides a real mismatch.

Add a new STALE outcome instead. It still exits 1 and tells the author to merge the base ref. The gate stays closed and the noise gets an actionable message.

## Evidence

- PR #6415, `verify_dispatch_closure.py`: the `_differs` helper, the removed-root check, and `_unchanged_symlinks`.
- The pre-push security review caught the fail-open before it shipped.
