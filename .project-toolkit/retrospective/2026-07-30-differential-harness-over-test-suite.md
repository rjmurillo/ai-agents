# A Passing Test Suite Missed Six Defects a Differential Harness Caught

Date: 2026-07-30
Failure mode: Class 9, confident-incorrectness recurrence
(`.agents/governance/FAILURE-MODES.md`). Secondary: Class 4, verification
theater, where a green suite is read as proof of no regression.

## Summary

A long-lived branch hardened the subprocess text-encoding guard in
`tests/test_subprocess_text_encoding.py` over roughly twenty rounds. The owner
closed that branch as superseded once two competing guard PRs merged to `main`.
The correct recovery was to port the branch's unique detections forward onto
current `main`, not to rebase or merge the divergent branch.

During that port, a differential harness (run the old guard and the new guard
over the same corpus of payloads and diff the flagged line sets) caught six
defects across three classes. Every one of them was invisible to a suite that
was passing at the time, including the tests written for the very change that
introduced the defect.

The suite went from 228 tests on `main` to 283 on the port. It was green at
every point where the harness found a problem.

## Impact

| Area | Severity | Effect |
|------|----------|--------|
| Detection correctness | High | Three real regressions were introduced by one 40-line change and caught only by the diff. All three would have silenced genuine detections on `main`. |
| False-positive rate | High | Two false positives were caught, one of them pre-existing on `main` and inherited by every consumer of that guard since it merged. |
| Base-branch selection | High | Measuring the abandoned branch against `main` showed it carried 8 false positives `main` does not have. Merging it would have shipped all 8. |
| Sequencing cost | Medium | One deferral (`operator.methodcaller`) was correct when made and trivial three commits later. Re-checking deferrals after adjacent work lands is nearly free. |
| Complexity | Positive | `_resolve_indirect` fell from 15 to 10 while gaining five capability families, because each family reused the extraction the previous one forced. |

## Timeline

1. The branch `feat/guard-multi-hop-detection` was closed by the owner as
   superseded (PR #3835). Two guard PRs, #3826 and #3894, had already merged to
   `main`.
2. Rather than assume the closed branch was the better base, both guards were
   snapshotted and run over the same 489-payload corpus. The closed branch
   flagged 27 shapes `main` did not. Tracing those 27 by hand found 8 were
   **false positives** the branch had introduced, not detections `main` was
   missing. That measurement, not the owner's authority, is what settled the
   base-branch question.
3. A fresh branch off current `main` ported five detection families forward,
   one commit each, tests first in every case.
4. Family F4 (mutating a `functools.partial`'s keyword mapping to undo a codec
   pin) passed its own 5 tests. The differential harness immediately flagged
   `runner.keywords.get('encoding')` as newly detected. The rule "any mention of
   `.keywords` voids the pin" had swept in **read-only** access. Fixed by adding
   a parent map and a `_reads_only` predicate. 3 new quiet tests.
5. The same diff surfaced a payload where `main` flagged a `partial` whose
   construction site pinned `encoding='utf-8'`. A two-module probe confirmed the
   codec is pinned at runtime. **That was `main`'s bug, inherited, not the
   port's.** Fixed with `_prepinned`, the exact mirror of the existing
   `_presupplied`.
6. `_prepinned` passed its own 4 tests. The differential harness caught **three
   real regressions it had introduced**: a call site naming `encoding="latin-1"`
   (which wins at runtime), a call site splatting `**overrides` (which may carry
   `encoding`), and `alias = runner; alias.keywords['encoding'] = None` (an alias
   shares the mapping, so a node-id-keyed void set misses it). All three were
   written as failing tests, then fixed.
7. `operator.methodcaller` had been deferred earlier as expensive: it needs
   keywords from a node other than the call site. After the operator-getter
   machinery landed for family F1, the same deferral cost one word in a table
   plus a nine-line helper. The deferral was correct when made and wrong three
   commits later.

## What Went Wrong

- Reading a green suite as proof that a behavioral change introduced no
  regression. It is proof that the change satisfies the assertions someone
  thought to write, which is a strictly smaller claim.
- Writing the void rule for `.keywords` as "any mention" without asking what a
  read looks like. The tests written for that change all used writes.
- Assuming a closed branch was the better base because it had more rounds of
  work in it. Round count is not detection quality. It had 8 false positives.
- Treating a deferral as permanent. The cost estimate that justified it was
  accurate against the code as it stood, and stale two commits later.

## What Went Right

- Snapshotting both guards to separate files and diffing their flagged line sets
  over a shared corpus. Cheap to build, and it earned its keep six times.
- Running the diff **against `main`** and not only against the abandoned branch.
  The vs-`main` direction is the important one: entries there are behaviors the
  port **removed**, each of which must be justified as a false positive or it is
  a lost detection.
- Writing every fix as a failing test first, and confirming the red matched
  exactly the intended cases before implementing.
- Extracting shared helpers as each family arrived rather than after. That is
  why complexity fell while capability grew.

## Remediation

| Action | Owner | Tracking |
|--------|-------|----------|
| Port five detection families plus `methodcaller` onto current `main` | shipped | this branch, Refs #3422 |
| Fix `main`'s construction-site codec-pin false positive | shipped | commit `8ce470bfd` |
| Record that the abandoned branch carried 8 false positives | this document | see Timeline item 2 |
| Decide the `capture_output=False` conservatism policy | open | see Follow-Ups |
| 162 test-tree calls need a codec pinned | open | issue #3925 |
| Widen the guard's scan root beyond `scripts/` | open | issue #3927 |

## Follow-Ups Not Yet Filed

1. The differential-harness pattern is not encoded anywhere. It is three small
   scripts in `/tmp` that any future guard author will rebuild from scratch.
   Worth a skill or a checked-in tool: snapshot two versions of a scanner, run
   both over a corpus, diff the flagged sets, and require every removed
   detection to be justified.
2. `capture_output=False` at a call site that overrides a `partial`'s
   `capture_output=True`. `main` flags it. Runtime proof shows `stdout` is
   `None`, so nothing is decoded and the flag is a false positive. This is a
   conservatism **policy** call, not a bug, and belongs to the owner.
3. No CI gate runs a differential diff on guard changes. A guard PR can silently
   remove detections and stay green. The corpus exists; the comparison does not.

## Learning

A test suite answers "did the behaviors I thought of still work." A differential
harness answers "what behaviors changed," including the ones nobody thought of.
Those are different questions, and only the second one catches a regression in a
scanner, because a scanner's output is a set and a suite only ever samples it.

The cost of the harness was under an hour. It caught three regressions in one
40-line change, two false positives (one inherited from `main`), and settled a
base-branch decision that would otherwise have been made on authority or on
round count. Both of those would have been wrong.

The transferable rule: when a change alters what a scanner flags, diff the
flagged sets before and after over a real corpus, and read the **removals** as
carefully as the additions. A removal is either a false positive you fixed or a
detection you lost, and the test suite cannot tell you which.
