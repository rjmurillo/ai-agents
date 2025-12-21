---
number: 188
title: "feat: Add PSScriptAnalyzer to pre-commit hook"
state: OPEN
created_at: 12/20/2025 12:37:13
author: rjmurillo-bot
labels: ["enhancement", "priority:P0"]
assignees: []
milestone: null
url: https://github.com/rjmurillo/ai-agents/issues/188
---

# feat: Add PSScriptAnalyzer to pre-commit hook

## Context

From Session 36 retrospective:

**Root Cause**: Syntax error in Get-PRContext.ps1 was committed without detection due to lack of pre-commit validation.

**Pattern**: Variable interpolation bug (`$PullRequest:` instead of `$($PullRequest):`) caused syntax error that should have been caught before commit.

## Objective

Add PSScriptAnalyzer static analysis to pre-commit hook to prevent PowerShell syntax errors and common issues from being committed.

## Acceptance Criteria

- [ ] PSScriptAnalyzer integrated into pre-commit hook
- [ ] Runs on all staged .ps1 and .psm1 files
- [ ] Blocks commit if critical or error-level issues found
- [ ] Provides clear output showing which files failed and why
- [ ] Does not slow down commit process excessively (less than 5s for typical commit)

## Technical Details

**Severity Levels**:
- Error: BLOCK commit
- Warning: ALLOW but display
- Information: Silent

**Ruleset**: Use PSScriptAnalyzer default rules plus:
- PSAvoidUsingPositionalParameters
- PSAvoidUsingInvokeExpression
- PSAvoidUsingCmdletAliases
- PSUseConsistentIndentation
- PSUseConsistentWhitespace

## References

- Session 36 retrospective
- Skill-PowerShell-001: Variable interpolation safety (95% atomicity)
- Skill-CI-001: Pre-commit syntax validation (92% atomicity)

## Priority

P0 (CRITICAL) - Prevents syntax errors from entering codebase

## Effort Estimate

30 minutes


