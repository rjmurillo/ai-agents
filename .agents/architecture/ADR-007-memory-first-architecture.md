# ADR-007: Memory-First Architecture

## Status

Accepted (Revised 2026-01-01)

## Date

2025-12-20 (Original) | 2026-01-01 (Augmented + Revised per ADR Review)

## Context

The ai-agents system evolved organically with memory as an afterthought - agents would execute tasks and optionally store learnings. This led to:

1. **Repeated discoveries**: Agents re-learned the same patterns across sessions
2. **Lost institutional knowledge**: Retrospective insights weren't consistently retrievable
3. **Inconsistent behavior**: Same scenarios handled differently based on what agents happened to remember
4. **No semantic search**: Pattern matching relied on exact keyword hits

Research into [ruvnet/claude-flow](https://github.com/ruvnet/claude-flow) revealed a self-reported 84.8% solve rate on SWE-bench-Lite (300 instances; not SWE-bench Verified, where SOTA achieves 74.6-80.9%). The memory contribution was not separately quantified, but their architecture includes:

- 96-164x faster vector search via HNSW indexing
- 4-tier memory architecture (AgentDB, ReasoningBank, SQLite, JSON fallback)
- Semantic retrieval enabling pattern matching across sessions

### Extended Research (2026-01-01)

Additional research into memory-first systems revealed complementary approaches:

**[Forgetful MCP](https://github.com/ScottRBK/forgetful)** implements a semantic memory system with:

- Meta-tools pattern: 3 tools expose 42 underlying operations, preserving context window
- Dual graph architecture: Memory graph (concepts) + Entity graph (real-world objects)
- Auto-linking: Cosine similarity ≥0.7 triggers bidirectional links to top 3-5 matches
- Token budget: Configurable limit (default 8000 tokens, 20 memories max)
- Multi-stage retrieval: Dense search → Sparse search → RRF fusion → Cross-encoder reranking

**[BMAD Method](https://github.com/bmad-code-org/BMAD-METHOD)** provides a scale-adaptive workflow framework:

- Sidecar files: Persistent `memories.md` per agent in `{agent-name}-sidecar/` folders
- Critical actions: Memory loading enforced before task execution
- Scale-adaptive routing: Quick Flow / BMad Method / Enterprise Method tracks
- Party Mode: Multi-agent collaboration for complex decisions

**[Zettelkasten Method](https://zettelkasten.de/introduction/)** establishes foundational principles:

- **Atomicity**: One concept per note (300-400 words optimal)
- **Unique identifiers**: Stable IDs enable robust cross-referencing
- **Explicit linking**: Connections with context (why linked, not just that linked)
- **Emergence**: Patterns and insights emerge from the growing network

**[A-MEM](https://arxiv.org/abs/2502.12110)** (arXiv 2502.12110) advances beyond static retrieval:

- Dynamic memory organization with contextual descriptions, keywords, tags
- Intelligent linking based on meaningful similarities
- Memory evolution: New memories trigger updates to existing memory attributes
- Superior improvement over SOTA baselines across six foundation models

## Decision

**Memory retrieval MUST precede reasoning in all agent workflows.**

Specifically:

1. **Step 0 of SESSION-PROTOCOL**: Agents call `list_memories` before any analysis
2. **Semantic storage**: New patterns stored with embeddings for future retrieval
3. **Memory-first patterns**: Detection logic documented in memory, not executable scripts
4. **Retrieval verification**: Session logs must evidence memory retrieval before decisions

### Zettelkasten Principles (Augmented)

Memory creation and organization SHOULD follow Zettelkasten principles:

| Principle | Implementation | Rationale |
|-----------|----------------|-----------|
| **Atomicity** | One concept per memory (max 400 words) | Enables precise retrieval, reduces noise |
| **Unique IDs** | Stable memory IDs (Forgetful: auto-generated) | Enables robust cross-referencing |
| **Explicit Linking** | Links include context explaining relationship | Prevents meaningless tangles |
| **Emergence** | Knowledge graph grows organically via auto-linking | Patterns emerge without manual curation |

### Dual Memory Architecture (Augmented)

The system employs complementary memory systems with **Serena as the canonical layer**:

| System | Scope | Persistence | Cross-Platform | Role |
|--------|-------|-------------|----------------|------|
| **Serena** | Project | Git-synchronized markdown | ✅ All platforms | **Canonical** |
| **Forgetful** | Local | SQLite database | ❌ Local only | Supplementary |

**Critical insight**: Forgetful and claude-mem tools may be available on hosted platforms (GitHub Copilot), but **the database contents are not**. Only Serena memories (`.serena/memories/*.md`) travel with the repository.

**Memory workflow** (Serena-first):

1. **Read** from Serena (canonical, always available) → markdown files with explicit cross-references
2. **Augment** with Forgetful (if available) → semantic search for related patterns
3. **Persist** to Serena → new learnings as markdown files
4. **Commit** with code → Git synchronizes to all platforms/VMs

**Routing heuristic**:

- **Serena**: All important patterns, decisions, cross-references (canonical source)
- **Forgetful**: Semantic search, knowledge graph (supplementary, local-only)

### Fallback Behavior

When Forgetful MCP is unavailable, agents MUST continue with Serena-only workflow:

| Scenario | Detection | Fallback Behavior |
|----------|-----------|-------------------|
| Forgetful not running | `mcp__forgetful__*` tools unavailable | Use Serena `memory-index` for keyword-based discovery |
| Forgetful timeout | Tool call times out | Proceed with Serena memories already loaded |
| Forgetful empty results | Search returns no matches | Check Serena skill indexes directly |
| Fresh environment | No Forgetful database | Full Serena workflow (no semantic search) |

**Graceful degradation**:

```text
1. Attempt Forgetful semantic search
2. If unavailable or empty: Fall back to Serena memory-index
3. Read memories listed in memory-index matching task keywords
4. Proceed with available context
```

**MUST NOT**:

- Block work waiting for Forgetful
- Skip memory retrieval because Forgetful is unavailable
- Claim memory compliance without reading Serena memories

**Evidence**: When Forgetful is unavailable, session log Evidence column should note:
`memory-index, skills-xxx-index (Forgetful unavailable - Serena only)`

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
- **Tooling dependency**: Requires Serena MCP availability

### Tool Selection (Clarification)

| Tool Pattern | Status | Scope |
|--------------|--------|-------|
| `mcp__serena__*` | **Canonical** | Project memory operations |
| `mcp__forgetful__*` | Supplementary | Semantic search (local only) |
| `cloudmcp-manager` | **Deprecated** | Legacy references, migrate to Serena |

**Note**: Agent templates and CLAUDE.md may reference `cloudmcp-manager` - these are legacy and should migrate to `mcp__serena__*` tools.

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

## Confirmation

Compliance with "memory retrieval MUST precede reasoning" is verified by:

1. **SESSION-PROTOCOL Phase 2**: Blocking gate requires `memory-index` read
2. **Session logs**: Must evidence memory retrieval before decision-making
3. **Pre-commit hook**: Validates session log compliance (`scripts/Validate-SessionEnd.ps1`)

## Security Considerations

### Memory Integrity

Memories are consumed without cryptographic verification. Mitigations:

1. **Git history**: Provides audit trail for memory changes
2. **PR review**: Memory file changes subject to code review
3. **Future**: Issue tracking for memory provenance validation (CWE-345)

### Data Classification

Memory content SHOULD NOT include:

- API keys, tokens, credentials
- PII or sensitive user data
- Security vulnerabilities (use `.agents/security/` instead)

### Access Control

Inherited from git repository permissions. No additional ACL.

### Storage Security

- **Serena**: Git-tracked markdown (inherits repo access controls)
- **Forgetful**: Local SQLite without encryption (CWE-311) - supplementary only

## Implementation Status

**Current State (2026-01-01)**:

- ✅ Serena MCP active: 459 memory files in `.serena/memories/`
- ✅ SESSION-PROTOCOL Phase 2 enforces memory-first workflow
- ✅ ADR-017 Tiered Index implements Zettelkasten principles
- ⏳ Issue #584 (P0): Serena Integration Layer pending
- ✅ Forgetful MCP configured (`.mcp.json`)

**Acceptance Criteria**:

- ADR-007 is **architecturally accepted** as guidance
- Dual memory (Serena + Forgetful) is experimental until Issue #584 closes

## Relationship to Issue #167

Issue #167 proposes "Vector Memory System with Semantic Search."
Forgetful MCP (integrated 2026-01-01) provides this capability:

- HNSW indexing for semantic search
- Multi-stage retrieval (dense → sparse → RRF → cross-encoder)
- Auto-linking at cosine similarity ≥0.7

**Recommendation**: Close Issue #167 as superseded by Forgetful integration,
or document gaps if additional capabilities are needed.

## Implementation Notes

1. **Immediate**: SESSION-PROTOCOL Phase 1 requires `mcp__serena__list_memories`
2. **Phase 2A**: ~~Implement vector memory backend (Issue #167)~~ → Superseded by Forgetful
3. **Phase 5A**: Add skill auto-consolidation (Issue #173)

### Forgetful Integration (Augmented)

Forgetful MCP provides the semantic memory backbone. Key integration points:

```python
# 3-layer workflow (token efficient)
1. search(query) → Get index with IDs (~50-100 tokens/result)
2. timeline(anchor=ID) → Get context around interesting results
3. get_observations([IDs]) → Fetch full details ONLY for filtered IDs
```

**Memory creation pattern** (Zettelkasten-compliant):

```python
mcp__forgetful__execute_forgetful_tool("create_memory", {
    "title": "Short descriptive title (max 200 chars)",
    "content": "Atomic concept, max 2000 chars, ideally 300-400 words",
    "context": "Why this matters, when to apply (max 500 chars)",
    "keywords": ["semantic", "search", "terms"],
    "tags": ["category1", "category2"],
    "importance": 7,  # 1-10 scale for retrieval priority
    "project_ids": [1]
})
```

**Auto-linking**: Forgetful automatically creates bidirectional links when cosine similarity ≥0.7.

### BMAD-Inspired Enhancements (Future)

Consider adopting BMAD patterns:

1. **Sidecar memories**: Per-agent persistent context in `.claude/agents/{name}-sidecar/memories.md`
2. **Critical actions**: Pre-task memory loading as blocking gate
3. **Party Mode**: Multi-agent memory synthesis for complex decisions

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

### Original References

- Epic #183: Claude-Flow Inspired Enhancements
- Issue #167: Vector Memory System
- Issue #173: Skill Auto-Consolidation
- Issue #176: Neural Pattern Learning
- Issue #180: Reflexion Memory
- [claude-flow memory architecture](https://github.com/ruvnet/claude-flow)
- `.serena/memories/claude-flow-research-2025-12-20.md`

### Augmentation References (2026-01-01)

- [Forgetful MCP](https://github.com/ScottRBK/forgetful) - Semantic memory with knowledge graph
- [BMAD Method](https://github.com/bmad-code-org/BMAD-METHOD) - Scale-adaptive agent workflows
- [Zettelkasten Method](https://zettelkasten.de/introduction/) - Atomic note-taking principles
- [A-MEM: Agentic Memory for LLM Agents](https://arxiv.org/abs/2502.12110) - Dynamic memory evolution
- [7 Essential Principles of Zettelkasten](https://medium.com/@theo-james/7-essential-principles-of-zettelkasten-0f3bd8896d68)

---

*Template Version: 1.0*
*Origin: Epic #183 closing comment (2025-12-20)*
*Augmented: 2026-01-01 with Forgetful, BMAD, Zettelkasten, A-MEM research*
