# Skill: Root-cause bisection names the cause, never the remedy (90%)

**Atomicity Score**: 90%
**Source**: Retrospective `.agents/retrospective/2026-08-02-wrong-fix-before-search.md`
**Date**: 2026-08-02
**Validation Count**: 1 (PR #4302 closed unmerged)
**Tag**: helpful
**Impact**: 9/10 (this is the generator behind an entire class of confidently wrong fixes)

## Statement

A clean bisection tells you *which* change crossed a threshold. It tells you nothing about
*why* that code is shaped the way it is, or whether the threshold is the right measure. Treat
the end of diagnosis as the start of design, not the end of it.

## Context

Any time a bisection, `git blame`, or a failing gate hands you a single file and a single
number. The confidence from a clean diagnosis is the trap: it feels like it carries the answer
forward, and it does not.

## Evidence

2026-08-02. Bisection was correct: `scripts/validation/pre_pr_sequence.py` crossed the
taste-lint 500-line ceiling in PR #4272, breaking every push in the repo.

Two different remedies follow from that same correct diagnosis:

| Remedy | Reasoning |
|---|---|
| Extract 57 lines into a new module | The file is over the ceiling, so shorten the file |
| Convert 48 ordered `run_validation` calls into a table-driven registry | The file is a registration list; a length ceiling is the wrong measure for it |

The bisection cannot distinguish these. It measures the symptom's location, not the code's
nature. I picked the first, shipped it, and closed it unmerged when issue #4285 named the
second.

Three independent parties converged on "match main's suppression comment, do not extract":
PR #4290 (another agent), the `redo4003` agent resolving a merge conflict on the same file,
and issue #4285's author. I was the only one who extracted, and I was the only one who went
straight from bisection to design.

## The check

After a bisection completes, before writing any remedy, answer two questions in writing:

1. **What is this code, structurally?** A registration list, a state machine, a parser, a
   config block. Not "a long function."
2. **Is the metric that flagged it the right metric for that structure?** A length ceiling on a
   registration list measures how many features the project has, not its complexity.

If the answer to 2 is no, the remedy is to change the structure or suppress the metric with a
written rationale, never to game the counter.

## Related

- `.serena/memories/process/process-search-open-issues-before-designing-a-fix.md` is the cheap
  mechanical guard that catches this failure even when you skip the check above.
