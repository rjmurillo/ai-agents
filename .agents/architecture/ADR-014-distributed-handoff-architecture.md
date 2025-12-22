# ADR-014: Distributed Handoff Architecture

## Status

Accepted

## Date

2025-12-22

## Context

HANDOFF.md has grown to **122KB / 2,997 lines / ~35K tokens**, causing severe operational problems:

1. **Token limit overflow** → context compaction on every read
2. **Merge conflicts on EVERY PR** → 80%+ conflict rate
3. **Exponential AI review costs** → each rebase triggers full re-review
4. **Account ban risk** → API storm from concurrent agent operations
5. **Velocity logjam** → every PR requires manual conflict resolution

The system must support:

- **Multiple machines** running agents concurrently
- **Multiple git worktrees** per machine (parallel PRs)
- **GitHub Copilot** reviewing dozens of PRs
- **Claude Code CLI** on local dev machines

**Root cause**: Centralized file acting as single source of truth creates bottleneck when multiple agents update simultaneously.

**Critical requirement**: Must work WITHOUT MCPs (Session State MCP #219, Agent Orchestration MCP #221) until they're ready.

## Decision

Implement a **three-tier distributed handoff architecture** that eliminates centralized HANDOFF.md as a write target:

### Architecture Overview

| Tier | Location | Token Budget | Lifecycle | Purpose |
|------|----------|--------------|-----------|---------|
| **Tier 1** (Session) | `.agents/sessions/YYYY-MM-DD-session-NN.md` | 2K per session | Permanent | Complete session record |
| **Tier 2** (Branch) | `.agents/handoffs/{branch}/` | 3K per branch | Deleted on merge | Branch coordination (optional) |
| **Tier 3** (Canonical) | `.agents/HANDOFF.md` | **5K (hard limit)** | Rolling window | Read-only dashboard |

### Key Changes

1. **HANDOFF.md becomes read-only** for all agents on feature branches
2. **Session logs become authoritative** for session context
3. **Serena memory stores cross-session context** (using MCP when available)
4. **Branch handoffs are optional** for multi-session branch coordination
5. **Pre-commit hook blocks** HANDOFF.md modifications on feature branches
6. **Token budget validator** enforces 5K limit on HANDOFF.md

## Rationale

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|-------------|------|------|----------------|
| Keep centralized HANDOFF.md | Familiar, simple concept | 80%+ conflict rate, exponential AI costs, context overflow | Current crisis state - unsustainable |
| Delete HANDOFF.md entirely | No conflicts ever | Loses historical context, no dashboard | Too radical - need gradual transition |
| Lock-based updates | Prevents simultaneous writes | Requires coordination service, doesn't work across machines | Needs infrastructure not yet built |
| Event sourcing with append-only log | Theoretical elegance | Complex implementation, high token cost | Over-engineered for current needs |
| Per-PR handoff files | Good isolation | No cross-PR context, duplication | MCPs will handle this better |

### Trade-offs

**Chosen approach trade-offs:**

- **Accept**: Some context fragmentation across session logs
- **Accept**: Agents must use Serena memory for cross-session queries
- **Accept**: HANDOFF.md becomes stale (but remains readable)
- **Gain**: Zero merge conflicts on HANDOFF.md
- **Gain**: Linear AI review costs (not exponential)
- **Gain**: Works immediately without waiting for MCPs

## Consequences

### Positive

- **Immediate relief**: Stops 80%+ merge conflict rate TODAY
- **Cost reduction**: Eliminates exponential AI review costs from rebases
- **Scalability**: Multiple agents can work concurrently without coordination
- **Token efficiency**: HANDOFF.md stays under 5K tokens (96% reduction)
- **MCP-ready**: Architecture aligns with Session State MCP design
- **Backward compatible**: Existing session logs remain valid
- **Fail-safe**: Pre-commit hook prevents protocol violations

### Negative

- **Context fragmentation**: Information spread across session logs (mitigated by Serena memory)
- **Discovery cost**: Finding relevant context requires searching session logs or memory
- **HANDOFF.md staleness**: Dashboard may lag behind recent sessions
- **Learning curve**: Agents must adapt to new protocol

### Neutral

- **Session log importance increases**: Already required by protocol, now more critical
- **Serena memory dependency**: Already required, now mandatory for cross-session context
- **Pre-commit hook complexity**: Adds validation logic (but prevents violations)

## Implementation Notes

### Phase 1: Immediate (P0) - COMPLETED

**Goal**: Stop the bleeding. Zero agent prompt changes initially.

**Changes**:

1. Update SESSION-PROTOCOL.md v1.4:
   - Change "MUST update HANDOFF.md" to "MUST NOT update HANDOFF.md"
   - Direct agents to: session logs, Serena memory, branch handoffs
2. Archive current HANDOFF.md to `.agents/archive/HANDOFF-2025-12-22.md`
3. Create minimal dashboard (4KB) in `.agents/HANDOFF.md`:
   - Active projects summary
   - Recent session links (last 5)
   - Key ADRs and architecture links
4. Add `.gitattributes`:
   - HANDOFF.md uses 'ours' merge strategy on feature branches
   - Branch handoffs use 'handoff-aggregate' merge driver
5. Create `scripts/Validate-TokenBudget.ps1`:
   - Enforces 5K token limit
   - Called by pre-commit hook
6. Update `.githooks/pre-commit`:
   - Block direct HANDOFF.md modifications on feature branches
   - Add token budget validation
   - Remove HANDOFF.md staging requirement

**Verification**:

```bash
# Token budget check
pwsh scripts/Validate-TokenBudget.ps1

# Pre-commit enforcement test
echo "test" >> .agents/HANDOFF.md
git add .agents/HANDOFF.md
git commit -m "test"  # Should FAIL on feature branch
```

### Phase 2: MCP Integration (P1) - FUTURE

**Goal**: Let MCPs own all coordination state (when available).

| Week | MCP | HANDOFF Impact |
|------|-----|----------------|
| 1-2 | Session State MCP (#219) | State machine replaces session tracking |
| 3-4 | Cross-session context via Serena memory | Replaces HANDOFF sections |
| 5-6 | Agent Orchestration MCP (#221) | Parallel coordination without files |
| 8+ | Full MCP ownership | Can delete HANDOFF.md entirely |

### Token Budget Calculation

**Conservative estimate**: 4 characters per token (English text average)

**HANDOFF.md limits**:

- **Hard limit**: 5,000 tokens (20KB)
- **Current**: 1,003 tokens (4KB) - 20% usage
- **Buffer**: 3,997 tokens (80%) remaining

**Dashboard content priorities**:

1. Active projects (1-2K tokens)
2. Recent sessions (500 tokens)
3. Key ADRs (500 tokens)
4. Protocol compliance (500 tokens)

### Git Merge Strategies

**.gitattributes configuration**:

```gitattributes
# HANDOFF.md uses ours strategy (main branch wins)
.agents/HANDOFF.md merge=ours

# Branch handoffs use custom aggregation
.agents/handoffs/*.md merge=handoff-aggregate
```

**Why 'ours' strategy**: Feature branches should never modify HANDOFF.md. If conflict occurs, main branch version always wins (it's the authoritative dashboard).

**Why 'handoff-aggregate' for branches**: Future optimization - merge driver can aggregate branch handoffs intelligently (P2 work).

### Session Log Requirements

**Session logs MUST include**:

1. **Session metadata**: Date, branch, starting commit, objective
2. **Protocol compliance checklist**: Session start and end gates
3. **Work log**: Tasks attempted, decisions made, challenges
4. **Cross-references**: Links to related sessions, artifacts, PRs
5. **Next session notes**: Context for continuation

**Example session log structure**: See `.agents/SESSION-PROTOCOL.md` Session Log Template

### Serena Memory Protocol

**When to write memory**:

- **After significant decisions**: Architecture, design patterns, tool choices
- **After discoveries**: Gotchas, pitfalls, non-obvious behaviors
- **After skill creation**: New capabilities available to agents
- **After milestone completion**: Major features, refactorings

**Memory naming conventions**:

- `pattern-{technology}-{pattern-name}`: Code patterns
- `decision-{topic}-{date}`: Architecture decisions
- `skill-{category}-{name}`: Skill documentation
- `project-{name}-status`: Project state

### Rollback Plan

If distributed approach fails (10-minute rollback):

1. Remove `.gitattributes` merge driver
2. Remove HANDOFF.md validation from pre-commit hook
3. Delete `.agents/handoffs/` directory
4. Restore HANDOFF.md from `.agents/archive/HANDOFF-2025-12-22.md`
5. Revert SESSION-PROTOCOL.md to v1.3

## Related Decisions

- **ADR-007**: Memory-First Architecture (Serena memory foundation)
- **ADR-008**: Protocol Automation Lifecycle Hooks (pre-commit validation)
- **ADR-009**: Parallel-Safe Multi-Agent Design (concurrent execution patterns)
- **ADR-011**: Session State MCP (future state management)
- **ADR-013**: Agent Orchestration MCP (future coordination)

## References

- **Issue #190**: HANDOFF.md merge conflicts causing exponential AI review costs
- **Issue #219**: Session State MCP (replaces session tracking)
- **Issue #221**: Agent Orchestration MCP (replaces parallel coordination)
- **SESSION-PROTOCOL.md v1.4**: Updated protocol with HANDOFF.md prohibition
- **4-agent consensus**: high-level-advisor, architect, devops, analyst (from issue description)

## Success Metrics

| Metric | Baseline | Target | Verification |
|--------|----------|--------|--------------|
| Merge conflicts per PR | 80%+ | <5% | 10-PR test period |
| HANDOFF.md token count | 35K | <5K | Token validator |
| Rebase overhead | 5-15 min | <30s | Time measurement |
| AI review re-runs per PR | 3-5x | 1x | GitHub Actions logs |
| HANDOFF.md size | 118KB | <20KB | File system |

**Validation period**: 2 weeks (20 PRs minimum)

**Success criteria** (with operational definitions):

- ✅ Zero HANDOFF.md merge conflicts
  - *Definition*: No merge conflict markers in HANDOFF.md across 20-PR validation period
- ✅ Token budget maintained <5K
  - *Definition*: `scripts/Validate-TokenBudget.ps1` returns exit code 0
- ✅ Pre-commit hook blocks violations
  - *Definition*: Attempting to commit HANDOFF.md changes on feature branch fails with ADR-014 error
- ✅ CI backstop blocks bypass attempts
  - *Definition*: PR with HANDOFF.md changes fails `validate-handoff-readonly` workflow
- ✅ No agent confusion about protocol
  - *Definition*: Zero protocol compliance failures in session logs (Phase 1/2 gates pass on first attempt)
  - *Measurement*: Audit 10 consecutive session logs for "Protocol Compliance: PASS" entries
- ✅ Session logs contain complete context
  - *Definition*: Session logs include all 5 required sections per ADR-014:
    1. Session metadata (date, branch, commit, objective)
    2. Protocol compliance checklist
    3. Work log (tasks, decisions, challenges)
    4. Cross-references (sessions, artifacts, PRs)
    5. Next session notes
  - *Measurement*: Automated linter validates session log structure (future: Session State MCP)

---

*Template Version: 1.0*
*Created: 2025-12-22*
*GitHub Issue: #190*
