---
description: Run DevOps quality gate locally on uncommitted changes before pushing
argument-hint: --base BRANCH
---

# PR Quality Gate - DevOps Review (Local)

Run the DevOps quality gate locally on your current changes before pushing.

## Context

### Branch Information

- Current branch: !`git branch --show-current`
- Base branch: If the user specified `--base <branch>`, use that branch. Otherwise default to `main`.

### Review Criteria

Apply the DevOps review criteria from the shared prompt file.

{{file ".github/prompts/pr-quality-gate-devops.md"}}

### Changed Files

Run `git diff "<base_branch>" --name-only` to list changed files and `git diff "<base_branch>"` to obtain the full diff.

## Reasoning Protocol

Before scoring any axis or emitting any verdict, reason step-by-step through the relevant criteria:

1. What does the diff change? Read the diff, not the description.
2. What invariant does each criterion protect (pinned actions, secret hygiene, reproducible builds, deployment safety)?
3. What evidence in the diff supports or contradicts a PASS verdict?

Do not emit a verdict without working through all three. Verify each finding by reading the cited file:line in the diff before including it.

## Instructions

1. Review CI/CD pipeline changes
2. Assess infrastructure and deployment configurations
3. Check for proper secrets management
4. Verify build and deployment patterns
5. Output verdict in the required format

## Output Bounds

Cap findings: at most 10 items per severity. Cap total output: 800 words or the JSON schema below, whichever ends first. Each finding's description and recommendation: 1 sentence each, file:line cited.

## Output Format (REQUIRED)

```json
{
  "verdict": "PASS|WARN|CRITICAL_FAIL",
  "findings": [
    {
      "severity": "critical|high|medium|low",
      "category": "string",
      "file": "path/to/file",
      "line": number,
      "description": "string",
      "recommendation": "string"
    }
  ],
  "summary": "string"
}
```

**Note**: This command validates **uncommitted changes** in your working directory (shift-left). For PR-committed changes, use the CI workflow.
