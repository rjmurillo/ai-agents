# Agent Workflow Skills

## Skill-Agent-Infra-001: Agent Infrastructure Verification

**Statement**: Check Copilot CLI availability before invoking architect agent; exit code 1 may indicate infrastructure failure

**Context**: Before invoking agents that depend on Copilot CLI or other infrastructure

**Evidence**: Session 38 - architect agent failed with exit code 1 due to Copilot CLI access issue on rjmurillo-bot service account. This was an infrastructure issue, not a code quality problem.

**Atomicity**: 88%

**Source**: Session 38 retrospective (2025-12-20)

---

## Skill-Agent-Diagnosis-001: Agent Error Type Distinction

**Statement**: Distinguish agent execution errors (environment) from agent findings (code quality); infrastructure failures should not block PR merge

**Context**: When agent invocations fail during PR workflows

**Evidence**: PR #121 merged despite architect failure. Analysis showed Copilot CLI access issue (infrastructure) rather than code quality concern.

**Atomicity**: 90%

**Source**: Session 38 retrospective (2025-12-20)

---

## Error Classification

| Error Type | Cause | Action |
|------------|-------|--------|
| **Infrastructure Error** | Copilot CLI access, MCP server down, API rate limit | Retry, skip agent, do not fail PR |
| **Agent Error** | Prompt issue, model timeout, parsing failure | Log, investigate, may retry |
| **Quality Finding** | Actual code issue found by agent | Block PR, require fix |

**Key Insight**: Exit code alone is insufficient. Parse error messages to classify:
- "access denied", "authentication", "CLI failed" → Infrastructure
- "timeout", "parsing", "model error" → Agent
- "CRITICAL_FAIL", "security concern", "bug found" → Quality

---

## Pre-Invocation Health Check Pattern

```bash
# Check Copilot CLI availability
if ! command -v copilot &> /dev/null; then
  echo "::warning::Copilot CLI not available - skipping agent"
  exit 0  # Don't fail workflow
fi

# Check MCP servers
if ! mcp__serena__check_onboarding_performed 2>/dev/null; then
  echo "::warning::Serena MCP not responding - using fallback"
fi
```
