# The dispositions registry is trusted only where the trusted-ref check runs

`.agents/pr-checks/dispositions.json` can make a failing non-required check
stop blocking a merge. Exactly one caller may read it, and the difference
between the two callers is not a style choice.

## The two callers

**The completion gate may read it.** `run_completion_gate.py` byte-compares
every tracked file its criteria name against the trusted ref before running
any of them, so a PR that edits the registry halts the gate at exit 2 instead
of being believed by it. `pr-review-config.yaml` therefore passes
`--dispositions-file` and that is correct.

**The pr-autofix tier probe must not.** The two `test_pr_merge_ready.py`
invocations in `.claude/commands/pr-autofix.md` run against the checked-out PR
branch with no comparison of any kind. Their verdict flows into
`TIER_TRUSTED_T1`, and the block immediately below it disarms an already-armed
native auto-merge only when `TIER_TRUSTED_T1` is not `yes`.

So passing the flag there is a merge bypass: a PR adds an entry disposing its
own failing security check, scoped to its own number with a future expiry,
classifies as T1, skips the disarm, and GitHub merges it red. The gate's later
halt does not unmerge anything. CWE-829 and CWE-284.

## Why this is written down

PR #5481 shipped that bypass and caught it one review round later. The path in
is the part worth remembering, because it looks like diligence:

1. A reviewer observed, correctly, that the registry was inert for pr-autofix
   tiering, since `_load_dispositions(None)` returns `{}`.
2. The fix added `--dispositions-file` to both tier probes.
3. A test was written to pin it, `TestShippedCallersPassTheRegistry`, whose
   invariant was "every shipped caller passes the flag".

Step 3 is the tell. The invariant was a headcount, not a boundary, so it made
the vulnerable state the thing being enforced. The replacement,
`TestDispositionRegistryWiring` in `tests/test_test_pr_merge_ready.py`, states
the boundary in both directions: a `completion_criteria` command must pass the
flag, and no invocation anywhere under the shipped roots may otherwise carry
it. Both halves discover their inputs, because a hard-coded file list cannot
fail on the call site nobody added to it.

`tests/commands/test_pr_autofix_bot_tier_forwarding.py` asserts the exact argv
of both probes, so the absence of the flag is pinned at runtime too.

## If you are here to make tiering honor the registry

That is a real gap and the revert did not close it: #5433, #5460, and #5466
still classify as T2 or T5 on a failure the registry disposes. The fix is to
load the registry from the base ref rather than the checkout, which is not PR
content. Do not reach for the flag instead. Read the comments at both call
sites first; they say this.
