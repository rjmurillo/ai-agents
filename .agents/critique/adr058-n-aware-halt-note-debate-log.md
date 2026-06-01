# ADR-058 Review: N-aware Halt Threshold Note (Issue #1878)

Date: 2026-05-31
Scope: One documentation note added to `.agents/architecture/ADR-058-agent-eval-discipline.md`.
Change class: Documentation of an already-implemented, scoped change to an existing capability (the `halt-due-to-flakiness` gate). Not a new decision, not a policy reversal, not a removal of a constraint.

## Subject of Review

The note records that `ReportAggregator` halts when the flaky-fixture count reaches `max(ceil(0.30 * N), min(5, N // 2))` instead of using a fixed 30 percent fraction. The 30 percent fraction stays normative at large N. A small-N floor (5 at N=10) keeps a couple of flaky fixtures from halting a tiny corpus. A flag-and-continue mode is exposed on the aggregator. Implementation lives at `scripts/eval/_report_aggregator.py:_flaky_halt_count`.

## Phase 0: Related Work

- ADR-058 already names the small-N problem in "Cadence Trigger After This Spike" (line 275): at N=10 the old 30 percent fraction made three flaky fixtures exceed the threshold, and recommended corpus expansion to N>=30. The N-aware threshold is the code-side complement of that recommendation: it relaxes the small-N halt instead of requiring corpus growth before any verdict can run.
- AC-10 (REQ-004) is the source requirement for the flakiness gate. The 30 percent fraction is preserved at large N, so AC-10 intent holds.
- Issue #1878 is the motivating ticket.

## Phase 1: Independent Review

| Agent | Verdict | Key finding |
|-------|---------|-------------|
| architect | Accept | The note is consistent with the existing ADR structure and cites the canonical implementation symbol. The 30 percent fraction remains the normative governor at the corpus sizes the methodology targets (N>=30), so the ADR's statistical-power argument is intact. |
| critic | Accept | The note states the small-N floor and the boundary (4 of 10 no longer halts, 5 does). It does not overclaim: it explicitly says the 30 percent fraction governs at large N. No gap between the note and the code (verified against `_flaky_halt_count`). |
| independent-thinker | Accept with one observation | The flag-and-continue mode is a new operating mode. Observation: the default stays hard-halt, so the methodology's normative behavior is unchanged unless a caller opts in. The note correctly frames the flag as a recorded-but-non-halting signal, not a soft pass. |
| security | Accept | No security surface. The change is an in-process arithmetic threshold on eval reporting; no new external input, no auth, no command or path handling. |
| analyst | Accept | Evidence is concrete: the worked values (N=2 -> 1, N=10 -> 5, N=30 -> 9) are reproduced in tests `TestFlakyHaltCount` and `TestReportAggregatorNAwareHalt`. 307 eval tests pass. The behavior change to the prior `test_contingency_above_30_pct_halts` test is deliberate and documented in the test as a #1878 behavior change, not a silenced failure. |
| high-level-advisor | Accept | Priority is correct: the small-N halt was over-tight and blocked verdicts on legitimate small corpora. The fix lowers a false-halt rate without weakening the large-N guarantee. Ship. |

## Phase 2: Consolidation

Consensus: 6 of 6 Accept. No P0 or P1 issues. One P2 observation (independent-thinker): the flag-and-continue mode should not become a default path to graduation; the ADR text already forbids softening halt into a pass, and the note keeps the flag as a non-halting signal only. No conflict to resolve.

## Phase 3: Resolution

No blocking issues. The note is a faithful, minimal record of the implemented threshold and mode.

## Phase 4: Convergence

All six agents Accept. Strategic lenses:

- Chesterton's Fence: the fixed 30 percent fraction's purpose (halt unstable methodologies) is preserved at large N; only the small-N false-halt is relaxed. PASS.
- Path Dependence: reversible (single arithmetic helper, default unchanged). PASS.
- Core vs Context: eval discipline is Core; the change sharpens it. PASS.
- Second-System Effect: no scope creep; one helper plus one optional flag. PASS.

Verdict: APPROVED. The note may land alongside the implementation in the same PR.
