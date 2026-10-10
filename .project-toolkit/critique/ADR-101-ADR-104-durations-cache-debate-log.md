# ADR Debate Log: ADR-101 and ADR-104 amendments for cache-backed pytest-split timings

Panel: full six seats, because the change edits the ADR-101 CODEOWNERS requirement and an impact row that other reviews read.

## Summary

- **Rounds**: 2
- **Outcome**: Consensus (round 2: critic Accept, security Pass; the other seats' round-1 Disagree-and-Commit conditions are all resolved)
- **Final Status**: ADR-101 stays accepted (amended). ADR-104 stays proposed (amended).

## Decision under review

The owner decided on 2026-10-09 that nobody maintains a durations file. The branch deletes the committed `tests/.test_durations` and its CODEOWNERS rule. pytest-split timings now come from an Actions cache. Each split leg restores the newest main-scope cache. The `test-durations` job merges the per-leg files and saves the cache only on a push to main. A 480 s leg limit runs in the required `coverage` job.

## Round 1 Summary

### Agent Positions

| Agent | Position | Main finding |
|-------|----------|--------------|
| architect | Disagree-and-Commit | Cited test file did not exist; ADR-104:620 stale; "no head-editable file" too broad |
| critic | Block | Nonexistent test citation (P0); ADR-104:620 still named the deleted file and rule (P0) |
| independent-thinker | Disagree-and-Commit | The 480 s gate ran in a job no required context depends on, so it did not block |
| security | Accept (conditional) | Citation fix; say only the main scope is protected; branch looked like it reverted newer main content |
| analyst | Disagree-and-Commit | Citation fix; a pull request can still write its own ref-scoped cache |
| high-level-advisor | Disagree-and-Commit | Fix ADR-104:620 here; do not call the change a simplification |

### Key Issues Addressed

- P0: the ADRs cited `tests/ci/test_pytest_split_durations_wiring.py`, which does not exist.
- P0: ADR-104:620 still named `tests/.test_durations` and its CODEOWNERS rule.
- P1: the leg-limit gate did not block a merge.
- P1: "no head-editable file sets group balance" overstated the protection.
- P1: the apparent reverts of `vendor-provenance.yml` and the Claude action pins.

### Major Changes Made

- Both ADRs now cite `tests/ci/test_pytest_split_durations_save.py`, which asserts the push-to-main save condition.
- ADR-104:620 mirrors the ADR-101 row.
- The leg-limit check moved into the `coverage` job, which `Run Python Tests` requires.
- The text says no head-editable data file carries the timing map, and names the CODEOWNERS rules that own the workflow and the runner.
- `/scripts/testing/` gained a CODEOWNERS rule, because it holds the 480 s limit.
- The text names the invariant: every collected test lands in exactly one group, so a hostile or empty map ends red or unbalanced, never green with tests skipped.
- The text names the cold-cache case as a latency risk, not a correctness risk.
- The branch was rebased; the reverts came from a stale base and are gone.

## Round 2 Summary

### Agent Positions

| Agent | Position | Note |
|-------|----------|------|
| critic | Accept | All eight round-1 items resolved against the live files |
| security | Pass | No reverts remain; save is push-to-main only; the gate fails closed on a missing JUnit file |

### Dissent

The high-level-advisor noted the change adds about 315 production lines and removes 87. It trades a maintained file for more CI wiring. The owner chose that trade: no hand-maintained file.

The independent-thinker noted 480 s is pytest time only. Setup plus split-1's primary steps took about 95 s on PR #6241's run, so the gate fires before the 10-minute job limit.

## Strategic Review

| Lens | Assessment |
|------|------------|
| Chesterton's Fence | PASS: the file existed to balance legs; the cache does the same job without a maintainer |
| Path Dependence | PASS: reverting restores the committed file in one step |
| Core vs Context | PASS: leg balancing is context |
| Second-System Effect | WARNING: more wiring than before, accepted by the owner to remove manual upkeep |
