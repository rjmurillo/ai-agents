---
description: Run all PR quality gates locally on uncommitted changes before pushing
argument-hint: --base BRANCH
---

# PR Quality Gate - All Reviews (Local)

Run all quality gates locally on your current changes before pushing. This meta-command executes all 6 agent reviews sequentially.

## Context

### Branch Information

- Current branch: !`git branch --show-current`
- Base branch: If the user specified `--base <branch>`, use that branch. Otherwise default to `main`.

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

### Changed Files

Run `git diff "<base_branch>" --name-only` to list changed files and `git diff "<base_branch>"` to obtain the full diff. All 6 agent reviews score against this diff.

## Reasoning Protocol

For every axis in every agent, before scoring or emitting any verdict, reason step-by-step:

1. What does the diff change? Read the diff, not the description.
2. What invariant does each criterion protect?
3. What evidence in the diff supports or contradicts a PASS verdict?

Do not emit a verdict without working through all three. Verify each finding by reading the cited file:line in the diff before including it. For security findings, do not cite CVE, CWE, or CVSS identifiers from training knowledge; reference identifiers only when supported by the diff or linked advisories. Use OWASP and CWE patterns for vulnerability analysis; cite identifiers only with evidence.

This step-by-step reasoning is internal. Do not emit it. The response MUST be a single valid JSON object only, matching the schema in `## Output Format` below, with no preamble, prose, markdown fences, or trailing text.

## Output Bounds

Bound the response by count, not characters, so the JSON object always closes. Cap findings at 10 items per severity per agent. When near the limit, drop the lowest-severity findings first and shorten the top-level `summary` rather than truncating mid-object. Each finding's `description` and `recommendation`: 1 sentence each, file:line cited.

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
