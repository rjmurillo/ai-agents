# ADR-007: Memory-First Architecture

## Status

Accepted

## Date

2025-12-20

## Context

The ai-agents system evolved organically with memory as an afterthought - agents would execute tasks and optionally store learnings. This led to:

1. **Repeated discoveries**: Agents re-learned the same patterns across sessions
2. **Lost institutional knowledge**: Retrospective insights weren't consistently retrievable
3. **Inconsistent behavior**: Same scenarios handled differently based on what agents happened to remember
4. **No semantic search**: Pattern matching relied on exact keyword hits

Research into [ruvnet/claude-flow](https://github.com/ruvnet/claude-flow) revealed that their 84.8% SWE-Bench solve rate (vs 43% industry average) was partially attributed to a sophisticated memory system with:

- 96-164x faster vector search via HNSW indexing
- 4-tier memory architecture (AgentDB, ReasoningBank, SQLite, JSON fallback)
- Semantic retrieval enabling pattern matching across sessions

## Decision

**Memory retrieval MUST precede reasoning in all agent workflows.**

Specifically:

1. **Step 0 of SESSION-PROTOCOL**: Agents call `list_memories` before any analysis
2. **Semantic storage**: New patterns stored with embeddings for future retrieval
3. **Memory-first patterns**: Detection logic documented in memory, not executable scripts
4. **Retrieval verification**: Session logs must evidence memory retrieval before decisions

## Rationale

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|-------------|------|------|----------------|
| Code-first (scripts) | Familiar, debuggable | No learning, manual updates | Doesn't scale |
| Hybrid (code + memory) | Flexible | Unclear boundaries, duplication | Maintenance burden |
| Memory-first | Scales learning, semantic search | Requires discipline | **Chosen** |

### Trade-offs

- **Upfront cost**: Must populate memory before benefiting from retrieval
- **Discipline required**: Agents must actually call retrieval before reasoning
- **Tooling dependency**: Requires Serena or cloudmcp-manager availability

## Consequences

### Positive

- Agents inherit institutional knowledge from prior sessions
- Patterns discovered once benefit all future sessions
- Semantic search finds relevant context even with imprecise queries
- Skills auto-consolidate from retrospectives (Issue #173)

### Negative

- Cold start problem for new deployments
- Memory corruption could propagate bad patterns
- Slower initial response (retrieval latency)

### Neutral

- Shifts complexity from code maintenance to memory curation

## Implementation Notes

1. **Immediate**: SESSION-PROTOCOL Phase 1 requires `mcp__serena__list_memories`
2. **Phase 2A**: Implement vector memory backend (Issue #167)
3. **Phase 5A**: Add skill auto-consolidation (Issue #173)

Example memory-first pattern:

```markdown
# Skill: Copilot Follow-Up PR Detection

**Trigger**: PR review comment from Copilot
**Pattern**: Check for new PRs with title "copilot/sub-pr-{original-PR}"
**Action**: If found within 60 seconds, likely follow-up PR not direct fix
```

This pattern is retrieved via semantic search, not executed as a script.

## Related Decisions

- ADR-008: Protocol Automation via Lifecycle Hooks (enforces retrieval)
- SESSION-PROTOCOL.md Phase 1 requirements

## References

- Epic #183: Claude-Flow Inspired Enhancements
- Issue #167: Vector Memory System
- Issue #173: Skill Auto-Consolidation
- Issue #176: Neural Pattern Learning
- Issue #180: Reflexion Memory
- [claude-flow memory architecture](https://github.com/ruvnet/claude-flow)
- `.serena/memories/claude-flow-research-2025-12-20.md`

---

*Template Version: 1.0*
*Origin: Epic #183 closing comment (2025-12-20)*
