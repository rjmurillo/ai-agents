# Retrospective: Issue #4746 (a conflicted path counted once per merge stage)

## Session Info

- **Date**: 2026-09-01
- **Agent**: Claude Code (remote session, implementer)
- **Task Type**: Bug fix (CI gate correctness), P2 backlog
- **Outcome**: Fix, tests, and negative control shipped on the PR that closes
  issue #4746

## What shipped

`git ls-files` prints one line per index entry, and an unmerged path holds one
entry per merge stage. `count_ratchet.tracked_files` returned that raw list, so
all six ratchets under `scripts/ci` were handed the same conflicted path two or
three times. Five of them counted its violations that many times. The
memory-index ratchet did not, because its `_tracked_relative_paths` builds a set
and the repeats collapsed before anything counted them. The reporter saw
`585 violations > baseline 583 (+2)` on a branch whose only conflicted file was
byte-identical to `origin/main`, and `git add` of unchanged content cleared it.

Fixing the shared enumeration still covers the immune consumer, because it reads
the index like the rest and so carries the mid-merge note. That note is a
reporting concern rather than a counting one, which is the distinction the
first draft of this record blurred.

`deduplicate_index_entries` keeps the first occurrence and the original order.
Repeats are reported on stderr rather than through a second git call, because a
duplicate index entry is what an unmerged path is.

## What worked

- **Reproducing before designing.** A scratch repository with a 601-line file
  conflicted content-versus-content measured 4 violations mid-merge against 2
  after staging byte-identical content. The `+2` matched the issue exactly, and
  the decomposition (1 for the linter's own copy, 3 for the conflicted file)
  confirmed the mechanism rather than inferring it from the symptom.
- **Pinning the git behavior, not only the fix.** A separate case asserts
  `git ls-files -z` really does repeat an unmerged path three times. Without it
  a future git that stopped repeating would leave the deduplication passing its
  own tests while guarding nothing.
- **Answering the issue's open question by measurement.** It asked whether the
  sibling ratchets share the enumeration. All six do, so one seam fix covers
  all six, and a per-consumer test now fails if one stops sharing it.
- **The negative control found the real blast radius.** Restoring the defect
  failed exactly three cases (`assert 3 == 1`, `assert 2 == 1`, `assert 4 == 2`)
  and left the seventeen order, cap, and wiring cases green, which is the
  evidence that those seventeen are not the ones doing the work.

## What failed, and the correction

- **The main checkout was behind `origin/main` by a wide margin.** The first
  read of `count_ratchet.py` returned a 541-line file; the worktree cut from a
  freshly fetched `origin/main` holds 1019 lines, with an exit-code contract and
  a `--base-ref` policy the older copy never mentions. The edit landed correctly
  only because `tracked_files` happened not to have moved. Correction: read the
  file from the worktree you are about to change, not from whichever checkout is
  open. This is the same staleness trap `.claude/rules/ci-scripts.md` MUST 14
  records for ratchet counts, arriving through a different door.
- **The mid-merge inflation is not a fixed multiple.** The reported case had
  three stages, but add/add and delete/modify carry two, so dividing by three
  would have been wrong on half the conflict shapes. Deduplication is
  shape-independent; a two-stage case pins it.

## Failure mode classification

**Failure mode 10, silent defaults and guard-clause suppression**
(`.agents/governance/FAILURE-MODES.md`). That entry's unifying property, quoted
verbatim: "the call site has no way to know the operation didn't actually do
what its name claims." The enumeration claims paths and returned index entries,
all six call sites consumed the difference as though it were paths, and the
verdict that came out was internally consistent with the file list printed
beneath it. The reporter could not tell from the output that the index was the
cause, which is the whole of that mode. It fires exactly when someone is
mid-merge and least able to tell an artifact from a regression.

The shape is inverted from that entry's canonical examples, and worth naming so
the next reader is not misled: those describe a check falling through to a
positive signal, while this one falls through to a false RED. The suppression is
the same either way, because a verdict nobody can place is what both produce.
The remedy the entry asks for is the one taken here, which is to surface the
suppression rather than only correct the number.

**Not failure mode 9** (confident-incorrectness recurrence), which the symptom
superficially resembles. That entry describes "an agent reaches a conclusion
from partial signal, delivers it with full confidence." No agent asserted this
count. The gate computed it from a mis-measured input, so the defect is in the
measurement, not in a claim anyone made about it.

**Not failure mode 4** (false completion markers), whose direction is opposite:
success reported against an artifact that does not satisfy the criteria. This
gate reported failure against a tree that did.

## Remediation

Every action below is a code change, and all of them landed in PR #5454 against
issue #4746. Owner: the PR author (`@rjmurillo`, agent-assisted). Nothing here
is deferred, so no follow-up issue is open against this record.

| # | Action | Owner | Tracking | Status |
|---|--------|-------|----------|--------|
| 1 | Deduplicate at the shared seam, covering all six ratchets at once | `@rjmurillo` | PR #5454, issue #4746 | DONE |
| 2 | Emit a stderr note naming the unmerged paths, capped at five | `@rjmurillo` | PR #5454, issue #4746 | DONE |
| 3 | Pin git's per-stage enumeration so a future git that stops repeating cannot leave the fix guarding nothing | `@rjmurillo` | PR #5454, issue #4746 | DONE |
| 4 | Drive each of the six consumers' real `current_count` through a spy, so one leaving the shared enumeration fails | `@rjmurillo` | PR #5454, issue #4746 | DONE |
| 5 | Suppress the note on the run's second index read, so one run prints one caveat | `@rjmurillo` | PR #5454, issue #4746 | DONE |
| 6 | Narrow the impact claim to the five ratchets that actually double-counted | `@rjmurillo` | PR #5454, issue #4746 | DONE |
| 7 | Announce once for the two-scope consumer, whose reads are both counting reads | `@rjmurillo` | PR #5454, issue #4746 | DONE |
| 8 | Assert exact per-consumer read counts, so dropping one of several scopes fails | `@rjmurillo` | PR #5454, issue #4746 | DONE |

On action 2: the count is right after the fix, and the note still earns its
place, because the linter reads content off disk, so conflict markers left in
the working copy add lines and can push a file over a size threshold on their
own. A count taken mid-merge deserves the caveat. The five-path cap exists
because a two-hundred-file conflict printed above a 40-line violation cap buries
the payload.

On action 4: this replaced a weaker first attempt. See the correction below.

## Learnings

- A git plumbing command's unit of output is worth checking before it is
  consumed as a set. `ls-files` enumerates index entries, not paths, and the two
  differ only in a state most sessions never reach.
- When a gate reports a number, the honest failure is one that says which tree
  it measured. Correcting the count and dropping the mid-merge note would have
  left a second, smaller version of the same defect: a number nobody can place.
- A shared helper makes the mirror obligation cheap to discharge and easy to
  over-claim. The first wiring test asserted each consumer still held the
  imported reference, which proves an import survived and not that anything
  calls it. See the correction below.

## Correction, 2026-09-01, review round 1

Appended rather than rewritten, per this repository's rule that a landed retro
is corrected by addition.

Review found the wiring claim above unsupported by the test that was supposed to
carry it. The original test asserted `module.tracked_files is
count_ratchet.tracked_files` for each of the six consumers. That is an
identity check on an imported name: a consumer can stop calling the enumeration,
keep the now-unused import, and pass.

Measured rather than argued. One consumer was rewritten to walk the filesystem
with `rglob` instead of calling the shared enumeration, with the import left in
place. Under that mutation the identity assertion evaluated `True`, so the
original test would have shipped green against exactly the regression it was
written to catch. The replacement, which drives each consumer's real
`current_count` with the enumeration monkeypatched to a spy, failed both of that
consumer's cases on the same mutation. Restoring the consumer was confirmed
byte-identical and returned all 26 cases to green.

Second and third findings, both real and both against
`.claude/rules/retros.md`: MUST 2 requires a retro to classify its failure
against a numbered entry in `.agents/governance/FAILURE-MODES.md`, and MUST 4
requires remediation actions to carry owners or issues. The original record had
a prose description in place of the classification and a bare bullet list in
place of the remediation table. Both are now supplied above.

The through-line across all three: each was a claim stated in the right shape
without the thing that makes the shape load-bearing. That is the same defect
class as the bug this PR fixes, one level up.

## Correction, 2026-09-01, review round 2

Three more findings, all real, all confirmed by reading the cited source before
acting.

**A duplicate note, which is the fix reproducing the defect it fixes.** On a
regression `run` reads the index twice: once through the counter, then again
through the lister that renders the violations. Both reads saw the same unmerged
index, so both emitted the identical caveat and a contributor mid-merge read it
twice for one run. The note exists to make a mid-merge count legible, and
printing it twice makes the output harder to read, not easier. Fixed by giving
the enumeration an `announce_unmerged` keyword that the counting read leaves
true and both listers pass false: the counting read runs on every invocation, so
it owns the announcement, and the diagnostic re-read stays silent because the
count already said it. `memory_index_count_ratchet` needed the keyword threaded
two frames down, through `_collect` and `_tracked_relative_paths`.

Negative control: restoring both call sites to the announcing form failed three
cases, the end-to-end once-only assertion and one lister case per module, with
28 passing. Both restores were confirmed byte-identical and returned all 31 to
green. The end-to-end case drives `main` rather than the helpers, because the
double emission only exists in the sequence `run` performs, and it asserts the
violations header so a future change that skips the lister entirely cannot make
it pass vacuously. A paired control asserts the counting read still announces,
because silencing both reads would leave a mid-merge run with no caveat at all,
which is this defect one step further on.

**An overstated impact claim, twice.** The first draft of this record and the
test module both said every ratchet counted the conflicted path two or three
times. Five did. `memory_index_count_ratchet._tracked_relative_paths` builds a
set, so the repeats collapsed there before anything counted them, and that
consumer was already immune to the counting symptom while still sharing the
enumeration. The PR description's scope analysis had this right from the start,
so the defect was an inconsistency between two documents in the same change,
where the narrower and correct claim was already written down.

The pattern worth keeping from this round: the strongest claim reachable is not
always the true one, and a claim already stated correctly somewhere else in the
same change is the cheapest place to catch that.

## Correction, 2026-09-01, review round 3

Two findings, both real, both consequences of the round 2 fix rather than of the
original defect.

**The round 2 fix left one consumer behind.** It assigned the announcement to
"the counting read", on the assumption that each ratchet has exactly one.
`cli_exit_contract_ratchet` has two: it counts from `scripts/ci/*.py` and
`.github/scripts/*.py` in one read and `tests/**/*.py` in another, disjoint
scopes that can each legitimately hold an unmerged path. Both defaulted to
announcing, so a merge conflicting a file in each scope printed one note per
scope for a single run. That is the duplicate output round 2 removed,
reintroduced at a shape the round 2 rule did not describe.

Silencing the second read would have been wrong in the other direction: a
conflict confined to `tests/` would then announce nothing at all, which is worse
than announcing twice. The fix reads the union of both pathspecs first, gives
that read the announcement, and silences both scoped reads. One run, one caveat,
naming every unmerged path either scope would have counted. The union read also
serves as the git-health probe for the pair, so its None short-circuits before
either scoped read runs.

Negative control: reverting to two independent announcing reads, against a
fixture carrying a conflict in both scopes, failed on `one run printed the
mid-merge note 2 times`. Restore confirmed byte-identical.

**The wiring test's lower bound could not see a half-broken consumer.** It
asserted `spy.calls >= 1`, which any one surviving read satisfies, so a consumer
that dropped one of several scopes for a raw filesystem walk would still have
passed. The counts are now exact per consumer and per condition: one read when
the first enumeration is unusable, and for the two-scope consumer three when
every enumeration is readable.

Negative control, run in two halves against the same mutation. With the tests
scope switched to `rglob`, the exact assertion failed with
`made 2 enumeration read(s), expected 3`. Loosening that one assertion back to
`>= 1`, with the mutation still in place, passed 16 of 16. The lower bound
demonstrably could not see the defect.

Deviation from the review's suggested shape, recorded because it is visible in
the diff: the review asked for exactly two reads for this consumer, one per
glob. It makes three, because the union read that owns the announcement is a
third. The intent, catching a consumer that silently drops a read, is served
identically by an exact three.

The pattern across rounds 2 and 3: a rule that assigns a responsibility ("the
counting read announces") is only as good as its enumeration of the cases. This
one was written from five consumers that share a shape and applied to a sixth
that does not. Worth checking the odd one out before generalising, not after.
