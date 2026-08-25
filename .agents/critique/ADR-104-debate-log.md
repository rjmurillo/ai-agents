# ADR Debate Log: ADR-104 Gate Tier Placement

## Summary

- **Rounds**: 1
- **Outcome**: Consensus to revise. Two Block votes, three Disagree-and-Commit,
  one Accept-with-findings. Every P0 was resolved by changing the code or the
  record, not by deferring it.
- **Final Status**: proposed, revised. `implemented: false` until merge.

Six seats reviewed the first revision of ADR-104 against the implementation on
`claude/pre-push-hook-performance-audak0`. Four additional agents reviewed the
implementation itself (code review, silent-failure, test coverage, CI wiring).
Phase 0 related-work research was folded into the seat prompts rather than run
as a separate pass: issues #5315, #4710, #5066, #5050 and ADRs 004, 049, 054,
071, 086, 101 were supplied as context and each seat verified what it used.

## Round 1

### Agent positions

| Agent | Position | Core objection |
|-------|----------|----------------|
| architect | Block | Rule 6's premise false; rule 3 violated by the shipping hook; ADR-054 and ADR-071 conflicts uncited |
| critic | Block | Rules 4 and 5 rest on "CI executes the same commit", false for the dominant change class; two of four claimed defect classes not caught |
| independent-thinker | Disagree-and-Commit | Same two premises; direction right, both statements ship to developers in hook output |
| security | Disagree-and-Commit | `.claude/skills/**` executes in neither plane; piping does not prove a glob-filtered job ran |
| analyst | Disagree-and-Commit | The 140s projection does not follow from its own components; the exit-1 causal claim unsupported |
| high-level-advisor | Disagree-and-Commit | Median fixed, tail untouched; the glob defect is the one no other seat's remit covers |

### P0 issues and resolution

**P0-1. The deduplication was unsound.** Raised independently by architect
(A2), critic (C3), security (S2), independent-thinker (I5), advisor (H1) and
the silent-failure agent. `piped: true` proves no earlier job failed, not that
one ran; every deferral target carries a `glob:` and `pre-pr-validation` does
not. The silent-failure agent settled it empirically on lefthook 2.1.10 against
a fixture repo: a glob-filtered job prints `(skip) no matching push files` and
the hook exits 0, so a skipped job is indistinguishable from a passed one.

Resolved by reverting the skip (`248797b4a`) rather than by weakening the
claim. The test that shipped with it checked job names and ordering, which
catches a rename and misses this entirely; it is rewritten as a regression
guard carrying the condition that would make a deferral sound, plus a negative
control proving the condition discriminates. Issue #5317 carries three costed
options for removing the duplication properly.

**P0-2. Two of four claimed defect classes are not caught by collection.**
Raised by architect (A4), critic (C2), independent-thinker (I2), each probing
independently. A test requesting a missing fixture collects clean, exit 0. Two
same-named test functions in one module collect and execute clean. Only the
import case, the syntax case, and a same-basename module collision exit
non-zero.

The false claim appeared in the ADR, in a docstring, and in the stderr line
developers read to decide what they are covered for. Corrected in all three
(`f215f6661`). Rule 5 now says "a defect class you have measured it to catch"
and names the two that failed.

**P0-3. "CI executes the same commit" was false at PR time.** Raised by critic
(C1), security (S1), independent-thinker (I1) and confirmed in detail by the
CI-wiring agent, which also found the mitigating fact nobody else had: `pytest.yml`
declares `merge_group` and `FORCE_RUN_EVENTS: merge_group`, so the paths filter
is bypassed in the merge queue and `main` was never exposed. The exposure was a
reviewer approving a green PR whose relevant tests had not run, with the
skip-through job carrying the same required check name.

Resolved two ways: the paths filter gained the Markdown roots its own tests
read (`134fd03f5`), each justified by a named test; and the stand-in's message
now states the merge-queue-versus-PR-time distinction instead of asserting
unconditional coverage.

### P1 issues resolved in this round

- The 140s projection did not follow from its cited components (analyst N1:
  the same arithmetic gives ~148.5s, and the "roughly 46s" term is a 3-of-4
  partial sum). The projection is removed rather than repaired; MUST-16 says a
  standalone sum is not a number to trust, and the real figure arrives with the
  first push.
- The exit-1 attribution was wrong (analyst N2). The mutation partition failed
  because its target file was being edited while the run was in flight, which
  the harness refuses by design; the `gh` GraphQL line came from a partition
  that passed. Corrected to state that 382s is a duration measurement and
  nothing more.
- `-q` was cancelled by `addopts = "-v ..."` (architect A9), printing 31,765
  lines into hook output per fallback push against 878 with three `-q`. Fixed;
  this was a token-cost regression in a change whose purpose includes cutting
  token cost.
- The record claimed no prior ADR set a pre-push cost bar (architect A8).
  ADR-054 set a qualitative one. Corrected and cited.
- Rule 3 was violated by the shipping hook with no exception clause (architect
  A1, advisor H2, independent-thinker I7), and ADR-071 had deliberately placed
  the credentialed e2e smokes in pre-push six days earlier. A Known
  non-conformances section now names all five jobs and cites ADR-071.
- ADR-054's enforced 900s `security-scan` budget contradicts the 300s target
  (architect A3). Named in the record as unreconciled rather than papered over.
- `AI_AGENTS_PYTEST_FULL_SUITE_LOCALLY` silently ignored every value but "1"
  (silent-failure agent), so `export ...=true` gave less work than requested
  with no notice. Now raises.
- `run_pytest` returned 0 for an empty command list (silent-failure agent). The
  invariant lives in another module; the function that decides whether a push
  is allowed now carries its own guard.
- The 14s / 34.62s inconsistency between the record and its own constant
  comment (critic C4, advisor H5, independent-thinker I4). Both are real, idle
  and loaded; the comment now says which, and the budget is sized from the
  loaded one per MUST-16.
- The inverted mutation control had its polarity broken by this branch
  (test-coverage agent): asserting exact stderr text made it die to a single
  added space, which is the opposite of an inverted control's job. Restored,
  with the exact-text assertion split into its own test. Its unverifiable
  "a mutation harness consumes this" docstring is dropped; nothing under
  `tests/mutation/` references it.
- The load-bearing broken-import claim had no executing test (test-coverage
  agent). Added end to end against a real tree with a clean-tree negative
  control, plus tests for the reason pass-through and for the collection
  ceiling appearing in a timeout message.
- `implemented: true` on an unmerged record (architect A10,
  independent-thinker I10). Set to false per ADR-073.

### Deferred with issues filed

- The duplication between `pre-pr-validation` and the fast stage, worth roughly
  40s per push: issue #5317, three costed options.
- The unmeasured tail (five glob-gated jobs, never timed when their globs
  fire), the unmeasured pre-commit target, the selector/CI-filter divergence, a
  hook-level deadline, and the ADR-054 reconciliation: issue #5318.

### Dissent recorded

The advisor seat dissented against shipping the record without the rule 3
exception clause and without fixing the glob defect. Both were done in this
round, so the dissent is satisfied rather than carried.

The analyst seat had no shell in its harness and could not run four of the
reproduction commands it was asked to run. Its claim audit is therefore
partial by construction, and it said so (N3). The orchestrator supplied those
measurements from its own runs; a future round should route a seat with
execution to confirm them independently.

The architect seat's A5 (eight pre-push jobs the tier model cannot place:
six advisory reporters and two local-state repair actions) is **not** resolved.
The record does not add a placement rule for non-blocking reporters. It is
recorded here as an open gap rather than folded into #5318, because it is a
question about the tier model itself rather than about pre-push cost.

## Next steps

1. Measure the hook end to end on the first real push and put the number in the
   record. Acceptance is gated on it.
2. Work #5317 before re-attempting any deduplication.
3. Work #5318's five items; the tail is the part of the operator's stated
   problem this record does not solve.

## Round 2: the acceptance gate closed

Round 1 ended with acceptance gated on one thing no seat could supply: an
end-to-end in-hook measurement of the pre-push hook during a real push.
`ci-scripts.md` MUST-16 forbids sizing a pre-push budget from a standalone run,
and every number Round 1 had was standalone. The critic (C4),
independent-thinker (I3), advisor (H5) and architect (A7) seats each raised
this independently, from four different angles.

The first push of this branch supplied it. Lefthook 2.1.10, same 4-CPU
container:

```text
total                        142.39s   (679s recorded for a comparable push)
  pre-pr-validation          105.48s   (110.12s recorded)
  fast parallel stage         55.32s   ( 56.21s recorded, max member 20.62s)
  python-tests                15.10s   (498.52s recorded)
  security-scan               13.02s
```

Three findings from Round 1 are settled by this rather than argued:

- The analyst's N1 objection to the 140s projection is moot. The projection was
  removed rather than repaired, and the measured figure, 142.39s, happens to
  land near it. That is a coincidence worth naming, not a vindication: the
  projection's arithmetic was still wrong, and it would have been wrong at any
  outcome.
- The advisor's "median fixed, tail untouched" verdict holds exactly. Every
  glob-gated tail job cost under 3s on this push because none of their globs
  fired hard. Nothing here measures the tail; issue #5318 still owns it.
- The shape changed. `pre-pr-validation` is now 74% of the hook. The
  duplication the advisor's H1 and the reverted skip were both about is now the
  largest remaining target, which raises issue #5317's priority.

The first push attempt also produced an unplanned observation. The
`mutation-safety` guard refused it in 0.33s, on leftover harness state from a
SIGKILLed run earlier in the session. Its own `recover` command could not clear
the marker: the marker compares a file hash against a snapshot taken before
commits that legitimately advanced HEAD, so a clean tree still reads as
modified. Clearing it required proving by hand that the working tree matched
HEAD. That is a real gap in the harness's recovery path and is recorded against
issue #5318.

The architect seat's A5 remains open and unaddressed: the tier model still has
no placement rule for the six non-blocking advisory reporters or the two
local-state repair actions in pre-push.

## Round 3: bounding the declared worst case

Round 2 closed the acceptance gate with a measured 142.39s push and left the
advisor seat's verdict standing: the median was fixed, the tail was not. The
operator's requirement is that pre-push must stop being a cause of aborted
container pushes, and a 4.8x median cut does not on its own establish that.

The gap was concrete. Two real pushes measured 142.39s and 144.39s. The
**declared** worst case of the same graph was 4170s, 69.5 minutes, 29x higher,
because caps had been sized on unloaded machines and never revisited. A cap is
not a cost, but it is the promise about the worst case, and the worst case is
what reclaims a container.

Three things changed.

**Seventeen caps resized from in-hook measurement.** The stdin group carried
four caps of 5m and 2m for jobs measured at 0.93s, 0.28s, 0.38s and 0.38s. The
fast parallel gates carried 5m each against a slowest member of 20.62s.
`python-type-check` carried 15m against 2.73s. Margins were left far above the
9x to 15x in-hook inflation `ci-scripts.md` MUST-16 records for this graph.

**Inner budgets pulled under their outer caps.** `python-tests` 30m to 15m with
its suite budget 1740s to 780s, and `workflow-local-run` 30m to 10m with its
budget 1740s to 540s, so the inner timeout fires first and the reader gets a
diagnostic rather than a bare kill, per ADR-086 Decision item 9.

**A ratchet on the declared total**, which is rule 7's ceiling half that Round 1
noted was missing (architect A6, critic C5, advisor H3). It models lefthook's
scheduling from the config rather than from a run summary, per MUST-17, and
carries a negative control raising a cap to 99h.

Result: 4170s to 2610s, 69.5 to 43.5 minutes.

One cut was reverted during the work and is worth recording, because it is the
same class of coupling the reverted deduplication was. Cutting
`pre-pr-validation` from 15m to 5m failed
`test_check_generated_staleness_termination.py`: that job's Generated Artifact
Staleness gate clamps to `PRE_PR_OUTER_CAP_SECONDS` and a test pins
budget-plus-grace at or under half the cap. The 15m was load-bearing for an
invariant two files away. It also bought nothing, since a parallel group costs
its slowest member and that is a 20m e2e job either way.

### What is still not solved

43.5 minutes is not a survivable declared worst case, and the ratchet stops it
rising rather than bringing it down. The remaining 2100s is two job classes:

- the two CLI e2e smokes at 20m each, which set the expensive group's cost;
- `security-scan` at 15m, which ADR-054 sets as an enforced 900s budget.

Attempts to measure the four glob-gated tail jobs while firing were
inconclusive: each scopes its work to `origin/main...HEAD` and short-circuits
when the branch does not touch its inputs, and `workflow-local-run` is DEGRADED
in a container because actionlint is absent. So they are unmeasured while
firing, and a push whose glob fires one can still outlive a container. That is
the honest residual, and it is issue #5318, not a claim this record can make.

## Round 4: closing the container bound

Round 3 cut the declared worst case from 4170s to 2610s and left the
requirement open. The record said so plainly: a push whose glob fires an e2e
smoke could still outlive a container, and cutting those caps without measuring
them would be the guess MUST-16 forbids.

The way out was not a better guess. It was noticing that a workstation and a
container are asking different questions and had been given one answer.

A workstation needs a long cap for a job with real work to do; a long cap costs
patience there. A container is reclaimed after a period without progress, so
the same cap is a job that can outlive its environment and take the push with
it, leaving no diagnostic at all. `_run_command` is the funnel every expensive
pre-push job's work passes through, so clamping its child's deadline to 150s
when `_is_remote_container()` is true bounds the container case without
touching the workstation case or CI.

The detection was not invented for this. Issue #2548 already added it for
`workflow-local-run`, and already established the precedent of degrading a
pre-push job in a container rather than blocking on an environment gap. Reusing
it was the difference between a new concept and an application of an existing
one.

```text
declared, workstation   4170s -> 2370s   (69.5 -> 39.5 min)
container-clamped         n/a ->  660s   (        11.0 min)
```

660s sits below the roughly 679s at which a reclamation was observed.

Two things this round is worth recording beyond the numbers.

**A 100x margin two files away was holding 900s in place.**
`pre-pr-validation` could not drop below a 15m cap because its Generated
Artifact Staleness gate clamps to `PRE_PR_OUTER_CAP_SECONDS` and a test pins
budget plus grace at or under half that cap. The budget was 420s for work
measured at 1s. Nothing in `lefthook.yml` mentions that constraint, and an
earlier attempt to cut the cap failed the staleness test rather than any hook
test. This is the same shape as the reverted deduplication: a local edit that
looks free because the thing it depends on lives somewhere the edit does not
touch.

**Nine cap cuts silently hit the wrong hook.** The first pass edited by job
name with a regex, and nine job names exist in both `pre-commit` and
`pre-push`; the regex matched the pre-commit copy each time. It was caught only
because the container assertion still failed afterward with
`infrastructure-advisory=300` in its own failure message, a number that should
have been 60. Without an assertion that printed the contributing jobs, the
commit would have shipped looking correct. Both budget assertions now name
their three largest contributors for that reason.

### Still open after this round

- The workstation declared worst case is 39.5 minutes against a 300s target.
  The two e2e smokes account for 1200s of it and remain unmeasured while
  firing. Issue #5318. This is slow rather than destructive.
- ADR-054's enforced 900s `security-scan` budget still contradicts the 300s
  target. In a container the clamp bounds it at 150s regardless, which lowers
  the stakes but does not reconcile the two records.
- The architect seat's A5, no placement rule for the six advisory reporters or
  the two local-state repair actions, is unaddressed for a fourth round.

### Round 4 addendum: the first cap set was too tight in one place

The fourth real push came back green at 142.47s, and it also showed
`pre-pr-validation` at 106.34s against the 3m cap that round had just given it.
1.7x headroom is thin, and a cap that blocks a legitimate push wastes the same
time the whole record is about; a false block is not a safer failure than a
slow push, only a different one.

Rebalanced rather than accepted: the subprocess clamp drops 180s to 150s, which
every job routing through it can afford (python-tests is the largest at 38.84s,
a 3.9x margin), and the reclaimed budget goes to `pre-pr-validation` as a 4m
cap, 2.3x over its measured cost. The container bound lands at 660s, exactly at
the ceiling, so the graph now has no slack: any new pre-push job fails the
assertion until something is measured and cut. That is the intended state for a
ratchet, not an accident.
