---
description: Use when performing local architecture review before pushing PR changes. Reviews design patterns, system boundaries, coupling/cohesion, and ADR compliance.
argument-hint: [--base BRANCH]
allowed-tools:
  - Bash(git:*)
  - Read
  - Grep
  - Glob
  - mcp__forgetful__*
  - mcp__serena__*
model: opus
---

# PR Quality Gate - Architect Review

Run the architect quality gate locally on your current changes before pushing.

## Context

### Branch Information

- Current branch: !`git branch --show-current`
- Base branch: ${1:-main}

### Review Criteria

Apply the criteria from: @.github/prompts/pr-quality-gate-architect.md

### Changed Files

!`git diff "${1:-main}" --name-only`

### Full Diff

!`git diff "${1:-main}"`

## Output Format

Provide your verdict in EXACTLY this format. Do not add preambles, explanations, or additional text before the verdict:

```text
VERDICT: [PASS|WARN|CRITICAL_FAIL]
MESSAGE: [One sentence summary]

[Detailed findings following prompt structure]
```
