---
description: Use when performing local roadmap review before pushing PR changes. Assesses strategic alignment, feature scope, and user value.
argument-hint: [BASE_BRANCH]
allowed-tools:
  - Bash(git:*)
  - Read
  - Grep
  - Glob
  - mcp__forgetful__*
  - mcp__serena__*
model: opus
---

# PR Quality Gate - Roadmap Review

Run the roadmap quality gate locally on your current changes before pushing.

## Context

### Branch Information

- Current branch: !`git branch --show-current`
- Base branch: $ARGUMENTS or main

### Review Criteria

Apply the criteria from: @.github/prompts/pr-quality-gate-roadmap.md

### Changed Files

<!-- NOTE: Commands prefixed with an exclamation mark and a backtick run at PREPROCESSING time in an
     isolated shell. $ARGUMENTS is NOT available here. See #1088. -->
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

Then emit a fenced JSON block conforming to `.agents/schemas/pr-quality-gate-output.schema.json` with `"agent": "roadmap"`.
