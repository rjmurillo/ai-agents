<#
.SYNOPSIS
    Enforces ADR-007 Memory-First Architecture at session start.

.DESCRIPTION
    Claude Code hook that injects memory-first requirements into the session context.
    Outputs blocking gate requirements that Claude receives before processing any user prompts.
    Part of the ADR-007 enforcement mechanism (Issue #729).

.NOTES
    Hook Type: SessionStart
    Exit Codes:
        0 = Success, stdout added to Claude's context
        2 = Block session (critical failure)

.LINK
    .agents/architecture/ADR-007-memory-first-architecture.md
    .agents/SESSION-PROTOCOL.md
#>
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Output context that will be injected into Claude's context window
@"

## ADR-007 Memory-First Enforcement (Session Start)

**BLOCKING GATE**: Complete these steps BEFORE any reasoning or implementation:

### Phase 1: Serena Initialization (REQUIRED)

1. ``mcp__serena__activate_project`` - Activate project memory
2. ``mcp__serena__initial_instructions`` - Load Serena guidance

### Phase 2: Context Retrieval (REQUIRED)

1. Read ``.agents/HANDOFF.md`` - Previous session context
2. Read ``memory-index`` from Serena - Identify relevant memories
3. Read task-relevant memories - Apply learned patterns

### Verification

Session logs MUST evidence memory retrieval BEFORE decisions.
Pre-commit validation will fail without proper evidence.

**Protocol**: ``.agents/SESSION-PROTOCOL.md``
**Architecture**: ``.agents/architecture/ADR-007-memory-first-architecture.md``

"@

exit 0
