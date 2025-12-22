# ADR-014: Distributed Handoff Architecture

> **Status**: Accepted
> **Date**: 2025-12-21
> **Authors**: architect, high-level-advisor, devops, analyst (4-agent consensus)
> **Supersedes**: Monolithic HANDOFF.md approach

## Context

HANDOFF.md grew to 122KB / 2,997 lines / ~35K tokens, causing:

1. **Token limit overflow**: Exceeds model context limits, triggers context compaction on every read
2. **Merge conflicts on every PR**: 80%+ conflict rate as all agents update same file
3. **Exponential AI review costs**: Each rebase triggers full re-review of HANDOFF.md
4. **Account ban risk**: API storm from concurrent agent operations
5. **Velocity logjam**: Every PR requires manual conflict resolution

### Scale Requirements

Must support simultaneously:

- **Multiple machines** running agents concurrently
- **Multiple git worktrees** per machine (parallel PRs)
- **GitHub Copilot** reviewing dozens of PRs
- **Claude Code CLI** on local dev machines

## Decision

Implement a **three-tier distributed handoff system** that replaces the monolithic HANDOFF.md with scoped, conflict-free files.

### Architecture

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Three-Tier Handoff System                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Tier 1: Session-Scoped (Ephemeral)                                          │
│  ════════════════════════════════                                            │
│  Location: .agents/sessions/YYYY-MM-DD-session-NN.md                         │
│  Token Budget: 2K per session                                                │
│  Lifecycle: Retained for 30 days, then archived                              │
│  Ownership: Single session                                                   │
│  Conflict Risk: ZERO (unique per session)                                    │
│                                                                              │
│  Tier 2: Branch-Scoped (Per-PR)                                              │
│  ══════════════════════════════                                              │
│  Location: .agents/handoffs/{branch-name}/INDEX.md                           │
│  Token Budget: 3K per branch                                                 │
│  Lifecycle: Deleted on branch close/merge                                    │
│  Ownership: All sessions on that branch                                      │
│  Conflict Risk: LOW (only same-branch sessions)                              │
│                                                                              │
│  Tier 3: Canonical Summary (Dashboard)                                       │
│  ═══════════════════════════════════                                         │
│  Location: .agents/HANDOFF.md (archived/minimal)                             │
│  Token Budget: 5K HARD LIMIT                                                 │
│  Lifecycle: Rolling window (last 10 sessions + active PRs)                   │
│  Ownership: Aggregation scripts only                                         │
│  Conflict Risk: ELIMINATED (automated aggregation only)                      │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Data Flow

```text
Session Work
     │
     v
┌─────────────────────────────────────────┐
│   Tier 1: Session Log                    │
│   .agents/sessions/YYYY-MM-DD-NN.md     │
│   (Tasks, decisions, challenges)         │
└─────────────────────┬───────────────────┘
                      │
                      │ Cross-session context
                      v
┌─────────────────────────────────────────┐
│   Serena Memory                          │
│   mcp__serena__write_memory              │
│   (Patterns, learnings, decisions)       │
└─────────────────────────────────────────┘
```

### Token Budget Enforcement

| Tier | Budget | Enforcement Mechanism |
|------|--------|----------------------|
| Session logs | 2K recommended | Guidance only (no hard block) |
| Branch INDEX | 3K recommended | Guidance only (no hard block) |
| HANDOFF.md | **5K HARD LIMIT** | Pre-commit hook rejects >5K |

### File Structure

```text
.agents/
├── HANDOFF.md                    # Tier 3: Minimal dashboard (5K max)
├── archive/
│   └── HANDOFF-2025-12-21.md     # Archived full content
├── sessions/
│   ├── 2025-12-21-session-01.md  # Tier 1: Session logs
│   ├── 2025-12-21-session-02.md
│   └── ...
└── handoffs/
    ├── feat-xyz/
    │   └── INDEX.md              # Tier 2: Branch context
    └── fix-abc/
        └── INDEX.md
```

## Rationale

### Why Three Tiers?

1. **Session logs (Tier 1)**: Capture granular details without bloating shared state
2. **Branch INDEX (Tier 2)**: Provide PR-specific context without cross-branch conflicts
3. **Canonical dashboard (Tier 3)**: Maintain high-level visibility with strict token limits

### Why Serena Memory Instead of Files?

- **Conflict-free**: Memory updates don't cause git merge conflicts
- **Queryable**: Can search for relevant context without reading entire files
- **Scoped**: Can store patterns, learnings, and decisions separately
- **Cross-session**: Persists between sessions without file management

### Why 5K Token Hard Limit?

- Model context limits: ~35K tokens causes immediate compaction
- Safety margin: 5K leaves room for other context
- Enforcement: Hard limit forces discipline, soft limits are ignored

## Alternatives Considered

### 1. Keep Single HANDOFF.md with Better Discipline

**Rejected**: Trust-based compliance consistently fails. File will grow again.

### 2. Per-Session HANDOFF Files Only

**Rejected**: Loses cross-session context needed for continuity.

### 3. Database-Backed Storage

**Rejected**: Adds infrastructure complexity. Serena memory provides same benefits.

### 4. Event Sourcing with Compaction

**Considered for P2**: Rolling window aggregation could be added later for analytics.

## Implementation Plan

### P0: Immediate (Complete)

- [x] Update SESSION-PROTOCOL.md to stop HANDOFF.md mandates
- [x] Create this ADR

### P1: This Week

- [ ] Create `.agents/archive/` directory
- [ ] Archive current HANDOFF.md content
- [ ] Create minimal HANDOFF.md dashboard template
- [ ] Add `.gitattributes` merge driver configuration
- [ ] Add pre-commit hook for token budget enforcement
- [ ] Create aggregation scripts

### P2: MCP Integration

- [ ] Session State MCP replaces session tracking (#219)
- [ ] Agent Orchestration MCP replaces parallel coordination (#221)
- [ ] Full MCP ownership allows HANDOFF.md deletion

## Success Metrics

| Metric | Before | Target | Verification |
|--------|--------|--------|--------------|
| Merge conflicts per PR | 80%+ | <5% | 10-PR test |
| HANDOFF.md token count | 35K | <5K | Token validator |
| Rebase overhead | 5-15 min | <30s | Time measurement |
| AI review re-runs per PR | 3-5x | 1x | GitHub Actions logs |

## Rollback Plan

If distributed approach fails (10-minute rollback):

1. Remove .gitattributes merge driver
2. Remove handoff validation from pre-commit hook
3. Delete `.agents/handoffs/` directory
4. Restore HANDOFF.md from archive
5. Revert SESSION-PROTOCOL.md changes

## References

- Issue #227: HANDOFF.md merge conflicts causing exponential AI review costs
- Issue #219: Session State MCP
- Issue #221: Agent Orchestration MCP
- Issue #168: Parallel Agent Execution
- Issue #190: Orchestrator HANDOFF coordination
