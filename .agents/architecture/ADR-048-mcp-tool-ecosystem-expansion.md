# ADR-048: MCP Tool Ecosystem Expansion

## Status

Proposed

## Date

2026-02-23

## Context

The ai-agents project uses MCP (Model Context Protocol) for tool integration. The current ecosystem includes:

- **Serena MCP**: Code navigation, symbol analysis, memory management
- **DeepWiki MCP**: Repository documentation and knowledge
- **Forgetful MCP**: Semantic memory (currently unavailable)

Analysis of claude-flow (`.agents/analysis/claude-flow-architecture-analysis.md`) shows their ecosystem includes 100+ MCP tools across categories: Swarm Coordination, Neural Networks, Memory, Analysis, GitHub Integration, and Workflow Automation.

### Current Gaps

| Category | ai-agents | claude-flow |
|----------|-----------|-------------|
| GitHub Tools | Skill-based via `gh` CLI | Dedicated MCP tools |
| Performance | None | performance_report, bottleneck_analyze |
| Neural/Learning | None | neural_train, neural_patterns |
| Coordination | Manual orchestration | swarm_init, agent_spawn |

### Existing ADR Dependencies

- **ADR-011**: Session State MCP (proposed)
- **ADR-012**: Skill Catalog MCP (proposed)
- **ADR-013**: Agent Orchestration MCP (proposed)

## Decision

Expand the MCP tool ecosystem in four phases, building on existing ADRs:

### Phase 1: Foundation (ADR-011, 012, 013)

Implement the already-proposed MCPs first:

| MCP | Purpose | Issue |
|-----|---------|-------|
| Session State | Protocol enforcement | #219 |
| Skill Catalog | Skill discovery | #220 |
| Agent Orchestration | Structured invocation | #221 |

### Phase 2: GitHub Integration

Replace skill-based GitHub operations with dedicated MCP tools:

| Tool | Purpose | Replaces |
|------|---------|----------|
| `github_repo_analyze` | Repository structure analysis | Manual exploration |
| `github_pr_manage` | PR creation, review, merge | `.claude/skills/github/` |
| `github_issue_track` | Issue management, labeling | `gh` CLI via skills |
| `github_release_manage` | Release coordination | Manual `gh release` |

### Phase 3: Performance Tools

Add observability and performance analysis:

| Tool | Purpose |
|------|---------|
| `performance_report` | Generate session/agent performance summary |
| `bottleneck_analyze` | Identify slow operations |
| `benchmark_run` | Execute benchmarks (script invocation) |
| `metrics_collect` | Gather system metrics |

### Phase 4: Neural/Learning Tools

Enable pattern learning from execution history:

| Tool | Purpose |
|------|---------|
| `neural_train` | Train patterns from successful workflows |
| `neural_patterns` | Query learned patterns |
| `learning_adapt` | Apply adaptive learning to routing |
| `skill_consolidate` | Auto-extract skills from retrospectives |

## Rationale

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|-------------|------|------|----------------|
| Keep skill-based approach | Works today, no new infrastructure | No structured interface, manual enforcement | Skills lack programmatic validation |
| Build monolithic MCP | Single deployment | Complex, hard to iterate | Violates separation of concerns |
| Adopt claude-flow directly | 100+ tools immediately | Different architecture, heavy dependency | Not compatible with existing patterns |
| Phased MCP expansion | Incremental, build on existing ADRs | Slower rollout | Chosen: manageable scope, proven patterns |

### Trade-offs

- **Incremental vs. Big Bang**: Phased approach delays full capability but reduces risk
- **Custom vs. Reuse**: Building custom MCPs requires maintenance but fits project architecture
- **MCP vs. Skills**: MCPs provide structured interfaces but skills remain simpler for some operations

## Consequences

### Positive

- Unified tool interface for common operations
- Programmatic validation replaces trust-based enforcement
- Foundation for advanced coordination (swarm, parallel)
- Metrics enable data-driven optimization
- Pattern learning reduces manual retrospective work

### Negative

- MCP development requires TypeScript/Node.js expertise
- Additional infrastructure to maintain
- Migration path needed for existing skill users
- Learning curve for MCP tool usage

### Neutral

- Existing skills remain valid during transition
- MCP and skill approaches can coexist

## Implementation Notes

### Technology Stack

| Component | Technology |
|-----------|------------|
| MCP Runtime | TypeScript + `@modelcontextprotocol/sdk` |
| State Storage | SQLite (via Serena memories) |
| Metrics Storage | JSON files in `.agents/metrics/` |
| Pattern Storage | Vector embeddings (future) |

### File Structure

```text
mcp/
├── session-state/       # ADR-011
├── skill-catalog/       # ADR-012
├── agent-orchestration/ # ADR-013
├── github/              # Phase 2
├── performance/         # Phase 3
└── neural/              # Phase 4
```

### Migration Path

1. **Coexistence**: Skills and MCPs work in parallel
2. **Prefer MCP**: Update AGENTS.md to prefer MCP tools when available
3. **Deprecation**: Mark skills as deprecated after MCP equivalents proven
4. **Removal**: Remove deprecated skills after 2 major versions

## Related Decisions

- [ADR-011: Session State MCP](ADR-011-session-state-mcp.md)
- [ADR-012: Skill Catalog MCP](ADR-012-skill-catalog-mcp.md)
- [ADR-013: Agent Orchestration MCP](ADR-013-agent-orchestration-mcp.md)
- [ADR-030: Skills Pattern Superiority](ADR-030-skills-pattern-superiority.md)

## References

- [Claude-flow Architecture Analysis](../analysis/claude-flow-architecture-analysis.md)
- [MCP Protocol Specification](https://modelcontextprotocol.io/)
- [Issue #179: Expand MCP Tool Ecosystem](https://github.com/rjmurillo/ai-agents/issues/179)
