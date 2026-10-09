# ADR Debate Log: ADR-101 and ADR-104 amendments for the test selector retirement

Issue #6239. Panel: full six seats, per owner decision D3, because the selector was a named CI enforcement component.

## Summary

- **Rounds**: 2
- **Outcome**: Consensus (5 Accept, 1 Disagree-and-Commit)
- **Final Status**: ADR-101 stays accepted (amended). ADR-104 stays proposed (amended).
- **Scope**: amendment notes only. No requirement number changed. The owner decisions were not open for debate: buy not build, pre-push collection only, keep `--dist loadfile`, pytest-split for the CI legs.

## Phase 0: Related work

- #5050 built the import-graph selector because the full suite cost 878 s per push.
- #4345 and #4408 recorded false greens from the earlier path filters.
- #4824 named pytest-testmon as a candidate. No rejection was recorded.
- #6036 replaced the `skip-tests` job with `test-result`.
- SPEC-6211 recorded the 2026-10-07 decision to keep `loadfile`.

## Round 1 Summary

### Agent Positions

| Agent | Position | Main finding |
|-------|----------|--------------|
| architect | Block | ADRs said `scripts/test_selection/` was deleted while it was still tracked |
| critic | Disagree-and-Commit | "CI runs every leg in full on every event" overstated scope |
| independent-thinker | Disagree-and-Commit | High to Medium risk downgrade had no evidence |
| security | Disagree-and-Commit | `/scripts/ci/` is already owned; only `tests/.test_durations` lacked an owner |
| analyst | Block | No Chesterton record of why the selector existed |
| high-level-advisor | Disagree-and-Commit | Merge only with the code deletion in the same PR |

### Key Issues Addressed

- P0: the deletion claim did not match the tree.
- P0: the ADRs did not say why the selector existed or why it could go.
- P1: the "every leg, every event" claim was too broad.
- P1: the impact row lowered risk without evidence.
- P1: the CODEOWNERS text was stale.
- P1: the ADR-101 `skip-tests` note implied #6239 removed it.
- P1: no evidence that a durations edit cannot drop a test.

### Major Changes Made

- M4 deleted `scripts/test_selection/` and `tests/test_selection/` in this PR (commits d4a2b693c, a910d2633).
- Both ADRs now carry the Chesterton record: #5050 (878 s per push), #4345 and #4408, the 5 of 30 PR runs it narrowed, the inferred 40 to 60 s saving, and the Context-not-Core classification.
- Scope is precise: every pytest matrix leg runs its full partition on every event. Four pinned files run in `split-1` pin steps. `security` and `test-windows-pwsh` stay gated by `check-paths`.
- The impact rows split. `path_policy` stays High. Durations and partition membership are Medium.
- `.github/CODEOWNERS:63` adds `/tests/.test_durations`.
- `tests/ci/test_pytest_split_pool.py` proves a hostile durations file fails red. It empties a group (exit 5) or crashes pytest-split (exit 3). When every group exits 0, the groups cover the slice exactly once.

## Round 2 Summary

### Agent Positions

| Agent | Position | Note |
|-------|----------|------|
| architect | Accept | All eight resolutions verified against the files |
| critic | Accept | P2 wording only |
| independent-thinker | Disagree-and-Commit | Asked for tense fixes and the sample method |
| security | Accept | Asked for the exit-code clause in the impact row |
| analyst | Accept | Line cites hold |
| high-level-advisor | Accept | Scope ruling kept |

### Dissent

The independent-thinker committed with three P2 notes. Two tense fixes were applied. The 5 of 30 figure now states its sample: 30 of the 32 pull_request runs among the 80 most recent completed `pytest.yml` runs, 2026-10-08. The 40 to 60 s saving stays labeled as inferred, not measured.

### P2 items applied after Round 2

- ADR-101: "that half is still true" now reads "was true when written".
- ADR-104: the retired probe now says the selector "fell back".
- ADR-101 impact row: states the exit 5 and exit 3 outcomes and cites the guard test.

### Clarifications after consensus (from the /review decision-rigor axis)

These add no new decision. They state the evidence limits the panel already accepted.

- ADR-104 now says "per-push cost" where it said "cost", since pre-push only collects.
- ADR-104 scopes the testmon rejection to testmon 2.2.0 on this repository, with one confirmed miss.
- ADR-104 says push and merge_group timing was not sampled, and names the revert path.
- ADR-101 marks the historical `run_pytest_selected.py:177` citation with a `citation-freshness: ignore` note, because PR #6239 deletes that file.
- PR #6241 review (CodeRabbit): ADR-101's sixth-edge-kind passage said `path_policy.yml` decides whether six pinned contexts run. It now marks that as historical and says the filter gates only `security` and `test-windows-pwsh`.

### Deferred, flagged in the PR body

These predate #6239. The high-level-advisor ruled them out of scope.

- ADR-101 says CODEOWNERS has "five globs". The file has many more rules.
- ADR-104 `FORCE_RUN_EVENTS` text.
- ADR-090:255 mentions the pre-push selector.
- ADR-101 history cites `pytest.yml` line numbers that have moved.
- ADR-104 body text still cites #5318 as open work in places.

## Strategic Review

| Lens | Assessment |
|------|------------|
| Chesterton's Fence | PASS: purpose and its expiry are recorded |
| Path Dependence | PASS: pytest-split is one dev dependency and one data file |
| Core vs Context | PASS: test selection is context, so the repo buys |
| Second-System Effect | PASS: the branch removes more code than it adds |

**Overall Strategic Assessment**: APPROVED.
