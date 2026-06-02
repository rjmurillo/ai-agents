# Session 01: Issue #2222 - CI Gap in agent-drift-detection

**Date**: 2026-06-02  
**Issue**: #2222  
**Branch**: `fix/2222-drift-detection-build-all`  
**Agent**: rjmurillo-bot  
**Status**: Complete

## Objective

Close the CI gap where generated artifact drift could pass `agent-drift-detection` when `build_all.py` owned outputs were stale. The final PR keeps the build-all drift gate fail-closed and aligns the generated-agent validation workflow with the manifest parity checker that exists on `main`.

## Problem Context

- PR #2203 added a cache guard source copy and plugin-distributed mirrors.
- A generated Copilot CLI lib mirror was missed, so the existing agent-only validation did not catch the drift.
- `build_all.py --check` needed to catch staged generated-output drift, including regenerated files that reappear as untracked paths.
- Main now provides `build/scripts/check_plugin_manifest_parity.py` and its dedicated tests. This PR no longer introduces the superseded parity validator.

## Session Protocol Compliance

- [x] Read HANDOFF.md.
- [x] Read AGENTS.md and CLAUDE.md.
- [x] Read relevant ADRs: ADR-006, ADR-008, ADR-035, ADR-042.
- [x] Session log created.
- [x] Branch verified: `fix/2222-drift-detection-build-all`.
- [x] Bot identity verified: rjmurillo-bot authenticated.

## Design Decision

**Final design after merging main**: Reuse the existing manifest parity checker from `main` and keep this PR focused on the build-all drift detection gap.

**Rationale**:

- `build_all.py --check` is the canonical full-artifact freshness gate.
- The untracked-file union in `_git_diff_paths` catches the #2222 failure shape where generator-owned files are deleted, regenerated, and otherwise missed by `git diff --name-only` alone.
- The manifest parity checker and its tests already exist on `main`, so keeping the old validator in this PR would duplicate the rule and create review noise.
- `validate-generated-agents.yml` now calls the current parity checker name, avoiding a stale workflow reference.

## Work Completed

### Phase 1: Build-all staleness gate

- [x] Updated `build/scripts/build_all.py` so `_git_diff_paths` unions tracked diffs with untracked, non-ignored files.
- [x] Preserved fail-closed behavior: staleness in generator-owned outputs exits 2.

### Phase 2: Regression tests

- [x] Added `tests/build_scripts/test_build_all.py` coverage for tracked drift and untracked regenerated-output drift.
- [x] Covered the negative path that used to miss #2222-class drift.

### Phase 3: CI integration

- [x] Updated `validate-generated-agents.yml` to call `build/scripts/check_plugin_manifest_parity.py`.
- [x] Removed the superseded parity validator and test after merging main.

### Phase 4: Verification

- [x] `uv run pytest tests/test_check_plugin_manifest_parity.py tests/test_pr_description.py tests/workflows/test_agent_review_cache_guards.py`
- [x] `python3 build/scripts/build_all.py --check`
- [x] `python3 build/scripts/check_plugin_manifest_parity.py`
- [x] `python3 scripts/validation/pr_description.py --pr-number 2285 --ci`
- [x] Local drift proof: staged drift in a generated Copilot agent caused `python3 build/scripts/build_all.py --check` to exit 2 and report the stale generated path.

## Files Modified In Final PR Diff

- `.agents/sessions/2026-06-02-session-01-issue-2222-ci-gap.md`
- `.github/workflows/validate-generated-agents.yml`
- `build/scripts/build_all.py`
- `tests/build_scripts/test_build_all.py`

## Delivery Summary

- **PR**: #2285 - <https://github.com/rjmurillo/ai-agents/pull/2285>
- **Branch**: `fix/2222-drift-detection-build-all`
- **Issue**: Fixes #2222
- **Result**: build-all drift now fails loudly on generated-output staleness instead of passing when regenerated files become untracked.
