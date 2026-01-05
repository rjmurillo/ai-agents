# Session Log: PR 791 Duplicate Workflow Run Analysis

**Date**: 2026-01-05
**Session**: 01
**PR**: #791
**Branch**: `add-factory-workflows-1767593727986`
**Trigger**: PR review comment from @rjmurillo

## Session Context

**Request**: Analyze duplicate workflow run issue identified by Cursor in PR review comment on `.github/workflows/droid.yml:19`

**Reference**: User mentioned "dealing with a version of this over on PR 790"

## Investigation Summary

### Issue Identified

Cursor's PR review correctly identified that `.github/workflows/droid.yml` triggers on:
```yaml
issues:
  types: [opened, assigned]
```

But the workflow condition only checks if `@droid` is in the issue body/title, not which specific action triggered the event. This causes duplicate runs:

1. Issue opened with `@droid` in body → Workflow runs ✅
2. Same issue gets assigned → Workflow runs again ❌ (duplicate)

### Critical Finding

Found the same pattern in `.github/workflows/claude.yml:9`:
```yaml
issues:
  types: [opened, assigned, labeled]
```

This means the Claude workflow has the same issue (potentially 3x duplicate runs).

### Root Cause

The workflow conditions don't check `github.event.action` to distinguish between:
- `action: opened` - Should run if `@droid`/`@claude` in body
- `action: assigned` - Should only run if assignment itself triggers mention (e.g., `@me` pattern)
- `action: labeled` - Should only run if label-related trigger needed

### Analysis

**Impact**:
- Wasted CI resources
- Potential duplicate API calls to Factory AI / Anthropic
- Increased costs
- Possible duplicate comments/responses

**Legitimate Use Case for `assigned`**:
- `claude.yml` has `assignee_trigger: "@me"` configuration
- Intended to support "assign yourself to activate Claude" workflow
- However, current condition doesn't distinguish this from body mentions

## Recommendations Provided

### Short-term Fix (Simplest)
Remove `assigned` trigger from `droid.yml`:
```yaml
issues:
  types: [opened]
```

### Long-term Fix (Recommended)
Add action-specific conditions:
```yaml
(github.event_name == 'issues' && github.event.action == 'opened' && (contains(github.event.issue.body, '@droid') || contains(github.event.issue.title, '@droid')))
```

### Coordination Needed
- PR 790 likely addresses same issue for `claude.yml`
- Both PRs should use consistent fix pattern
- Check if Factory AI's action has built-in idempotency protection

## Outcome

**Status**: Analysis complete, recommendations provided

**Deliverables**:
- Comprehensive analysis posted to PR review comment
- Identified same issue in existing `claude.yml` workflow
- Provided short-term and long-term fix recommendations
- Noted permission limitation (cannot modify workflow files)

**Limitations**:
- Cannot modify `.github/workflows/` files due to GitHub App permissions
- Cannot access PR 790 details (gh command requires approval)
- Manual fix required by user or repository maintainer

## Files Analyzed

- `.github/workflows/droid.yml` (new in PR)
- `.github/workflows/droid-review.yml` (new in PR)
- `.github/workflows/claude.yml` (existing, same issue found)

## Knowledge Gained

**Pattern**: Multi-trigger workflows need action-specific conditions to prevent duplicate runs when the triggering content (body/title) persists across events.

**Best Practice**: Always check `github.event.action` when using multiple trigger types on the same event (e.g., `issues: [opened, assigned, labeled]`).

## Session Protocol Compliance

- [x] Read HANDOFF.md (Serena MCP unavailable in GitHub Actions context)
- [x] Created session log
- [x] Analysis complete
- [x] Recommendations provided via GitHub comment
- [ ] Commit session log (will complete at session end)

## Related Issues/PRs

- **PR #791**: Factory AI workflows (current)
- **PR #790**: Referenced by user as having "a version of this issue"
- **claude.yml**: Has same duplicate run issue (lines 9, 48-54)
