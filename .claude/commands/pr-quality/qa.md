---
description: Use when performing local QA review before pushing PR changes. Evaluates test coverage, error handling, and code quality.
argument-hint: [--base BRANCH]
allowed-tools: [Bash(git:*), Read, Grep, Glob, mcp__forgetful__*, mcp__serena__*]
model: sonnet
---

# PR Quality Gate - QA Review

Run the QA quality gate locally on your current changes before pushing.

## Context

### Branch Information

- Current branch: !`git branch --show-current`
- Base branch: ${1:-main}

### Changed Files

!`git diff HEAD --name-only`

### Full Diff

!`git diff HEAD`

### Review Criteria

Apply the criteria from: @.github/prompts/pr-quality-gate-qa.md

## Output Format

Provide verdict in this format:

```text
VERDICT: [PASS|WARN|CRITICAL_FAIL]
MESSAGE: [One sentence summary]

[Detailed findings following prompt structure]
```
