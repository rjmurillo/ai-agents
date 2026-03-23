---
description: Security review - invoke security agent with OWASP Top 10 check, secret detection, and dependency audit.
argument-hint: [--owasp-only] [--secrets-only] <security-scope>
allowed-tools:
  - Bash(pwsh .claude/skills/workflow/scripts/*)
  - Bash(git:*)
  - Bash(ls:*)
  - Read
  - mcp__agent_orchestration__invoke_agent
  - mcp__agent_orchestration__track_handoff
model: opus
---

# /4-security — Security Review

Comprehensive security assessment using the security agent.

## Context

Implementation artifacts: !`ls -1 .agents/sessions/ | tail -3`

Current branch: !`git branch --show-current`

## Invocation

```bash
pwsh .claude/skills/workflow/scripts/Invoke-Security.ps1 $ARGUMENTS
```

## What This Command Does

1. Invoke `security` agent via Agent Orchestration MCP (model: opus per ADR-013)
2. OWASP Top 10 check (skipped with `--secrets-only`)
3. Secret detection scan (skipped with `--owasp-only`)
4. Dependency audit for known vulnerabilities
5. Generate security report with findings

## Arguments

- `--owasp-only`: Run only OWASP Top 10 check.
- `--secrets-only`: Run only secret detection.
- Remaining text: Security scope.

## Related

- ADR-013: `.agents/architecture/ADR-013-agent-orchestration-mcp.md`
