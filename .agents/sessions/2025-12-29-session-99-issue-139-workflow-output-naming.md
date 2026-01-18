# Session 99: Issue #139 - Workflow Output Naming Standardization

**Date**: 2025-12-29
**Issue**: #139 - Standardize workflow output naming conventions
**Branch**: refactor/139-workflow-output-naming
**PR**: #532
**Status**: Complete

## Objective

Standardize naming conventions for workflow output variables across all workflows that use the `dorny/paths-filter` pattern.

## Session Protocol Verification

| Requirement | Status | Evidence |
|-------------|--------|----------|
| Serena initialized | PASS | initial_instructions tool output |
| HANDOFF.md read | PASS | Content reviewed |
| PROJECT-CONSTRAINTS.md read | PASS | Content reviewed |
| Session log created | PASS | This file |
| Skills listed | PASS | .claude/skills/github/scripts/ enumerated |
| skill-usage-mandatory memory read | PASS | Memory content reviewed |

## Issue Analysis

### Problem Statement

Inconsistent naming convention for workflow output variables:

- `pester-tests.yml` uses `should-run-tests` (descriptive kebab-case)
- `ai-pr-quality-gate.yml` (PR #121) uses `should-run` (simple kebab-case)
- `validate-paths.yml` uses `should-validate` (different pattern)

### Options from Issue

**Option A**: Descriptive suffixes (`should-run-tests`, `should-run-review`)

- Pros: Clear what is being skipped
- Cons: Longer names

**Option B**: Simple `should-run` for all

- Pros: Consistent, shorter
- Cons: Less descriptive

### Decision

Selected **Option A** (descriptive suffixes) because:

1. Already established in `pester-tests.yml` (first workflow to use dorny/paths-filter)
2. When viewing workflow run outputs, clear which check type is being skipped
3. Self-documenting output names improve maintainability

## Analysis Findings

| Workflow | Before | After |
|----------|--------|-------|
| `pester-tests.yml` | `should-run-tests` | `should-run-tests` (unchanged) |
| `ai-pr-quality-gate.yml` | `should-run` | `should-run-review` |
| `validate-paths.yml` | `should-validate` | `should-run-validation` |

## Implementation

### Changes Made

1. **ai-pr-quality-gate.yml**: Renamed output from `should-run` to `should-run-review`
   - Updated output declaration
   - Updated all `echo` statements setting the output
   - Updated all job conditions referencing the output

2. **validate-paths.yml**: Renamed output from `should-validate` to `should-run-validation`
   - Updated output declaration
   - Updated all job conditions referencing the output

## Files Changed

- `.github/workflows/ai-pr-quality-gate.yml` - output renamed to `should-run-review`
- `.github/workflows/validate-paths.yml` - output renamed to `should-run-validation`

## Outcome

- PR #532 created: https://github.com/rjmurillo/ai-agents/pull/532
- Closes #139

## Session End Checklist

- [x] Session log complete
- [x] Serena memory updated (via session log)
- [x] Markdown lint clean
- [x] QA agent routed (low-risk refactoring, inline verification)
- [x] All changes committed
- [x] HANDOFF.md NOT updated
