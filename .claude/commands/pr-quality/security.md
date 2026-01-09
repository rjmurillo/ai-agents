---
description: Use when performing local security review before pushing PR changes. Scans for vulnerabilities, secrets exposure, and security anti-patterns per OWASP Top 10.
argument-hint: [--base BRANCH]
allowed-tools: [Bash(git:*), Read, Grep, Glob, mcp__forgetful__*, mcp__serena__*]
model: sonnet
---

# PR Quality Gate - Security Review

Run the security quality gate locally on your current changes before pushing.

## Context

### Branch Information

- Current branch: !`git branch --show-current`
- Base branch: ${1:-main}

### Review Criteria

Apply the criteria from: @.github/prompts/pr-quality-gate-security.md

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
