# Retrospective: Fixing Silent Failures, Silently (PR #5176)

## Session Info

- **Date**: 2026-08-21 (session opened 2026-08-20)
- **Trigger**: Owner instruction to review PR #5175 and drive it to closure. That PR
  carried a zero diff, so the work became: verify the defect still lived on `main`,
  implement it properly, open PR #5176, and drive that to green.
- **Scope**: `.claude/commands/pr-autofix.md` and its generated Copilot mirror, plus
  six new test modules under `tests/commands/`.

## What the change became

The reported defect was one `jq` path: `.Data.Tier` read from a producer that emits
no `Data` envelope, so `TIER` was pinned at `UNKNOWN` on every call. The fix is one
line. Everything else in the PR exists because a stuck sentinel does not fail one
way, and because closing the instance leaves the class open.

Two gates now stand behind it. A static contract gate binds every `jq` read in the
command body to its producer's real schema, derived with `ast`. A runtime gate
extracts the block between marker comments and executes it under `bash -c` against
fake producers, parameterized over the source and the generated mirror.

## The pattern that kept recurring

**A check whose unit is narrower than the claim it backs.** Counted across the PR it
appears roughly ten times, in three families:

1. **Coverage guards.** Presence of a line, then a count of paths, then programs,
   then producer binding, then recognized-versus-dispatched, then source without
   mirror. Each repair moved the unit one step closer to the claim, and each time
   the previous unit had looked sufficient.
2. **Recorded figures.** Pass counts and line numbers pinned in durable artifacts,
   narrower in time than the tree they described. Four separate staleness incidents.
3. **Controls.** Two probes that could not move the thing they measured, so they
   reported nothing and read as passes.

The third family is the one worth carrying forward, because it is the least visible.

## Finding 1: a control that cannot fail is not a passing control

Twice this session I ran a control, saw it pass, and nearly recorded that as
evidence.

- The inverted control's discrimination probe flipped `[ "$TIER" != "T1" ]` to
  `!= "T9"`. T3 sits on the same side of both, so the edit was behavior-preserving
  for the case the control runs. It passed and proved nothing.
- The comment-skip test used prose that merely mentioned bracket notation.
  `jq_programs` never reads a line with no `jq` token, so removing the guard under
  test changed nothing and the test passed anyway.

Both surfaced only by running the control and reading SURVIVED rather than DEAD.
Neither would have been caught by inspection, because both looked like the obvious
probe for the behavior in question.

**Carry forward**: after writing a control, ask what surviving input would make its
assertion false. If none exists, the control is unfinished, not passing. This is
testing rule SHOULD-10 applied to controls rather than to tests, and MUST-7's
three-outcome reporting is what makes the distinction visible at all.

## Finding 2: fixing a silent failure introduced a new one, four times

Every one was caught by a reviewer, not by the suite I was writing to catch exactly
this class.

| Repair | What it introduced | Direction |
|---|---|---|
| Capture the producer once | `2>/dev/null` on both `jq` reads, hiding parse errors | mislabels a skip |
| `//` default on completeness | jq's `//` fires on `false`, so an incomplete fetch read as unreadable | mislabels a denial |
| `tostring` to fix the above | no type check, so the string `"true"` became boolean `true` | **grants a merge** |
| Bracket-notation guard | no comment skip, so documenting the defect would fail the gate | closes on healthy input |

The third is the serious one: it fails open on the auto-merge path, which is the
single thing the guard exists to refuse. The suite caught the first by name. The
other three needed a human or a bot reading the code.

**Carry forward**: a repair to a silent-failure defect is itself a silent-failure
candidate, and the tests written for the original rarely cover the repair. After
fixing one, enumerate the *values* the new code can see, not just the branches, and
find the one that differs from what the old code saw. The `"true"` string was
reachable in one line of `jq` and invisible to five passing tests.

## Finding 3: whether the fix opens the case decides the scope question

A silent-failure sweep produced five findings outside the PR's diff, all pre-existing
on `main`. The instinct was to file them all as follow-ups, which is the correct
default and matched how the `--is-bot` gap had already been deferred.

Two of them were not follow-ups, and the discriminator was direction:

- **Completeness (`fetched_pages_complete`).** `classify_tier` returns T1 on
  `CanMerge`, which never consults it, so a truncated fetch can classify T1. That
  case was covered *by accident* before this PR, because a pinned `UNKNOWN` made
  `TIER != T1` hold for every PR, so the disarm gate stripped auto-merge anyway.
- **Round-cap escalation (CWE-284).** The breaker's ESCALATE path terminated the PR
  before the disarm gate ran, handing a human a PR that could still merge itself.
  Same mechanism: a pinned `UNKNOWN` never matched T3 or T4, so the breaker never
  fired and the path was unreachable.

In both, correcting the tier read is what made the case reachable. That is a mirror
obligation, not adjacent work.

**Carry forward**: for each pre-existing defect found near a fix, ask whether the
fix makes it reachable. "Pre-existing on `main`" and "not opened by this change" are
different claims, and only the second justifies deferral.

## Finding 4: a test can assert the defect is correct

The round-cap test read:

```python
assert not run.disarmed, "the loop kept acting after the round cap escalated"
```

It encoded the CWE-284 behavior as desirable, with a rationale that conflated
disarming with acting. Disarming is not acting on a PR; it is taking a capability
away from one, so it was never what the escalation needed to stop.

This is worse than absent coverage, because it also blocks the fix and reads as
deliberate. It was flipped rather than deleted, with the old assertion quoted in the
new docstring.

**Carry forward**: when a reviewer reports a behavior as a defect and a test asserts
that behavior, the test is a finding too. Check the assertion's justification, not
just its subject.

## Finding 5: durable records need properties, not measurements

Pass counts in the QA report went stale four times: once carried across a file split
so a row described a file that no longer had those cases, then repeatedly as the
suite grew. Each time the repair was to re-measure, which restores accuracy and
preserves the failure mode.

The fix that held was removing the counts and recording that every command exits 0.
A count is a fact about a moment; the exit status is a fact about the head, and
re-running the table checks it either way. The same move had already been applied to
a harness comment earlier in the same PR and simply was not generalized, because the
PR body named the QA report as the one place counts were still allowed.

**Carry forward**: when a correction is applied in one place, ask where else the same
claim is written. Counts still belong in mutation controls, where the number is the
finding.

## Process notes

- **`ruff format <directory>` reformatted ten unrelated files, three times.** The
  drift is pre-existing on the branch (confirmed with changes stashed). Scope the
  formatter to the files you touched, and read `git status` before every commit.
- **Concurrent agents pushed to the branch five times**, each landing a change
  equivalent to one staged locally, and twice fixing a real defect in code pushed
  minutes earlier. Taking their commit and dropping the local duplicate avoided
  force-pushing shared history every time.
- **`gh` lost both GraphQL and REST mid-session** (403 through the egress proxy).
  The GitHub MCP tools covered every read that mattered. Worth knowing that the
  local `commit-limit-bypass` check reads the label through `gh` and therefore
  cannot see it from a remote session, which is an environment problem rather than
  a PR problem.
- **A red check was an unrelated flake**: `test_portability_baseline_predecessor.py`
  races git's background `maintenance.lock`, where `rglob` snapshots a file git
  deletes before `unlink()` runs. Not this PR's code; proposed `missing_ok=True`
  rather than widening the diff.
- **A red `PR Merge State`** was GitHub answering `mergeStateStatus=UNKNOWN` seconds
  after a push, classified exit 3 (external) by the checker itself. Superseded by
  the next run.

## What went well

- Every bot finding on the PR was real, and treating them as bug reports rather than
  noise found four defects the suite could not.
- The defect *class* was closed rather than the instance: both the reported shape and
  its repeat are negative controls, and the gate now covers every read.
- Mutation controls with byte-identical restore assertions caught two cases where the
  target literal was not unique, which would otherwise have mutated two sites and
  silently stopped isolating anything.

## What to do differently

1. Run the control before believing the fix, and read SURVIVED as "I learned
   nothing," never as "it holds."
2. Treat a repair to a silent failure as new code needing its own value enumeration.
3. Ask "does my fix open this?" before deferring an adjacent finding.
4. Scope formatters to touched files.
5. Prefer properties over measurements in anything that outlives the commit.

## References

- PR #5176, issue #5094.
- `.agents/qa/session-99923-pr-autofix-tier-field-contract.md`, the report.
- `.agents/qa/session-99923-pr-autofix-review-passes.md`, the pass-by-pass record.
- `.claude/rules/testing.md` MUST-7 (three mutation outcomes), MUST-11 (inverted
  control), SHOULD-10 (discriminating input).
