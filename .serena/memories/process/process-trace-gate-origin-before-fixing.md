# Skill: Trace a failing gate's origin before fixing it (100%)

**Atomicity Score**: 100%
**Source**: Retrospective `.project-toolkit/retrospective/2026-10-11-goal-followup-loop.md`
**Date**: 2026-10-11
**Tag**: helpful
**Impact**: 9/10 (a fix turned into a removal of about 3,350 dead lines)

## Statement

Before fixing a failing gate, read the PR that built it (#4828, #6260).

## Evidence

Probe PR #6258 showed Validate Vendor Provenance blocking on 5 paths that never existed in any ref. The first plan was to patch the gate's triggers. The owner asked why the gate existed. Reading #4828 showed it was built ahead of a vendor bundle planned in #4651. #4651 merged without the bundle, and ADR-085 Decision 9 later deleted the hook it served. PR #6260 deleted the gate and its orphaned config instead of patching them.

## Related

- `process/process-search-open-issues-before-designing-a-fix` has the same search-first shape for issues.
