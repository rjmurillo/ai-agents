---
description: Run roadmap quality gate locally on uncommitted changes before pushing
argument-hint: --base BRANCH
---

# PR Quality Gate - Roadmap Review (Local)

Run the roadmap quality gate locally on your current changes before pushing.

## Context

### Branch Information

- Current branch: !`git branch --show-current`
- Base branch: ${1:-main}

### Review Criteria

Apply the roadmap review criteria from the shared prompt file.

{{file ".github/prompts/pr-quality-gate-roadmap.md"}}

### Changed Files

!`git diff HEAD --name-only`

### Full Diff

!`git diff HEAD`

## Instructions

1. Assess strategic alignment and user value
2. Evaluate feature completeness and scope
3. Check for proper documentation
4. Verify business impact justification
5. Output verdict in the required format

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
