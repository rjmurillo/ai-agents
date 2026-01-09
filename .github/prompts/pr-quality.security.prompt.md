---
title: Security Review (Local)
description: Run security quality gate locally on uncommitted changes before pushing
argument-hint: [--base BRANCH]
---

# PR Quality Gate - Security Review (Local)

Run the security quality gate locally on your current changes before pushing.

## Context

### Branch Information

- Current branch: !`git branch --show-current`
- Base branch: ${1:-main}

### Review Criteria

Apply the security review criteria from the shared prompt file.

{{file ".github/prompts/pr-quality-gate-security.md"}}

### Changed Files

!`git diff HEAD --name-only`

### Full Diff

!`git diff HEAD`

## Instructions

1. Analyze the diff above for security vulnerabilities per OWASP Top 10
2. Check for secrets exposure (API keys, passwords, tokens)
3. Identify security anti-patterns
4. Output verdict in the required format

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
