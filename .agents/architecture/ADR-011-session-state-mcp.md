# ADR-011: Session State MCP

## Status

Proposed

## Date

2025-12-21

## Context

The ai-agents project uses a multi-phase session protocol (SESSION-PROTOCOL.md) with RFC 2119 requirements. Evidence from retrospectives shows:

- **Trust-based compliance fails**: Session 15 had 5+ violations despite documentation
- **Verification-based BLOCKING gates achieve 100% compliance**: Phase 1 (Serena init) never violated
- **Manual validation is error-prone**: `Validate-SessionEnd.ps1` catches violations but only at session end
- **Cross-session context is fragile**: HANDOFF.md requires manual updates prone to conflicts in parallel sessions

The session protocol has 5 start phases and 4 end phases, each with MUST/SHOULD/MAY requirements:

| Phase | Name | Type | Key Gate |
|-------|------|------|----------|
| 1 | Serena Initialization | BLOCKING | Tool output in transcript |
| 1.5 | Skill Validation | BLOCKING | Skills listed in session log |
| 2 | Context Retrieval | BLOCKING | HANDOFF.md content in context |
| 3 | Session Log Creation | REQUIRED | File exists with template |
| 4 | Git State Verification | RECOMMENDED | Git state documented |
| End-1 | Documentation Update | REQUIRED | HANDOFF.md + session log updated |
| End-2 | Quality Checks | REQUIRED | Lint passes |
| End-2.5 | QA Validation | BLOCKING | QA report exists |
| End-3 | Git Operations | REQUIRED | Clean commit |

Currently, compliance checking is split between:
- Serena MCP (memories, code analysis)
- `Validate-SessionEnd.ps1` (post-hoc validation)
- Manual agent discipline (unreliable)

### Problem Statement

There is no **real-time state machine** enforcing protocol gates. Agents can skip phases, and violations are only caught at session end or through user intervention.

## Decision

Create a **Session State MCP** that:

1. Provides a state machine tracking session phases
2. Integrates with Serena for memory persistence
3. Exposes tools for gate validation and state transitions
4. Provides resources for session state visibility
5. Enforces BLOCKING gates programmatically

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Session State MCP                        │
├─────────────────────────────────────────────────────────────┤
│  TOOLS                           │  RESOURCES               │
│  ─────                           │  ─────────               │
│  session_start()                 │  session://state         │
│  validate_gate(phase)            │  session://checklist     │
│  advance_phase()                 │  session://history       │
│  record_evidence(phase, evidence)│  session://violations    │
│  session_end()                   │                          │
│  get_blocked_reason()            │                          │
├─────────────────────────────────────────────────────────────┤
│                    SERENA INTEGRATION                        │
│  ─────────────────────────────────────────────────────────  │
│  Memories:                                                   │
│  - session-state-{date}-{nn}.json (current state)           │
│  - session-history.json (cross-session context)             │
│  - session-violations.json (audit log)                      │
│                                                              │
│  Tools Used:                                                 │
│  - mcp__serena__write_memory (persist state)                │
│  - mcp__serena__read_memory (restore state)                 │
│  - mcp__serena__list_memories (find sessions)               │
└─────────────────────────────────────────────────────────────┘
```

## Tool Interface Design

### session_start

Initializes session state machine. MUST be called before any other session tool.

```typescript
interface SessionStartParams {
  objective: string;              // Session goal
  branch?: string;                // Git branch (auto-detected if omitted)
  starting_commit?: string;       // Starting commit SHA (auto-detected)
}

interface SessionStartResult {
  session_id: string;             // e.g., "2025-12-21-session-01"
  phase: "INIT";
  blocked_until: string[];        // Phases that must complete
  checklist: ChecklistItem[];     // Full checklist with status
}
```

### validate_gate

Checks if a BLOCKING gate requirement is satisfied. Returns pass/fail with evidence.

```typescript
interface ValidateGateParams {
  phase: "SERENA_INIT" | "SKILL_VALIDATION" | "CONTEXT_RETRIEVAL" |
         "SESSION_LOG" | "GIT_STATE" | "DOCS_UPDATE" | "QUALITY_CHECKS" |
         "QA_VALIDATION" | "GIT_COMMIT";
}

interface ValidateGateResult {
  phase: string;
  requirement_level: "MUST" | "SHOULD" | "MAY";
  status: "PASS" | "FAIL" | "SKIPPED";
  evidence: string | null;        // Verification evidence
  blocking: boolean;              // Whether this blocks next phase
  message: string;                // Human-readable status
}
```

**Gate Validation Logic:**

| Phase | Validation Method |
|-------|-------------------|
| SERENA_INIT | Check Serena tools are available |
| SKILL_VALIDATION | Check `.claude/skills/` exists and skill-usage-mandatory memory read |
| CONTEXT_RETRIEVAL | Check HANDOFF.md content hash in session state |
| SESSION_LOG | Check session log file exists at expected path |
| GIT_STATE | Check git status recorded in state |
| DOCS_UPDATE | Check HANDOFF.md modified timestamp > session start |
| QUALITY_CHECKS | Run markdownlint, check exit code |
| QA_VALIDATION | Check `.agents/qa/` for report matching session |
| GIT_COMMIT | Check git log for commit since starting_commit |

### advance_phase

Attempts to advance to next phase. Fails if BLOCKING requirements not met.

```typescript
interface AdvancePhaseParams {
  target_phase?: string;          // Optional: specific phase to advance to
  force?: boolean;                // Skip validation (logged as violation)
}

interface AdvancePhaseResult {
  previous_phase: string;
  current_phase: string;
  success: boolean;
  blocked_by?: string[];          // Unsatisfied requirements
  violations?: string[];          // If force=true, what was skipped
}
```

**State Machine Transitions:**

```
INIT ──[SERENA_INIT]──> INITIALIZED ──[SKILL_VALIDATION]──> SKILLS_READY
  │                                                              │
  │                    [CONTEXT_RETRIEVAL]                       │
  │                            │                                 │
  └────────────────────────────┴─────────────────────────────────┘
                               │
                               v
                          CONTEXT_LOADED ──[SESSION_LOG]──> READY
                                                              │
                               ┌──────────────────────────────┘
                               │
                               v
                            WORKING ──[DOCS_UPDATE]──> DOCUMENTING
                               │                           │
                               │    [QUALITY_CHECKS]       │
                               │           │               │
                               └───────────┴───────────────┘
                                           │
                                           v
                                      VALIDATED ──[QA_VALIDATION]──> QA_COMPLETE
                                                                        │
                                                    [GIT_COMMIT]        │
                                                        │               │
                                                        v               │
                                                   COMPLETE <───────────┘
```

### record_evidence

Records evidence for a checklist item. Auto-validates if evidence is sufficient.

```typescript
interface RecordEvidenceParams {
  phase: string;
  evidence_type: "tool_output" | "file_path" | "commit_sha" | "content_hash" | "manual";
  evidence: string;
  step?: string;                  // Specific checklist step (for phases with multiple)
}

interface RecordEvidenceResult {
  phase: string;
  step?: string;
  evidence_recorded: boolean;
  auto_validated: boolean;        // Whether evidence triggered validation
  gate_status: "PASS" | "FAIL" | "PENDING";
}
```

### session_end

Validates all end requirements and persists session state.

```typescript
interface SessionEndParams {
  summary: string;                // What was accomplished
  next_session_notes?: string;    // Context for next session
  skip_qa?: boolean;              // Only valid for docs-only sessions
}

interface SessionEndResult {
  session_id: string;
  status: "COMPLETE" | "INCOMPLETE";
  checklist: ChecklistItem[];
  violations: Violation[];
  handoff_updated: boolean;
  commit_sha?: string;
}
```

### get_blocked_reason

Returns why the session cannot proceed.

```typescript
interface GetBlockedReasonResult {
  is_blocked: boolean;
  blocked_phases: BlockedPhase[];
  suggested_actions: string[];
}

interface BlockedPhase {
  phase: string;
  requirement_level: "MUST" | "SHOULD";
  reason: string;
  evidence_needed: string;
}
```

## Resource URIs

### session://state

Current session state including phase, checklist status, and evidence.

```json
{
  "session_id": "2025-12-21-session-01",
  "objective": "Design Session State MCP",
  "branch": "feat/mcp-updates",
  "starting_commit": "e846d7e",
  "current_phase": "WORKING",
  "started_at": "2025-12-21T14:30:00Z",
  "phases_completed": ["SERENA_INIT", "SKILL_VALIDATION", "CONTEXT_RETRIEVAL", "SESSION_LOG"],
  "checklist": {
    "start": [...],
    "end": [...]
  },
  "evidence": {
    "SERENA_INIT": {"tool_output": "Project ai-agents activated"},
    "CONTEXT_RETRIEVAL": {"content_hash": "abc123..."}
  },
  "violations": []
}
```

### session://checklist

Full checklist with RFC 2119 requirements and current status.

```json
{
  "start": [
    {"req": "MUST", "step": "Initialize Serena: mcp__serena__activate_project", "status": "x", "evidence": "Tool output present"},
    {"req": "MUST", "step": "Initialize Serena: mcp__serena__initial_instructions", "status": "x", "evidence": "Tool output present"},
    {"req": "MUST", "step": "Read .agents/HANDOFF.md", "status": "x", "evidence": "Content in context"},
    ...
  ],
  "end": [
    {"req": "MUST", "step": "Update .agents/HANDOFF.md", "status": " ", "evidence": null},
    {"req": "MUST", "step": "Route to qa agent", "status": " ", "evidence": null},
    ...
  ]
}
```

### session://history

Cross-session context (last 5 sessions).

```json
{
  "sessions": [
    {
      "session_id": "2025-12-20-session-03",
      "objective": "PR batch review",
      "outcome": "COMPLETE",
      "commit_sha": "981ebf7",
      "key_decisions": ["Merged 4 PRs", "Deferred security review"],
      "next_session_notes": "Continue with Epic #183"
    },
    ...
  ]
}
```

### session://violations

Audit log of protocol violations for retrospective analysis.

```json
{
  "violations": [
    {
      "session_id": "2025-12-21-session-01",
      "timestamp": "2025-12-21T15:00:00Z",
      "phase": "SKILL_VALIDATION",
      "requirement": "MUST read skill-usage-mandatory memory",
      "severity": "CRITICAL",
      "recovery": "Read memory at 15:01:00Z"
    }
  ]
}
```

## Serena Integration Points

### Memory Schema

The MCP persists state through Serena memories:

| Memory Name | Purpose | Format |
|-------------|---------|--------|
| `session-current-state` | Active session state | JSON |
| `session-history` | Cross-session context | JSON |
| `session-violations-log` | Audit trail | JSON |

### Integration Flow

```
1. session_start() called
   └─> mcp__serena__write_memory("session-current-state", initial_state)

2. validate_gate(phase) called
   └─> Read protocol from SESSION-PROTOCOL.md
   └─> Check evidence against requirements
   └─> mcp__serena__edit_memory("session-current-state", updated_state)

3. record_evidence(phase, evidence) called
   └─> mcp__serena__edit_memory("session-current-state", {evidence})

4. session_end() called
   └─> mcp__serena__read_memory("session-history")
   └─> Append current session summary
   └─> mcp__serena__write_memory("session-history", updated)
   └─> mcp__serena__delete_memory("session-current-state")
```

### Fallback Without Serena

If Serena is unavailable:
- State persisted to `.agents/sessions/.session-state.json`
- Validation still works (reads SESSION-PROTOCOL.md directly)
- Degraded mode logged

## Rationale

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|-------------|------|------|----------------|
| Enhanced PowerShell scripts | Uses existing tooling, no new MCP | No real-time enforcement, post-hoc only | Doesn't prevent violations |
| Claude Code hooks | Native integration | Limited to specific events, can't track state | No persistent state machine |
| External state service | Full independence | Adds infrastructure, latency | Over-engineered for local CLI |
| Serena-only (no new MCP) | Minimal changes | No protocol-aware tooling | Serena is code-focused, not protocol-focused |

### Trade-offs

**Complexity vs Safety**: Adding an MCP increases complexity but provides the real-time enforcement that retrospectives show is necessary.

**Token Cost vs Compliance**: State queries add tokens, but prevent the much higher cost of rework from violations.

**Serena Dependency vs Independence**: Tight Serena integration reduces redundancy but creates coupling.

## Consequences

### Positive

- Real-time BLOCKING gate enforcement (100% compliance like Phase 1)
- Automated evidence collection (reduces manual checklist burden)
- Cross-session context without manual HANDOFF parsing
- Violation audit trail for retrospectives
- Parallel session conflict prevention

### Negative

- New MCP to maintain
- Token overhead for state queries
- Serena dependency for full functionality
- Migration effort from current manual process

### Neutral

- Existing `Validate-SessionEnd.ps1` becomes validation fallback
- SESSION-PROTOCOL.md remains canonical (MCP reads it)
- No change to agent prompt structure

## Implementation Notes

### Phase 1: Core State Machine (P0)

1. Create MCP scaffold with tool/resource definitions
2. Implement session_start, validate_gate, advance_phase
3. Integrate with Serena memory for persistence
4. Add session://state and session://checklist resources

### Phase 2: Evidence Automation (P1)

1. Implement record_evidence with auto-validation
2. Add file watchers for session log, HANDOFF.md
3. Integrate git state detection

### Phase 3: Cross-Session Context (P2)

1. Implement session_end with history update
2. Add session://history resource
3. Add violation logging

### Phase 4: Integration (P3)

1. Update SESSION-PROTOCOL.md to reference MCP tools
2. Add pre-commit hook integration
3. Create migration guide from manual process

### Technology Stack

- **Language**: TypeScript (MCP SDK compatibility)
- **Runtime**: Node.js (Claude Code compatible)
- **Dependencies**: @modelcontextprotocol/sdk, Serena MCP client
- **Testing**: Jest with mock Serena

## Related Decisions

- [ADR-007: Memory-First Architecture](./ADR-007-memory-first-architecture.md)
- [ADR-008: Protocol Automation Lifecycle Hooks](./ADR-008-protocol-automation-lifecycle-hooks.md)
- [ADR-009: Parallel-Safe Multi-Agent Design](./ADR-009-parallel-safe-multi-agent-design.md)

## References

- [SESSION-PROTOCOL.md](../.agents/SESSION-PROTOCOL.md) - Canonical protocol definition
- [Model Context Protocol Specification](https://modelcontextprotocol.io/)
- [Serena MCP Documentation](https://github.com/cloudmcp/serena)
- [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119) - Requirement level keywords
- [skill-protocol-002](../.serena/memories/skill-protocol-002-verification-based-gate-effectiveness.md) - Evidence for verification-based gates

---

*Template Version: 1.0*
*Created: 2025-12-21*
