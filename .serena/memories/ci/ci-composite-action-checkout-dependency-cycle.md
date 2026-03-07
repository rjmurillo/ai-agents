# CI: Composite Action Checkout Dependency Cycle

**Date**: 2026-01-09
**Session**: 02
**PR**: #845

## Problem

GitHub Actions composite actions referenced via `uses: ./path` require repository checkout BEFORE the action is loaded.

## Root Cause

The composite action `.github/actions/agent-review/action.yml` included `actions/checkout` as its first step. This created a dependency cycle:

1. GitHub Actions tries to load composite action file (at job setup time, before any steps run)
2. Composite action file doesn't exist yet (repository not checked out)
3. Job fails immediately with: `Can't find 'action.yml' under '.github/actions/agent-review'`

## Evidence

All 6 agent review jobs (security, qa, analyst, architect, devops, roadmap) failed with identical error at job setup, before any steps executed.

## Solution

Move checkout from composite action to calling workflow:

1. Add `actions/checkout` step to each agent job in calling workflow BEFORE composite action reference
2. Remove `actions/checkout` from composite action
3. Update composite action documentation with checkout requirement

## Pattern

**For local composite actions** (`uses: ./path`):

- Calling workflow MUST checkout repository BEFORE referencing the action
- Composite action MUST NOT include `actions/checkout` internally
- Document checkout requirement in composite action comments

## Related

- Session 02: `.agents/sessions/2026-01-09-session-02.md`
- PR #845: AI PR quality gate refactoring

## Keywords

github actions composite action local checkout dependency cycle uses path repository workflow ci
