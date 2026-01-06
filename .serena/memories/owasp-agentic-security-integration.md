# OWASP Agentic Applications Security Integration

> **Created**: 2026-01-04 (Session 308)
> **Related**: Session 307 (CWE-699), PR #752

## Purpose

Integration guidance for OWASP Top 10 for Agentic Applications (2026) into ai-agents security agent.

## Key Categories

| ID | Name | CWE Mapping | ai-agents Relevance |
|----|------|-------------|---------------------|
| ASI01 | Agent Goal Hijack | CWE-94, CWE-77 | Prompt injection in system prompts |
| ASI02 | Tool Misuse | CWE-22, CWE-78 | MCP tool parameter validation |
| ASI03 | Identity Abuse | CWE-269, CWE-284 | Agent privilege scope |
| ASI04 | Supply Chain | CWE-426, CWE-502 | MCP server validation |
| ASI05 | Code Execution | CWE-94, CWE-78 | ExpandString, Invoke-Expression |
| ASI06 | Memory Poisoning | CWE-1321, CWE-502 | Four-tier memory system |
| ASI07 | Inter-Agent Comms | CWE-319, CWE-345 | Task tool delegation (novel) |
| ASI08 | Cascading Failures | CWE-703, CWE-754 | Orchestrator error propagation |
| ASI09 | Trust Exploitation | CWE-346, CWE-451 | Human-agent checkpoints |
| ASI10 | Rogue Agents | CWE-284, CWE-269 | Agent allowlist (novel) |

## Priority Detection Patterns

### CRITICAL (M1)

1. **Untrusted input in system prompts** (ASI01)
   - Pattern: `$systemPrompt = "... $userInput ..."`
   - CWE: CWE-94

2. **Join-Path without containment** (ASI02)
   - Pattern: `Join-Path $base $userInput` without `Test-SafeFilePath`
   - CWE: CWE-22

3. **Invoke-Expression with variables** (ASI05)
   - Pattern: `Invoke-Expression "$cmd $args"`
   - CWE: CWE-78

### HIGH (M1)

4. **External goal/instruction loading** (ASI01)
   - Pattern: Loading agent behavior from external API
   - CWE: CWE-94

5. **ExpandString with external input** (ASI05)
   - Pattern: `$ExecutionContext.InvokeCommand.ExpandString($input)`
   - CWE: CWE-94

6. **Credentials in agent context** (ASI03)
   - Pattern: Tokens/secrets visible to agent memory
   - CWE: CWE-522

7. **Unvalidated MCP tool inputs** (ASI02)
   - Pattern: MCP tool parameters passed without validation
   - CWE: CWE-20

## ai-agents Existing Safeguards

| Safeguard | Addresses |
|-----------|-----------|
| Session protocol | ASI08 (bounded execution), ASI10 (audit trail) |
| Memory-first pattern | ASI10 (traceable decisions) |
| Orchestrator | ASI10 (explicit agent catalog) |
| HANDOFF.md read-only | ASI09 (prevents agent manipulation) |
| Skill library | ASI10 (no arbitrary code execution) |
| QA agent gate | ASI08 (validation checkpoint) |

## Recommended Enhancements

| Enhancement | Category | Priority |
|-------------|----------|----------|
| Add 15 agentic detection patterns to security.md | ASI01-05 | P0 |
| MCP server version pinning | ASI04 | P1 |
| Circuit breaker in orchestrator | ASI08 | P1 |
| Memory sanitization for imports | ASI06 | P2 |
| Agent allowlist enforcement | ASI10 | P2 |

## Novel Categories (Limited CWE Coverage)

Three categories represent genuinely new attack surfaces:

1. **ASI07 (Inter-Agent Comms)**: Traditional CWEs focus on human-system, not agent-agent
2. **ASI08 (Cascading Failures)**: Autonomous workflow propagation
3. **ASI10 (Rogue Agents)**: Goal-seeking behavior unique to AI agents

## References

- Analysis: `.agents/analysis/owasp-agentic-security-integration.md`
- CWE-699 Research: `.agents/analysis/cwe-699-framework-integration.md`
- Session 307: `.agents/sessions/2026-01-04-session-307-cwe699-research.md`
- Session 308: `.agents/sessions/2026-01-04-session-308-owasp-agentic-research.md`
