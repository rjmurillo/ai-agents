---
number: 200
title: "refactor: Rename GitHubHelpers.psm1 to remove -Helpers suffix"
state: OPEN
created_at: 12/20/2025 15:27:33
author: rjmurillo-bot
labels: []
assignees: []
milestone: null
url: https://github.com/rjmurillo/ai-agents/issues/200
---

# refactor: Rename GitHubHelpers.psm1 to remove -Helpers suffix

## Summary

The `GitHubHelpers.psm1` module uses the "-Helpers" suffix which is a code smell indicating unclear responsibilities.

**Source**: PR #93 review comment from @rjmurillo

## Current State

- Module: `.claude/skills/github/modules/GitHubHelpers.psm1`
- Contains: Authentication, repo resolution, error handling utilities

## Proposed Options

1. **Rename to focused name**: `GitHubCore.psm1` or `GitHubUtilities.psm1`
2. **Split into focused modules**:
   - `GitHubAuth.psm1` - Authentication functions
   - `GitHubRepo.psm1` - Repository resolution
   - `GitHubError.psm1` - Error handling utilities

## Acceptance Criteria

- [ ] Module renamed or split with clear single responsibility
- [ ] All references updated across scripts and tests
- [ ] Tests pass after rename

## Related

- PR #93 - Source of feedback

