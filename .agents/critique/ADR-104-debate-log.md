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
