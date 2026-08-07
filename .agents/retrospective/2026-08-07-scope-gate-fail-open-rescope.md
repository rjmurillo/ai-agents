# Scope Gate Rescope Shipped Three Fail-Open Paths

Date: 2026-08-07
Failure mode: [10. Silent defaults and guard-clause suppression](../governance/FAILURE-MODES.md#10-silent-defaults-and-guard-clause-suppression)
Severity: High

## Summary

`scripts/detect_scope_explosion.py` blocks a push when a change touches more
than 50 files. It measured every branch against `main`, so a stacked PR counted
its parent's files as its own and got blocked for work it did not contain.

Commit `bd37bddd9` fixed that by re-measuring against the real PR base. The fix
worked on the happy path. It also opened three ways for the gate to pass a
change it should have blocked, and none of the three printed anything.

The gate can only ever remove a block. That makes every uncertain case a
security-relevant decision, and all three uncertain cases resolved the wrong
way.

## Impact

| Area | Severity | Effect |
| --- | --- | --- |
| Push gate correctness | High | A 52 file change could pass as 0 files with no output |
| Reviewer trust | Medium | The gate reports a number that may describe a different comparison than the one it names |
| Blast radius | Low | Caught before the branch was pushed; never ran in CI or on another contributor's machine |

## Timeline

1. `bd37bddd9` landed the rescope with 77 passing tests. Every test was mocked.
2. An adversarial review on a different model family (GPT 5.6 Sol) returned
   INCORRECT with four findings.
3. Each finding was checked against source or against a live command before
   any of it was accepted. Three of four reproduced. The fourth was real but
   Low, and was left open on purpose.
4. `8fcfbe557` fixed all three. `9c0771fe7` split the new code into
   `scripts/scope_pr_base.py` after the additions tripped the file size ratchet.

## Root cause

Five whys:

1. Why did the gate pass a 52 file change? Because the second `detect_scope`
   call returned `file_count=0` and the rescope accepted it.
2. Why did it return 0? Because `get_index_files_against_ref` returns `[]` on
   any nonzero `git diff`, and `detect_scope` wraps `[]` into a
   `ScopeResult(file_count=0)` rather than `None`.
3. Why did the rescope accept that? Because it guarded `is None` only. A
   failed diff and a genuinely empty diff are indistinguishable at that call
   site.
4. Why was the guard written that way? Because the new code trusted a helper
   whose failure signature was never read. The helper's contract was assumed
   from its name.
5. Why did 77 tests miss it? Because every test mocked `detect_scope` and
   returned the value the test wanted. No test asked what the real helper does
   when git fails.

Root cause: **new code inherited an existing silent default without reading the
helper it called, and a fully mocked test suite could not surface it.** The
tests proved the new code did what its author intended. They could not prove
the helper does what its author assumed.

## The three paths

1. **Wrong PR.** The lookup used `gh pr view <branch>`, which is not restricted
   to open PRs. Verified against gh 2.97.0: a branch whose PR had merged
   returned that PR with `state=MERGED`. A reused branch would rescope against
   a dead PR's base.
2. **A failed diff read as a clean pass.** Described above.
3. **Comparison mode switch during a merge.** `is_ancestor(MERGE_HEAD, base)`
   picks between two comparison modes and takes the base as input. A second
   call with a different base can compare differently than the first, so the
   two numbers are not comparable.

## Remediation

| Action | State | Evidence |
| --- | --- | --- |
| Query only open PRs, accept the answer only when exactly one matches | Done | `scripts/scope_pr_base.py`, `resolve_pr_base_branch` |
| Refuse a rescope whose result is empty or `None` | Done | `scripts/scope_pr_base.py`, `is_credible_rescope` |
| Skip rescoping entirely while `MERGE_HEAD` exists | Done | `scripts/detect_scope_explosion.py`, `rescope_against_pr_base` |
| Add a subset invariant as defense in depth | Reverted, it was false | Disproved on a constructed repository; replaced with a fork-point ancestry test in `is_credible_rescope` |
| Validate `baseRefName` before it reaches a ref | Done | `scripts/scope_pr_base.py`, `_is_plain_branch_name`; rejects a non-string, `HEAD`, `..`, and option-shaped names |
| Resolve the PR against the branch that was measured, not a fresh read | Done | `rescope_against_pr_base` uses `blocked.current_branch` |
| Cover each path with a test plus a mutation control | Done | 146 tests; six mutation controls, each failing its targeted test |
| No upstream head fallback for detached or unpushed branches | Open by choice | `checks_common.py` has one (issue #4382, closed 2026-08-04); not reused here because it would widen a lookup that can only remove a block |

## Learnings

1. **A helper that returns an empty collection on failure is a fail-open
   waiting for a second caller.** The original call site handled it. The new one
   did not, because the signature does not say so. Read the failure branch of
   any helper before trusting its return value.
2. **A fully mocked suite tests the author's model of the system, not the
   system.** Passing tests are evidence about intent. They are not evidence
   about the helper the code calls.
3. **Adversarial review on a different model family found what the author and
   the tests both missed.** Verify each finding against source before accepting
   it, and equally, do not dismiss one because the reviewer was wrong elsewhere.
   Three of four reproduced exactly.
4. **When a fix can only ever remove a guard, every uncertain case must keep
   the guard.** State that as an invariant in the code, not as a habit.
5. **A claim about a graph cannot be tested with a mock.** The subset invariant
   was reasoned, not measured: a stacked surface "must" be contained in the
   main-relative surface because the stack base is downstream of main. It is
   false. A child that reverts a file its parent changed differs from its parent
   on exactly that file and agrees with main about it, so the file is absent
   from the main-relative set. Containment therefore rejected the honest
   one-file stacked PR that this whole path exists to unblock. The claim
   survived one adversarial review and 88 passing tests, because every one of
   those tests supplied the file sets from the same belief that produced the
   rule. A ten-line real repository refuted it in seconds. Build the graph.
6. **A test that fails and a test that cannot run look identical from the
   assertion.** The first draft of the real-git tests did not `chdir`, so the
   production `is_ancestor` ran `git merge-base` in the wrong repository, exited
   128, and returned False for every input. All three reject cases passed
   vacuously while the accept cases failed. Any suite whose subject returns a
   single value on both "no" and "cannot tell" needs an explicit positive
   control asserting the subject can see its inputs at all.

## References

- Commits: `bd37bddd9` (original fix), `8fcfbe557` (hardening), `9c0771fe7`
  (module split)
- `scripts/validation/checks_common.py` upstream-head fallback (issue #4382)
- `.agents/governance/FAILURE-MODES.md` section 10
