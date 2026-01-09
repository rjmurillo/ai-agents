---
description: Use when performing local architecture review before pushing PR changes. Reviews design patterns, system boundaries, coupling/cohesion, and ADR compliance.
argument-hint: [--base BRANCH]
allowed-tools: [Bash(git:*), Read, Grep, Glob, mcp__forgetful__*, mcp__serena__*]
model: opus
---

# PR Quality Gate - Architect Review

Run the architect quality gate locally on your current changes before pushing.

## Context

### Branch Information

- Current branch: !`git branch --show-current`
- Base branch: ${1:-main}

### Changed Files

!`git diff HEAD --name-only`

### Full Diff

!`git diff HEAD`

### Review Criteria

Apply the criteria from: @.github/prompts/pr-quality-gate-architect.md

## Output Format

Provide verdict in this format:

```text
VERDICT: [PASS|WARN|CRITICAL_FAIL]
MESSAGE: [One sentence summary]

[Detailed findings following prompt structure]
```
