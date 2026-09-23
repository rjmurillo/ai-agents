# PR #4718: two review findings that every cheap probe missed

## Summary

An adversarial reviewer opened two threads on PR #4718. Both were real, both
were reproducible against real git 2.43.0, and both had the same shape: a guard
that reads the obvious signal, and a real state where the obvious signal is
silent. Fixing them exposed a third problem, a taste count ratchet regression
that only became visible after merging current `main`.

## Failure mode classification

Pattern 10, silent defaults and guard-clause suppression
(`.agents/governance/FAILURE-MODES.md`). Both findings are cases where a probe
answered "nothing here" for a state it could not read, and the answer was
indistinguishable from a genuine all-clear.

The rescue-chain finding also touches pattern 11, a generated artifact shipped
without runtime verification: the tool printed a recovery command that had never
been run in the shape it printed for four or more orphans.

## Impact

| Area | Severity | What was at risk |
|---|---|---|
| Worktree GC removal path | High | A commit an in-flight `refs/worktree/*` write was about to anchor, removed with the admin directory, exit 0 and silent |
| Printed recovery command | High | With four or more orphans, the copied chain failed in the shell before creating a single rescue branch |
| Merge readiness | Medium | The branch tripped the taste count ratchet only after merging `main`, so the branch looked clean until the last gate |

## Evidence

- PR #4718, threads `PRRT_kwDOQoWRls6X7gq0` and `PRRT_kwDOQoWRls6X9283`.
- Ref lock, measured with `refs/worktree/installing.lock` held: the probe
  answered `None`, `worktree_ref_oids` answered `[]`, and `git worktree remove`
  exited 0, printed nothing, and deleted the worktree.
- Rescue chain, measured with seven orphans: the copied slice ended in prose
  and `bash -c` exited 2 with ``syntax error near unexpected token `('``.
- Fix commits `6771e31616`, `cb15548e3a`, and `d1b04dd837` on
  `fix/gc-worktrees-stale-entries`.

## Root cause

**Finding 1.** The operation probe held a flat list of marker names read from
the top of the admin directory. Per-worktree refs live one level down, under
`refs/`, and git's files backend derives a lock name from the ref's own path, so
no flat list can name them. The anchor reader that does walk `refs/` skips a
file holding no text, and a ref lock is empty for the whole of a delete
transaction. Two probes, each correct about its own question, and the state fell
between them.

**Finding 2.** The reason string is read by two consumers with different rules:
a shell, which stops at the end of the line, and a human, who stops at the
prose. The staged-work rescue already separated the two with `" | "`. The admin
rescue did not, so the prose about the commits still at risk was appended to the
command that would have rescued the first three.

**Ratchet regression.** The count ratchet compares a whole-tree violation count
against a baseline that `main` moves. The branch carried one file-size violation
`main` does not have. While the branch was fifteen commits behind, the tree's
total stayed one under the baseline and the violation was invisible. Merging
`main` surfaced it as a regression that looked self-inflicted by the merge.

## Remediation

1. Done: `in_progress_operation` now walks the admin `refs` tree for any lock
   file at any depth, and answers "unknown, so an operation may be in progress"
   when the walk cannot be trusted. Five real-git tests cover it, including one
   that drives a prepared `git update-ref --stdin` transaction so git writes the
   lock rather than the test.
2. Done: the orphan count moved behind the `" | "` delimiter, with a real-git
   test that runs the copied slice in `bash` from outside any repository and
   asserts three rescue branches appear.
3. Done: `tests/test_gc_worktrees_real_git_stale.py` split along its own seam
   into a stale-diagnostics suite and a rescue-command suite, 463 and 234 lines,
   which returned the count to the 583 baseline without raising it.
4. Standing practice, already in `.claude/rules/ci-scripts.md` item 14: merge
   `origin/main` and re-measure before reading a count ratchet. This run is one
   more datum that the ratchet's verdict on a stale branch is not evidence of
   anything.

## What generalizes

A probe that cannot distinguish "absent" from "unreadable" is a silent
all-clear. This module already made that distinction everywhere else, using
`lstat` over `exists` and three-valued returns. Finding 1 was not a missing
principle, it was a principle applied to the wrong directory depth.

A printed command is an artifact with a runtime, and the only test that proves
it works is running it. Both rescue commands in this module now have one.
