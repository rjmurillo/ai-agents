# Retrospective: squash-severed stack and silent reflog defaults

## Session Info

- **Date**: 2026-08-06
- **Agents**: Copilot (Opus 5), Gemini 3.1 Pro, Grok 4.5, GPT-5.6 Sol, GPT-5.5
- **Task Type**: Bug
- **Outcome**: Success with rework

## Phase 0: Data Gathering

Observed: work on `scripts/maintenance/gc_worktrees.py` grew past the push
ceiling, split into PR #4718 and a follow-on branch, and then lost its base
when PR #4708 squash-merged underneath it.

Glad: nine loss channels closed in the worktree garbage collector, four model
families used for adversarial review, 23857 tests passing at `7e3590b9e`.

Mad: two High defects reached a commit that 262 passing tests did not catch.

Sad: a delegated agent destroyed committed work in a shared worktree.

## Impact

| Area | Severity | Effect |
|------|----------|--------|
| Committed work in a scratch worktree | High | Destroyed by a delegated agent, recovered from a bundle and the reflog |
| Reflog anchor reading | High | A garbage line and a vanished file both read as an all-clear |
| Stacked PR #4718 | Medium | Base severed by a squash merge, 17 conflicts, one wasted push cycle |
| Push ceiling | Low | Repair merge tripped a limit that the deleted parent branch made unreachable |

## Phase 1: Insights Generated

### Failure 1: delegated agent destroyed committed work

Classification: failure mode 7, self-contained agent delegation failure
(`.agents/governance/FAILURE-MODES.md`).

Five whys:

1. Committed work disappeared from a scratch worktree.
2. A delegated review agent ran `git reset --hard` and `git clean`.
3. The agent was dispatched into the worktree that held the work in progress.
4. The delegation prompt described the review task and not the boundary.
5. The prompt template assumed a read-only agent would stay read-only, so no
   prompt stated the constraint and no backup ref existed to fall back on.

The recovery worked because a bundle happened to exist. That is luck, not a
control.

Corrections applied during the session, and held for every later dispatch:

- Every review agent got its own detached worktree.
- Every prompt named the forbidden commands explicitly rather than implying
  read-only intent.
- A backup ref was bundled before dispatch.

### Failure 2: two High defects in the reflog reader

Classification: failure mode 10, silent defaults and guard-clause suppression.

`_collect_reflog_oids` judged an entire reflog by its first line, so a file
whose first line parsed returned object ids while the rest was ignored.
`_reflog_text` returned an empty string for an absent file, which the caller
could not tell apart from a file that held nothing. Both turn missing
information into an all-clear, which is the exact shape the module exists to
prevent.

Five whys:

1. Two High findings survived to a commit.
2. The 262 tests in the suite did not fail on either.
3. Every test used a mock filesystem or a synthetic reflog with clean content.
4. No test made the filesystem genuinely fail, and none fed mixed valid and
   invalid content.
5. Mock-based tests reproduce the author's model of the world, so they agree
   with the code by construction.

This is the tenth time in this work that mock-based tests passed while real git
exposed a real defect. The reverse has not happened once.

The revert-proof is what turned the new tests from an assertion into evidence:
reverting the per-line fix fails three tests, reverting the vanished-file fix
fails one. Restored, thirty-one pass.

### Failure 3: a squash merge severed the stack

Classification: failure mode 9, confident-incorrectness recurrence.

`git log --oneline -3 origin/fix/worktree-walk-timeouts` shows
`fix(maintenance): ... (#4708)` at the tip, which reads as though the stack is
intact. It is not. A squash writes a new commit with no parent link, so
`git merge-base --is-ancestor` answers no, GitHub retargets the child PR on its
own, and the merge base collapses to a commit that predates the files. Git then
reports `add/add` conflicts on files both branches plainly have.

The readable signal and the authoritative check disagreed, and the readable one
was checked first.

## Phase 2: Remediation

| Action | Artifact | Status |
|--------|----------|--------|
| Record the squash-severs-a-stack quirk with the `merge-base --is-ancestor` check and the `-s ours` repair | `.serena/memories/git/git-a-squash-merge-severs-a-stacked-pr.md`, indexed in `skills-git-index.md` | Done in this branch |
| Nine regression tests for the reflog reader, including a real-git guard against over-tightening | `tests/test_gc_anchor_readers.py` | Done, PR #4718 follow-on |
| Fix both silent defaults so absence and garbage return `None` | `scripts/maintenance/_gc_anchors.py` | Done, commit `7e3590b9e` |
| State forbidden git commands in every delegation prompt and give each agent its own worktree | Session practice, applied to all later dispatches | Done |

## Phase 3: Learning Capture

Keep: adversarial review across model families with a mandatory two-direction
negative control. Gemini killed six hypotheses on real controls and Grok killed
eight, which is the same value as a confirmed finding at a fraction of the
rework. Keep the revert-proof as the test of a test.

Drop: trusting a mock-based suite as evidence that a filesystem reader is
correct. Make the filesystem actually fail.

Add: check ancestry with `git merge-base --is-ancestor` before reading any
stacked-PR conflict, and read an `add/add` conflict on a shared file as a
collapsed merge base rather than a content disagreement.

## Evidence

- PR #4718, the lower half of the split, and its `commit-limit-bypass` comment
  recording the measured commit counts.
- PR #4708, the squash merge that severed the stack.
- PR #4694, the base of the chain.
- Commit `7e3590b9e`, the two High fixes and their nine regression tests.
- Commit `cbed7c48f`, the repair merge, whose message records the verification
  that the result differs from the base on exactly the 31 files the branch owns.
- Issue #2761, the worktree accumulation the module exists to address.
