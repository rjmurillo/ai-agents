---
description: Quality assurance - invoke QA agent, validate test coverage, check acceptance criteria, and report results.
argument-hint: [--coverage-threshold N] <verification-scope>
allowed-tools:
  - Bash(pwsh .claude/skills/workflow/scripts/*)
  - Bash(git:*)
  - Bash(ls:*)
  - Read
  - mcp__agent_orchestration__invoke_agent
  - mcp__agent_orchestration__track_handoff
model: sonnet
---

# /3-qa — Quality Assurance

Invoke the QA agent and validate implementation quality.

## Context

Implementation artifacts: !`ls -1 .agents/sessions/ | tail -3`

Current branch: !`git branch --show-current`

## Invocation

```bash
pwsh .claude/skills/workflow/scripts/Invoke-QA.ps1 $ARGUMENTS
```

## What This Command Does

1. Invoke `qa` agent via Agent Orchestration MCP
2. Validate test coverage against threshold (default: 80%)
3. Check acceptance criteria from planning artifacts
4. Report pass/fail with details
5. Track handoff back to orchestrator

## Arguments

- `--coverage-threshold N`: Minimum coverage percentage (default: 80).
- Remaining text: Verification scope.

## Related

- ADR-006: `.agents/architecture/ADR-006-thin-workflows-testable-modules.md`
