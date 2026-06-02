# Session 01: Issue #2222 - CI Gap in agent-drift-detection

**Date**: 2026-06-02  
**Issue**: #2222  
**Branch**: `fix/2222-drift-detection-build-all`  
**Agent**: rjmurillo-bot  
**Status**: In Progress

## Objective

Close the CI gap where `agent-drift-detection.yml` only validates agent `.md` files via `generate_agents.py --validate`, but misses `build_all.py` output drift (plugin lib mirrors under `src/copilot-cli/lib/`, Copilot hook/skill/instruction mirrors). Add manifest version parity check to prevent `.claude/.claude-plugin/plugin.json` and `src/copilot-cli/.claude-plugin/plugin.json` version mismatches.

## Problem Context

- PR #2203 added `scripts/ai_review_common/cache_guard.py` plus `.claude/lib` mirror
- Generated `src/copilot-cli/lib/ai_review_common/cache_guard.py` was not committed
- `agent-drift-detection.yml` workflow only runs `python3 build/generate_agents.py --validate`
- `validate-generated-agents.yml` already runs `build_all.py --check` and `sync_plugin_lib.py --check`, but has different triggers
- Version mismatch exists today: both manifests show 0.5.32 (already matching, but no automated check)

## Session Protocol Compliance

- [x] Serena initialization: Not applicable (working in worktree as rjmurillo-bot)
- [x] Read HANDOFF.md
- [x] Read AGENTS.md and CLAUDE.md
- [x] Read relevant ADRs (ADR-006, ADR-008, ADR-035, ADR-042)
- [x] Session log created
- [x] Branch verified: `fix/2222-drift-detection-build-all`
- [x] Bot identity verified: rjmurillo-bot authenticated

## Design Decision

**Option C with enhancements**: Create dedicated `validate_plugin_manifests_version_parity.py` validator

**Rationale**:
- `validate-generated-agents.yml` already runs `build_all.py --check` and `sync_plugin_lib.py --check`
- `agent-drift-detection.yml` only runs agent validation
- Gap: neither workflow checks manifest version parity
- Solution: Add new validator, wire into both workflows for defense-in-depth

**Architecture**:
1. New validator: `build/scripts/validate_plugin_manifests_version_parity.py`
2. Wire into `validate-generated-agents.yml` (existing comprehensive validation workflow)
3. Also wire into `agent-drift-detection.yml` (closes the reported gap)
4. Exit codes: 0 = match, 2 = mismatch (follows build_all.py convention)

## Work Breakdown

### Phase 1: Create Validator
- [ ] `build/scripts/validate_plugin_manifests_version_parity.py`
  - Read both manifests (.claude and src/copilot-cli)
  - Compare version fields
  - Exit 0 on match, exit 2 on mismatch with clear diff
  - Handle missing file, malformed JSON edge cases

### Phase 2: Tests
- [ ] `tests/build_scripts/test_validate_plugin_manifests_version_parity.py`
  - Happy path: versions match → exit 0
  - Mismatch: different versions → exit 2 with diff
  - Missing manifest → exit 2 with clear error
  - Malformed JSON → exit 2 with parse error

### Phase 3: CI Integration
- [ ] Update `validate-generated-agents.yml`
  - Add new step after `Plugin lib sync check`
  - Call validator
- [ ] Update `agent-drift-detection.yml`
  - Add new step after agent validation
  - Call validator (closes the reported gap)

### Phase 4: Verification
- [ ] Reproduce original failure (temporarily delete a lib mirror file)
- [ ] Verify new gate catches it
- [ ] Run `python3 scripts/validation/pre_pr.py`
- [ ] Commit atomically (≤5 files per commit)

## Decisions Made

1. **Validator location**: `build/scripts/` (follows existing pattern)
2. **Exit code**: 2 for mismatch (matches build_all.py convention per ADR-035)
3. **Both workflows**: Defense-in-depth, different triggers give broader coverage
4. **Version equality**: Strict match required (0.5.32 = 0.5.32), no "copilot >= claude" rule

## Files Modified

### Created
- `.agents/sessions/2026-06-02-session-01-issue-2222-ci-gap.md` (this file)
- `build/scripts/validate_plugin_manifests_version_parity.py`
- `tests/build_scripts/test_validate_plugin_manifests_version_parity.py`

### Modified
- `.github/workflows/validate-generated-agents.yml`
- `.github/workflows/agent-drift-detection.yml`

## Commits

Will be added as work progresses.

## Session End

Not yet complete.

## Delivery Summary

- **PR**: #2285 - <https://github.com/rjmurillo/ai-agents/pull/2285>
- **Author**: rjmurillo-bot ✓
- **Branch**: fix/2222-drift-detection-build-all
- **Commits**: 2 (762cc6d4, 42681b96)
  - Commit 1: feat(ci): add plugin manifest version parity validator (2 files: validator + tests)
  - Commit 2: fix(ci): close build_all drift gate in agent-drift-detection (3 files: both workflows + session log)
- **Pre-PR validation**: Passed ✓
- **Tests**: 13/13 passing ✓
- **Design choice**: Option C with enhancements (dedicated validator wired into both workflows)

All phases complete. Issue #2222 resolved.
