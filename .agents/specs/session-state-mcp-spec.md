# Session State MCP Technical Specification

> **Status**: Draft
> **Version**: 0.1.0
> **ADR**: [ADR-011](../architecture/ADR-011-session-state-mcp.md)
> **Date**: 2025-12-21

## Overview

This specification defines the Session State MCP implementation, focusing on Serena integration and the verification-based gate enforcement pattern.

---

## Architecture Diagram

```
┌────────────────────────────────────────────────────────────────────┐
│                          Claude Code CLI                            │
│  ┌──────────────────────┐    ┌──────────────────────────────────┐  │
│  │   Agent Conversation │    │         MCP Registry              │  │
│  │                      │    │  ┌─────────────┐ ┌─────────────┐  │  │
│  │  "session_start()"   │───>│  │ Session     │ │ Serena      │  │  │
│  │                      │    │  │ State MCP   │ │ MCP         │  │  │
│  │  "validate_gate()"   │    │  └──────┬──────┘ └──────┬──────┘  │  │
│  └──────────────────────┘    │         │               │         │  │
│                              └─────────┼───────────────┼─────────┘  │
│                                        │               │            │
│                                        v               v            │
│                              ┌─────────────────────────────────┐   │
│                              │     Serena Integration Layer     │   │
│                              │  ┌──────────────────────────┐   │   │
│                              │  │ Memory Operations        │   │   │
│                              │  │ - write_memory()         │   │   │
│                              │  │ - read_memory()          │   │   │
│                              │  │ - edit_memory()          │   │   │
│                              │  │ - list_memories()        │   │   │
│                              │  └──────────────────────────┘   │   │
│                              └─────────────────┬───────────────┘   │
│                                                │                    │
└────────────────────────────────────────────────┼────────────────────┘
                                                 │
                                                 v
                              ┌──────────────────────────────────┐
                              │         .serena/memories/         │
                              │  ┌────────────────────────────┐  │
                              │  │ session-current-state.md   │  │
                              │  │ session-history.md         │  │
                              │  │ session-violations-log.md  │  │
                              │  └────────────────────────────┘  │
                              └──────────────────────────────────┘
```

---

## Serena Integration Details

### Memory Naming Convention

| Memory Name | Purpose | Lifecycle |
|-------------|---------|-----------|
| `session-current-state` | Active session state machine | Created at session_start, deleted at session_end |
| `session-history` | Cross-session context (last 10) | Persistent, appended each session |
| `session-violations-log` | Protocol violation audit trail | Persistent, appended on violations |

### Memory Formats

#### session-current-state

```markdown
# Session State

## Metadata

- **Session ID**: 2025-12-21-session-01
- **Objective**: Design Session State MCP
- **Branch**: feat/mcp-updates
- **Starting Commit**: e846d7e
- **Started At**: 2025-12-21T14:30:00Z
- **Current Phase**: WORKING

## Phase Status

| Phase | Status | Evidence |
|-------|--------|----------|
| SERENA_INIT | COMPLETE | Tool output in transcript |
| SKILL_VALIDATION | COMPLETE | Listed 12 scripts |
| CONTEXT_RETRIEVAL | COMPLETE | HANDOFF.md hash: abc123 |
| SESSION_LOG | COMPLETE | .agents/sessions/2025-12-21-session-01.md |
| GIT_STATE | COMPLETE | Clean, main branch |

## Checklist (Start)

| Req | Step | Status | Evidence |
|-----|------|--------|----------|
| MUST | Initialize Serena: mcp__serena__activate_project | [x] | Tool output present |
| MUST | Initialize Serena: mcp__serena__initial_instructions | [x] | Tool output present |
| MUST | Read .agents/HANDOFF.md | [x] | Content in context |
| MUST | Create session log | [x] | File exists |
| MUST | List skill scripts | [x] | 12 scripts found |
| MUST | Read skill-usage-mandatory | [x] | Content loaded |
| MUST | Read PROJECT-CONSTRAINTS.md | [x] | Content loaded |
| SHOULD | Search relevant memories | [x] | 3 memories read |
| SHOULD | Verify git status | [x] | Clean |
| SHOULD | Note starting commit | [x] | e846d7e |

## Checklist (End)

| Req | Step | Status | Evidence |
|-----|------|--------|----------|
| MUST | Update .agents/HANDOFF.md | [ ] | |
| MUST | Complete session log | [ ] | |
| MUST | Run markdown lint | [ ] | |
| MUST | Route to qa agent | [ ] | |
| MUST | Commit all changes | [ ] | |
| SHOULD | Update PROJECT-PLAN.md | [ ] | |
| SHOULD | Invoke retrospective | [ ] | |
| SHOULD | Verify clean git status | [ ] | |
```

#### session-history

```markdown
# Session History

## Recent Sessions (Last 10)

### 2025-12-20-session-03

- **Objective**: PR batch review
- **Outcome**: COMPLETE
- **Commit SHA**: 981ebf7
- **Key Decisions**:
  - Merged PRs #140, #212, #211, #147
  - Deferred security review to next session
- **Next Session Notes**: Continue with Epic #183 planning

### 2025-12-20-session-02

- **Objective**: Security remediation for ai-issue-triage
- **Outcome**: COMPLETE
- **Commit SHA**: 51101b5
- **Key Decisions**:
  - CWE-20/CWE-78 remediated
  - Added input validation to workflow
- **Next Session Notes**: Run full regression test
```

#### session-violations-log

```markdown
# Session Violations Log

## Purpose

Audit trail of protocol violations for retrospective analysis and skill extraction.

## Violations

### 2025-12-21-session-01

| Timestamp | Phase | Requirement | Severity | Recovery |
|-----------|-------|-------------|----------|----------|
| (none recorded) | | | | |

### 2025-12-18-session-15

| Timestamp | Phase | Requirement | Severity | Recovery |
|-----------|-------|-------------|----------|----------|
| 14:23:00 | SKILL_VALIDATION | MUST read skill-usage-mandatory | CRITICAL | Read at 14:25:00 |
| 14:30:00 | SKILL_VALIDATION | MUST check existing skills | CRITICAL | User intervention |
| 14:45:00 | SKILL_VALIDATION | MUST use skill not raw gh | CRITICAL | Reverted, used skill |
```

---

## Tool Implementation Details

### session_start Implementation

```typescript
async function session_start(params: SessionStartParams): Promise<SessionStartResult> {
  // 1. Check if session already active
  const existing = await serena.read_memory("session-current-state");
  if (existing) {
    throw new Error("Session already active. Call session_end() first.");
  }

  // 2. Auto-detect git state if not provided
  const branch = params.branch ?? await exec("git branch --show-current");
  const starting_commit = params.starting_commit ?? await exec("git rev-parse --short HEAD");

  // 3. Generate session ID
  const today = new Date().toISOString().split('T')[0];
  const existingSessions = await glob(`.agents/sessions/${today}-session-*.md`);
  const sessionNum = (existingSessions.length + 1).toString().padStart(2, '0');
  const session_id = `${today}-session-${sessionNum}`;

  // 4. Initialize state
  const state: SessionState = {
    session_id,
    objective: params.objective,
    branch,
    starting_commit,
    started_at: new Date().toISOString(),
    current_phase: "INIT",
    phases_completed: [],
    checklist: loadChecklistFromProtocol(),
    evidence: {},
    violations: []
  };

  // 5. Persist via Serena
  await serena.write_memory("session-current-state", formatAsMarkdown(state));

  // 6. Return initial state
  return {
    session_id,
    phase: "INIT",
    blocked_until: ["SERENA_INIT", "SKILL_VALIDATION", "CONTEXT_RETRIEVAL"],
    checklist: state.checklist
  };
}
```

### validate_gate Implementation

```typescript
async function validate_gate(params: ValidateGateParams): Promise<ValidateGateResult> {
  const state = await loadState();
  const protocol = await loadProtocol();

  const phase = params.phase;
  const requirement = protocol.requirements[phase];

  // Phase-specific validation logic
  let status: "PASS" | "FAIL" | "SKIPPED" = "FAIL";
  let evidence: string | null = null;

  switch (phase) {
    case "SERENA_INIT":
      // Check if Serena tools are responding
      try {
        await serena.list_memories();
        status = "PASS";
        evidence = "Serena MCP responding";
      } catch {
        status = "FAIL";
        evidence = "Serena MCP not available";
      }
      break;

    case "SKILL_VALIDATION":
      // Check skill directory and mandatory memory
      const skillsExist = await fileExists(".claude/skills/github/scripts");
      const memoryRead = state.evidence["skill-usage-mandatory-read"];
      if (skillsExist && memoryRead) {
        status = "PASS";
        evidence = `Skills dir exists, memory read at ${memoryRead}`;
      }
      break;

    case "CONTEXT_RETRIEVAL":
      // Check HANDOFF.md was read (via content hash)
      const handoffHash = state.evidence["HANDOFF_HASH"];
      if (handoffHash) {
        status = "PASS";
        evidence = `HANDOFF.md hash: ${handoffHash}`;
      }
      break;

    case "SESSION_LOG":
      // Check session log file exists
      const logPath = `.agents/sessions/${state.session_id}.md`;
      if (await fileExists(logPath)) {
        status = "PASS";
        evidence = `Session log exists: ${logPath}`;
      }
      break;

    case "QA_VALIDATION":
      // Check for QA report OR docs-only skip
      const qaReport = await findQAReport(state.session_id);
      const isDocsOnly = await checkDocsOnly(state.starting_commit);
      if (qaReport) {
        status = "PASS";
        evidence = `QA report: ${qaReport}`;
      } else if (isDocsOnly) {
        status = "SKIPPED";
        evidence = "SKIPPED: docs-only";
      }
      break;

    // ... other phases
  }

  // Update state with validation result
  await updateStateEvidence(phase, { status, evidence });

  return {
    phase,
    requirement_level: requirement.level,
    status,
    evidence,
    blocking: requirement.blocking,
    message: formatMessage(phase, status, evidence)
  };
}
```

### Serena Tool Wrapper

```typescript
class SerenaIntegration {
  private prefix = "mcp__serena__";

  async write_memory(name: string, content: string): Promise<void> {
    await callTool(`${this.prefix}write_memory`, {
      memory_file_name: name,
      content: content
    });
  }

  async read_memory(name: string): Promise<string | null> {
    try {
      const result = await callTool(`${this.prefix}read_memory`, {
        memory_file_name: name
      });
      return result.content;
    } catch {
      return null;
    }
  }

  async edit_memory(name: string, needle: string, repl: string): Promise<void> {
    await callTool(`${this.prefix}edit_memory`, {
      memory_file_name: name,
      needle,
      repl,
      mode: "literal"
    });
  }

  async list_memories(): Promise<string[]> {
    const result = await callTool(`${this.prefix}list_memories`, {});
    return JSON.parse(result.memories);
  }
}
```

---

## State Machine Definition

### States

```typescript
enum SessionPhase {
  // Start phases
  INIT = "INIT",
  SERENA_READY = "SERENA_READY",
  SKILLS_VALIDATED = "SKILLS_VALIDATED",
  CONTEXT_LOADED = "CONTEXT_LOADED",
  READY = "READY",

  // Working phase
  WORKING = "WORKING",

  // End phases
  DOCUMENTING = "DOCUMENTING",
  QUALITY_CHECKED = "QUALITY_CHECKED",
  QA_COMPLETE = "QA_COMPLETE",
  COMPLETE = "COMPLETE",

  // Error states
  BLOCKED = "BLOCKED",
  VIOLATION = "VIOLATION"
}
```

### Transitions

```typescript
const TRANSITIONS: Record<SessionPhase, TransitionRule[]> = {
  [SessionPhase.INIT]: [
    { to: SessionPhase.SERENA_READY, gate: "SERENA_INIT", blocking: true }
  ],
  [SessionPhase.SERENA_READY]: [
    { to: SessionPhase.SKILLS_VALIDATED, gate: "SKILL_VALIDATION", blocking: true }
  ],
  [SessionPhase.SKILLS_VALIDATED]: [
    { to: SessionPhase.CONTEXT_LOADED, gate: "CONTEXT_RETRIEVAL", blocking: true }
  ],
  [SessionPhase.CONTEXT_LOADED]: [
    { to: SessionPhase.READY, gate: "SESSION_LOG", blocking: true }
  ],
  [SessionPhase.READY]: [
    { to: SessionPhase.WORKING, gate: "GIT_STATE", blocking: false }
  ],
  [SessionPhase.WORKING]: [
    { to: SessionPhase.DOCUMENTING, gate: "DOCS_UPDATE", blocking: false }
  ],
  [SessionPhase.DOCUMENTING]: [
    { to: SessionPhase.QUALITY_CHECKED, gate: "QUALITY_CHECKS", blocking: true }
  ],
  [SessionPhase.QUALITY_CHECKED]: [
    { to: SessionPhase.QA_COMPLETE, gate: "QA_VALIDATION", blocking: true }
  ],
  [SessionPhase.QA_COMPLETE]: [
    { to: SessionPhase.COMPLETE, gate: "GIT_COMMIT", blocking: true }
  ]
};
```

---

## Integration with Existing Tools

### Validate-SessionEnd.ps1 Compatibility

The Session State MCP complements (not replaces) the existing validator:

```powershell
# In Validate-SessionEnd.ps1, add optional MCP check
if (Test-SessionStateMCP) {
    # Fast path: query MCP for validation status
    $mcpResult = Invoke-MCPTool "session_state" "validate_gate" @{ phase = "ALL" }
    if ($mcpResult.status -eq "PASS") {
        Write-Output "OK: Session End validation passed (via MCP)"
        exit 0
    }
}

# Fallback: existing file-based validation
# ... (existing code)
```

### Claude Code Hooks Integration

```json
// .claude/hooks.json
{
  "on_session_start": {
    "tool": "session_state.session_start",
    "params": {
      "objective": "{{user_prompt}}"
    }
  },
  "on_tool_call": {
    "match": "mcp__serena__*",
    "tool": "session_state.record_evidence",
    "params": {
      "phase": "SERENA_INIT",
      "evidence_type": "tool_output",
      "evidence": "{{tool_output}}"
    }
  }
}
```

---

## Error Handling

### Serena Unavailable

```typescript
async function withSerenaFallback<T>(
  serenaOp: () => Promise<T>,
  fallbackOp: () => Promise<T>
): Promise<T> {
  try {
    return await serenaOp();
  } catch (error) {
    console.warn("Serena unavailable, using file fallback");
    return await fallbackOp();
  }
}

// Example usage
async function saveState(state: SessionState): Promise<void> {
  await withSerenaFallback(
    () => serena.write_memory("session-current-state", formatState(state)),
    () => writeFile(".agents/sessions/.session-state.json", JSON.stringify(state))
  );
}
```

### Violation Recovery

```typescript
async function handleViolation(phase: string, requirement: string): Promise<void> {
  // 1. Log violation
  const violation: Violation = {
    timestamp: new Date().toISOString(),
    phase,
    requirement,
    severity: getSeverity(requirement),
    recovery: null
  };

  await appendViolation(violation);

  // 2. Block further progress if MUST requirement
  if (requirement.startsWith("MUST")) {
    await transitionTo(SessionPhase.BLOCKED);
  }

  // 3. Return recovery instructions
  throw new SessionBlockedError({
    phase,
    requirement,
    recovery_steps: getRecoverySteps(phase)
  });
}
```

---

## Testing Strategy

### Unit Tests

```typescript
describe("session_start", () => {
  it("creates session state in Serena memory", async () => {
    const mockSerena = createMockSerena();
    const result = await session_start({ objective: "Test" });

    expect(mockSerena.write_memory).toHaveBeenCalledWith(
      "session-current-state",
      expect.stringContaining("Test")
    );
    expect(result.session_id).toMatch(/^\d{4}-\d{2}-\d{2}-session-\d{2}$/);
  });

  it("rejects if session already active", async () => {
    const mockSerena = createMockSerena({
      "session-current-state": "existing session"
    });

    await expect(session_start({ objective: "Test" }))
      .rejects.toThrow("Session already active");
  });
});

describe("validate_gate", () => {
  it("passes SERENA_INIT when Serena responds", async () => {
    const mockSerena = createMockSerena();
    mockSerena.list_memories.mockResolvedValue([]);

    const result = await validate_gate({ phase: "SERENA_INIT" });

    expect(result.status).toBe("PASS");
    expect(result.blocking).toBe(true);
  });

  it("fails SERENA_INIT when Serena unavailable", async () => {
    const mockSerena = createMockSerena();
    mockSerena.list_memories.mockRejectedValue(new Error("Connection refused"));

    const result = await validate_gate({ phase: "SERENA_INIT" });

    expect(result.status).toBe("FAIL");
  });
});
```

### Integration Tests

```powershell
# tests/Session-State-MCP.Integration.Tests.ps1
Describe "Session State MCP Integration" {
    BeforeAll {
        # Start MCP server
        $script:mcpProcess = Start-Process -NoNewWindow -PassThru node "dist/index.js"
        Start-Sleep -Seconds 2
    }

    AfterAll {
        Stop-Process $script:mcpProcess
    }

    It "completes full session lifecycle" {
        # Start session
        $start = Invoke-MCPTool "session_start" @{ objective = "Integration test" }
        $start.session_id | Should -Match "^\d{4}-\d{2}-\d{2}-session-\d{2}$"

        # Validate gates
        $gate1 = Invoke-MCPTool "validate_gate" @{ phase = "SERENA_INIT" }
        $gate1.status | Should -Be "PASS"

        # End session
        $end = Invoke-MCPTool "session_end" @{
            summary = "Integration test complete"
            skip_qa = $true
        }
        $end.status | Should -Be "COMPLETE"
    }
}
```

---

## Deployment

### Package Structure

```
session-state-mcp/
├── package.json
├── tsconfig.json
├── src/
│   ├── index.ts           # MCP entry point
│   ├── tools/
│   │   ├── session_start.ts
│   │   ├── validate_gate.ts
│   │   ├── advance_phase.ts
│   │   ├── record_evidence.ts
│   │   ├── session_end.ts
│   │   └── get_blocked_reason.ts
│   ├── resources/
│   │   ├── state.ts
│   │   ├── checklist.ts
│   │   ├── history.ts
│   │   └── violations.ts
│   ├── serena/
│   │   ├── integration.ts
│   │   └── fallback.ts
│   ├── state-machine/
│   │   ├── phases.ts
│   │   └── transitions.ts
│   └── protocol/
│       └── parser.ts      # Parse SESSION-PROTOCOL.md
├── tests/
│   ├── unit/
│   └── integration/
└── dist/                  # Compiled output
```

### Installation

```bash
# Add to Claude Code MCP config
claude mcp add session-state /path/to/session-state-mcp

# Or in settings.json
{
  "mcpServers": {
    "session-state": {
      "command": "node",
      "args": ["/path/to/session-state-mcp/dist/index.js"],
      "env": {
        "SERENA_PROJECT": "/home/richard/ai-agents"
      }
    }
  }
}
```

---

## Open Questions

1. **Should session_start auto-invoke Serena initialization?**
   - Pro: Single entry point, guaranteed order
   - Con: Hides the explicit tool call that agents should see

2. **How to handle mid-session crashes?**
   - Option A: session-current-state persists, next session resumes
   - Option B: Orphaned sessions auto-expire after 24h

3. **Should the MCP enforce or just report?**
   - Current design: Report + provide blocking mechanism
   - Alternative: Actually block tool calls until gates pass

---

## References

- [ADR-011: Session State MCP](../architecture/ADR-011-session-state-mcp.md)
- [SESSION-PROTOCOL.md](../SESSION-PROTOCOL.md)
- [MCP TypeScript SDK](https://github.com/modelcontextprotocol/typescript-sdk)
- [Serena MCP](https://github.com/cloudmcp/serena)
