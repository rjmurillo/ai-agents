---
type: task
id: TASK-001
title: Implement PR Context Gathering Scripts
status: done
priority: P0
complexity: M
estimate: 4h
related:
  - DESIGN-001
blocks:
  - TASK-002
  - TASK-003
assignee: implementer
created: 2025-12-30
updated: 2025-12-30
author: spec-generator
tags:
  - github-skill
  - powershell
---

# TASK-001: Implement PR Context Gathering Scripts

## Design Context

- DESIGN-001: PR Comment Processing Architecture (Component 1: Context Gatherer)

## Objective

Create PowerShell scripts in .claude/skills/github/scripts/pr/ that retrieve complete PR context, comments, and reviewer information using the GitHub CLI.

## Scope

**In Scope**:

- Get-PRContext.ps1: Retrieve PR metadata (title, body, state, files)
- Get-PRReviewComments.ps1: Retrieve review and issue comments with pagination
- Get-PRReviewers.ps1: Retrieve unique reviewer list

**Out of Scope**:

- Signal analysis (TASK-002)
- Classification logic (TASK-003)

## Acceptance Criteria

- [ ] Get-PRContext.ps1 returns structured PR metadata
- [ ] Get-PRReviewComments.ps1 handles pagination for large PRs
- [ ] Get-PRReviewComments.ps1 supports -IncludeIssueComments flag
- [ ] Get-PRReviewers.ps1 returns deduplicated reviewer list
- [ ] All scripts follow ADR-005 (PowerShell only)
- [ ] All scripts have parameter validation
- [ ] Pester tests exist for each script

## Files Affected

| File | Action | Description |
|------|--------|-------------|
| `.claude/skills/github/scripts/pr/Get-PRContext.ps1` | Create | PR metadata retrieval |
| `.claude/skills/github/scripts/pr/Get-PRReviewComments.ps1` | Create | Comment retrieval with pagination |
| `.claude/skills/github/scripts/pr/Get-PRReviewers.ps1` | Create | Reviewer enumeration |
| `.claude/skills/github/tests/PRScripts.Tests.ps1` | Modify | Add Pester tests |

## Implementation Notes

- Use `gh pr view --json` for metadata
- Use `gh api repos/{owner}/{repo}/pulls/{number}/comments` for review comments
- Use `gh api repos/{owner}/{repo}/issues/{number}/comments` for issue comments
- Handle pagination with `--paginate` or manual Link header parsing
- Return structured objects, not raw JSON strings

## Testing Requirements

- [ ] Unit tests for parameter validation
- [ ] Tests for pagination handling
- [ ] Tests for error conditions (PR not found, auth failure)
