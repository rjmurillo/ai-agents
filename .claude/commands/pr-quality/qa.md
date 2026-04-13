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

Run the qa quality gate locally on your current changes before pushing.

## Context

### Branch Information

Use the Bash tool to run `git branch --show-current` to determine the current branch.

Use $ARGUMENTS as the base branch if provided, otherwise default to `main`.

### Review Criteria

Apply the criteria from: @.github/prompts/pr-quality-gate-qa.md

### Changed Files

Use the Bash tool to run `git diff "<base_branch>" --name-only` to list changed files.

### Full Diff

Use the Bash tool to run `git diff "<base_branch>"` to obtain the full diff.

## Output Format

Provide your verdict in EXACTLY this format. Do not add preambles, explanations, or additional text before the verdict:

```text
VERDICT: [PASS|WARN|CRITICAL_FAIL]
MESSAGE: [One sentence summary]

[Detailed findings following prompt structure]
```

Then emit a fenced JSON block conforming to `.agents/schemas/pr-quality-gate-output.schema.json` with `"agent": "qa"`.
