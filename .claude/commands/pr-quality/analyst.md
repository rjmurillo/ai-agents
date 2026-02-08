---
description: Use when performing local analyst review before pushing PR changes. Assesses code quality, impact analysis, and maintainability.
argument-hint: [BASE_BRANCH]
allowed-tools:
  - Bash(git:*)
  - Read
  - Grep
  - Glob
  - mcp__forgetful__*
  - mcp__serena__*
model: sonnet
---

# PR Quality Gate - Analyst Review

Run the analyst quality gate locally on your current changes before pushing.

## Context

### Branch Information

- Current branch: !`git branch --show-current`
- Base branch: $ARGUMENTS or main

### Review Criteria

Apply the criteria from: @.github/prompts/pr-quality-gate-analyst.md

### Changed Files

!`_BASE="${ARGUMENTS:-main}"; git diff "$_BASE" --name-only`

### Full Diff

!`_BASE="${ARGUMENTS:-main}"; git diff "$_BASE"`

## Output Format

Provide your verdict in EXACTLY this format. Do not add preambles, explanations, or additional text before the verdict:

```text
VERDICT: [PASS|WARN|CRITICAL_FAIL]
MESSAGE: [One sentence summary]

[Detailed findings following prompt structure]
```
