---
title: All Quality Gates (Local)
description: Run all PR quality gates locally on uncommitted changes before pushing
argument-hint: [--base BRANCH]
---

# PR Quality Gate - All Reviews (Local)

Run all quality gates locally on your current changes before pushing. This meta-command executes all 6 agent reviews sequentially.

## Context

### Branch Information

- Current branch: !`git branch --show-current`
- Base branch: ${1:-main}

### Changed Files

!`git diff HEAD --name-only`

### Full Diff

!`git diff HEAD`

## Execution Plan

Run the following reviews in sequence:

1. **Security Review** - OWASP Top 10, secrets detection
2. **QA Review** - Test coverage, code quality
3. **Analyst Review** - Code maintainability, bugs
4. **Architect Review** - Design patterns, ADR compliance
5. **DevOps Review** - CI/CD, infrastructure
6. **Roadmap Review** - Strategic alignment, user value

For each review, reference the corresponding criteria file:

- `.github/prompts/pr-quality-gate-security.md`
- `.github/prompts/pr-quality-gate-qa.md`
- `.github/prompts/pr-quality-gate-analyst.md`
- `.github/prompts/pr-quality-gate-architect.md`
- `.github/prompts/pr-quality-gate-devops.md`
- `.github/prompts/pr-quality-gate-roadmap.md`

## Output Format

```json
{
  "overall_verdict": "PASS|WARN|CRITICAL_FAIL",
  "agent_results": {
    "security": { "verdict": "...", "findings": [...] },
    "qa": { "verdict": "...", "findings": [...] },
    "analyst": { "verdict": "...", "findings": [...] },
    "architect": { "verdict": "...", "findings": [...] },
    "devops": { "verdict": "...", "findings": [...] },
    "roadmap": { "verdict": "...", "findings": [...] }
  },
  "summary": "string"
}
```

**Verdict Priority**: CRITICAL_FAIL > WARN > PASS

**Note**: This command validates **uncommitted changes** in your working directory (shift-left). For PR-committed changes, use the CI workflow.
