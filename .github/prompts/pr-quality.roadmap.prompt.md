---
description: Run roadmap quality gate locally on uncommitted changes before pushing
argument-hint: --base BRANCH
---

# PR Quality Gate - Roadmap Review (Local)

Run the roadmap quality gate locally on your current changes before pushing.

## Context

### Branch Information

- Current branch: !`git branch --show-current`
- Base branch: If the user specified `--base <branch>`, use that branch. Otherwise default to `main`.

### Review Criteria

Apply the roadmap review criteria from the shared prompt file.

{{file ".github/prompts/pr-quality-gate-roadmap.md"}}

### Changed Files

Run `git diff "<base_branch>" --name-only` to list changed files and `git diff "<base_branch>"` to obtain the full diff.

## Reasoning Protocol

Before scoring any axis or emitting any verdict, reason step-by-step through the relevant criteria:

1. What does the diff change? Read the diff, not the description.
2. What invariant does each criterion protect (strategic alignment, scope discipline, user value justification)?
3. What evidence in the diff supports or contradicts a PASS verdict?

Do not emit a verdict without working through all three. Verify each finding by reading the cited file:line and the linked issue or roadmap before including it.

This step-by-step reasoning is internal. Do not emit it. Follow the output format specified in `## Output Format (REQUIRED)` below.

## Instructions

1. Assess strategic alignment and user value
2. Evaluate feature completeness and scope
3. Check for proper documentation
4. Verify business impact justification
5. Output verdict in the required format

## Output Bounds

Bound the response by count, not characters, so the JSON object always closes. Cap findings at 10 items per severity. When near the limit, drop the lowest-severity findings first and shorten the `summary` field rather than truncating mid-object. Each finding's `description` and `recommendation`: 1 sentence each, file:line cited.

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
