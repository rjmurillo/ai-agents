# Calibrate a guard on the whole corpus, never on a sample of its own hits

## Question

A new validation guard fires on N files. How many do you inspect before you
trust the guard's precision?

## Conventional answer

Inspect a handful. If the first few hits are all genuine, the guard is well
targeted; ship it and let review catch the rest.

## First-principles position

That procedure cannot detect a false-positive rate, because the sample is drawn
from the guard's own output and read by the person who wants it to work. The
only honest measurement runs the *candidate rule* and the *narrower rule* across
the full corpus and compares the delta. If the narrower rule keeps almost every
catch, the wider rule was mostly wrong.

## Evidence

Issue #3383, session log contamination. First rule: flag any *second* feature
branch named in `branchVerified` / `notOnMain` evidence. Inspected four hits,
all genuine, wrote "0 false positives on inspection" in a commit message.

Running the full 946-log corpus told a different story. Seven hits, and six were
honest evidence describing a relationship:

```
"feat/1746-autonomous (renamed from feat/1774-autonomous ...)"
"On chore/3196-branch-context-lefthook, stacked on origin/chore/lefthook-migration"
"Branched from feat/1769-autonomous"
"On branch fix/branch-cleanup, then created chore/recover-orphaned-artifacts"
```

An 86 percent false-positive rate. The seventh hit was real contamination.

The tell arrived before the measurement and was ignored for one step: the guard
flagged the session log of the very branch introducing it, because that branch
was stacked on #3385.

## Decision

Narrowed to: flag only when the evidence names feature branches and *none* of
them is the declared branch. Contamination describes the other session and never
mentions this one. That made the branch check symmetric with the
starting-commit check next to it, which already used the none-matches shape.

Corpus fell from 10 contradictions to 4, all genuine.

Rule to carry forward: when a new guard fires on the change that introduces it,
stop and treat that as a calibration failure, not as proof the guard works.

Refs #3383, PR #3406.
