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
every ratchet under `scripts/ci` handed its linter the same conflicted path two
or three times and counted its violations that many times. The reporter saw
`585 violations > baseline 583 (+2)` on a branch whose only conflicted file was
byte-identical to `origin/main`, and `git add` of unchanged content cleared it.

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

A measurement gate reported a number that described no tree that existed, with
no signal distinguishing it from a real regression. The count and the printed
violation list were internally consistent, so the output actively led the reader
away from the index. It fires exactly when someone is mid-merge and least able
to tell an artifact from a regression, which is what turned a two-line defect
into a substantial diagnostic detour for the reporter.

## Remediation

- Deduplication at the shared seam, so all six ratchets are covered at once.
- A stderr note naming the unmerged paths. The count is right after the fix, and
  the note still earns its place: the linter reads content off disk, so conflict
  markers left in the working copy add lines and can push a file over a size
  threshold on their own. A count taken mid-merge deserves the caveat.
- The note is capped at five named paths, because a two-hundred-file conflict
  printed above a 40-line violation cap buries the payload.

## Learnings

- A git plumbing command's unit of output is worth checking before it is
  consumed as a set. `ls-files` enumerates index entries, not paths, and the two
  differ only in a state most sessions never reach.
- When a gate reports a number, the honest failure is one that says which tree
  it measured. Correcting the count and dropping the mid-merge note would have
  left a second, smaller version of the same defect: a number nobody can place.
- A shared helper makes the mirror obligation cheap to discharge but easy to
  under-claim. Asserting each consumer still holds the fixed reference costs six
  lines and converts "they share it today" into a standing check.
