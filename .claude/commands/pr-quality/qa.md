---
description: Use when performing local QA review before pushing PR changes. Evaluates test coverage, error handling, and code quality.
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

# PR Quality Gate - QA Review

Run the QA quality gate locally on your current changes before pushing.

## Context

### Branch Information

- Current branch: !`git branch --show-current`
- Base branch: $ARGUMENTS or main

### Review Criteria

Apply the criteria from: @.github/prompts/pr-quality-gate-qa.md

### Changed Files

!`git diff main --name-only`

### Full Diff

!`git diff main`

## Output Format

Provide your verdict in EXACTLY this format. Do not add preambles, explanations, or additional text before the verdict:

```text
VERDICT: [PASS|WARN|CRITICAL_FAIL]
MESSAGE: [One sentence summary]

[Detailed findings following prompt structure]
```
