---
type: requirement
id: REQ-010
title: M4 rework warning recalibration
status: draft
priority: medium
category: tooling
related:
  - DESIGN-010
  - TASK-010
issues:
  - 1990
predecessor: REQ-009
retrospective: .agents/retrospective/2026-05-10-pr-1989-recursive-failure.md
author: Richard Murillo
created: 2026-05-10
updated: 2026-05-10
---

# REQ-010: M4 Rework Warning Recalibration

## Step 0 First Principles

### Q1 Demand Reality

Three requesters:

1. Richard Murillo (issue #1990 + user correction 2026-05-10: "you don't need a fixture repo, you have PRs as a test bed")
2. `.agents/retrospective/2026-05-10-pr-1989-recursive-failure.md` (PR #1989 bug history #7: threshold-6 returned 0 on test bed)
3. `.serena/memories/implementation/implementation-007-pr1989-recursive-failure-learnings.md` (MED constraint: "Threshold-based detectors need calibration data from real PRs")

### Q2 Status Quo

1. Spec invocation picks an arbitrary numeric threshold
2. Detector ships with the arbitrary value
3. Real-PR run reveals threshold misses signal entirely
4. Threshold gets adjusted blindly OR detector silently becomes dead weight

### Q3 Desperate Specificity

The M4 rework warning at `.claude/skills/session-end/scripts/rework_warning.py`, constant `REWORK_THRESHOLD = 6`. PR #1989 had max file edit count of 4. Detector returns 0 on its own test bed.

### Q4 Narrowest Wedge (revised after Step 0.5 calibration)

~75 min total:

1. ~15 min: add `.agents/memory/episodes/` to `_REWORK_EXCLUDED_PREFIXES`
2. ~30 min: TDD with real git log fixture from orphan-ref-validator branch
3. ~15 min: self-apply gate against current branch
4. ~15 min: commit canonical + mirror

### Q5 Observation

- PR #1989 max file edit count = 4
- M4 returns 0 rework warnings on PR #1989
- Calibration across 4 branches: feat/req-008-step-0-5 (max=13), feat/issue-1939-orphan-ref (max=19), feat/issue-1988 (max=4), feat/1066-retire-pester (max=3)
- Real rework files cluster at 8-19 edits; non-rework at 1-4
- Top hit on orphan-ref-validator: episode-2026-05-10.json (19 edits, generated, should exclude) and scan.py (14 edits, real rework signal)

### Q6 Future-fit

Calibration data scales linearly with PR volume. Per-extension thresholds tracked as Deferred.

## Prior Art / Constraints

### Direct prior art from memory

- `implementation-007-pr1989-recursive-failure-learnings`: "Threshold-based detectors need calibration data from real PRs". Decision: honor.
- `testing-002-test-first-development`: write test first, code second. Decision: honor.
- `testing-007-contract-testing`: mock data structures must match real schemas. Decision: honor; use real git log output as fixture.
- `testing-004-coverage-pragmatism`: 100% on critical paths; treat detection logic as critical.
- chestertons-fence: `REWORK_THRESHOLD = 6` was committed without justification; revisable. Decision: PRESERVE constant, MODIFY exclusion list.

### Connected context (Phase 2 traversal)

- Connected entity: `.agents/memory/episodes/episode-*.json` (in-scope addition to exclusion list)
- Connected entity: `src/copilot-cli/skills/*/scripts/*` (mirror inflation, deferred)
- Out-of-scope: per-extension thresholds
- Linked project: /spec lifecycle

### Coverage notes

- chestertons-fence: 3 commits to module; no justification for "6"; PRESERVE + MODIFY
- Memory: 4 relevant entries hit
- Knowledge-graph: Phase 1-2 shallow; no Forgetful MCP

## Requirement Statement

WHEN `rework_warning.py` is invoked against a development branch that contains episode log files under `.agents/memory/episodes/` alongside edited source files,
THE SYSTEM SHALL exclude all files matching `_REWORK_EXCLUDED_PREFIXES` (including `.agents/memory/episodes/`) from the rework-candidate list and SHALL emit a warning for every source file whose edit count meets or exceeds `REWORK_THRESHOLD`,
SO THAT generated-log churn does not suppress real rework signal and the detector fires on the conditions it was built to detect.

## Context

PR #1989 exposed two independent defects in the M4 rework detector:

1. The exclusion list omitted `.agents/memory/episodes/`, a path that accumulates high edit counts on every branch that touches agent memory. Episode files are generated artifacts, not rework candidates. Their presence inflated the noise floor and crowded out real signal.

2. Calibration data gathered from four sampled branches (see Q5) showed that the real rework threshold sits between 8 and 19 edits. `REWORK_THRESHOLD = 6` is correct for that distribution. The detector was not broken by the threshold; it was broken by the exclusion list omission and the absence of a real-fixture test that would have caught the omission before merge.

The fix is narrow: add the missing prefix, write a contract test using captured real-branch output, and run the self-apply gate before the milestone commit.

## Acceptance Criteria

- [ ] REQ-010-01: WHEN tests/skills/session-end/test_rework_warning.py runs against a stubbed git log matching the orphan-ref-validator branch's actual output (scan.py 14 times, episode-2026-05-10.json 19 times), THE SYSTEM SHALL include scan.py in the warning list AND exclude episode-2026-05-10.json, SO THAT generated-log churn does not swamp real signal.

- [ ] REQ-010-02: WHEN `_REWORK_EXCLUDED_PREFIXES` is evaluated, THE SYSTEM SHALL include `.agents/memory/episodes/`, SO THAT episode logs are filtered alongside session logs and src/claude/.

- [ ] REQ-010-03: WHEN M4 runs against the current development branch before the milestone commit, THE SYSTEM SHALL emit at least one warning line that matches the empirical rework distribution (P75=5, P90=11 across 4 sampled branches), SO THAT the detector is verified to fire on the conditions it was built to detect.

- [ ] REQ-010-04: WHEN tests/skills/session-end/test_rework_warning.py runs, THE SYSTEM SHALL include a test case that loads its git-log fixture from a captured real-branch output (saved as a test-data file, not constructed inline), SO THAT the contract test mirrors the production input shape per testing-007-contract-testing.

## Rationale

The detector is security-adjacent tooling (it gates milestone commits). Missing signal on its own test bed is a correctness failure, not a style issue. The fix is additive and reversible. Preserving the threshold value keeps the chestertons-fence constraint: there is no evidence the value is wrong, only evidence the exclusion list is incomplete.

## Dependencies

- `.claude/skills/session-end/scripts/rework_warning.py` must exist at the canonical path (verified: present in repo).
- `tests/skills/session-end/` directory must exist or be created.
- Git CLI must be available in the test environment for fixture capture.
- DESIGN-010 must be approved before TASK-010 implementation begins.

## User Stories

1. As a session-end skill consumer, I want the M4 rework detector to flag source files I edited many times, so that I get a genuine signal before closing the milestone commit rather than a silent zero.

2. As a test author, I want the rework-warning test suite to load a fixture captured from a real branch, so that the test contract stays honest as the git log format evolves.
