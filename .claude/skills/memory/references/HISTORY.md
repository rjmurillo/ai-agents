# Memory System Evolution

This document traces the evolution of the ai-agents memory system across three major versions, explaining the motivations and lessons learned at each stage.

## Timeline Overview

```text
v0.0.1 (Nov 2025)    v0.1.0 (Dec 2025)    v0.2.0 (Jan 2026)
      │                    │                    │
      ▼                    ▼                    ▼
┌──────────┐         ┌──────────┐         ┌──────────┐
│  Serena  │  ──▶    │  Serena  │  ──▶    │  Serena  │
│  (file)  │         │    +     │         │    +     │
│          │         │Forgetful │         │Forgetful │
│          │         │ (vector) │         │    +     │
│          │         │          │         │Reflexion │
│          │         │          │         │(episodic)│
└──────────┘         └──────────┘         └──────────┘
   Tier 1              Tier 1               Tiers 1-3
```

## Version 0.0.1: Serena File-Based Memory (November 2025)

### What It Was

The first memory system was purely file-based, using Serena MCP to store and retrieve markdown memories from `.serena/memories/`.

```text
.serena/
└── memories/
    ├── powershell-array-handling.md
    ├── git-hooks-pre-commit.md
    └── ...
```

### Architecture

- **Storage**: Markdown files in Git repository
- **Search**: Lexical keyword matching in filenames
- **Access**: Direct MCP tool calls (`list_memories`, `read_memory`)

### Strengths

- Simple and reliable
- Travels with Git (cross-platform)
- No external dependencies
- Works offline

### Limitations

- No semantic understanding
- Keyword-only search misses conceptually related content
- No structure beyond filename conventions
- Limited to ~500 memories before search degraded

### Lessons Learned

1. File-based memory is essential for portability
2. Git integration ensures memory persistence
3. Lexical search is insufficient for complex queries
4. Need for semantic similarity became clear

## Version 0.1.0: Serena + Forgetful (December 2025)

### What Changed

Added Forgetful MCP as a semantic search layer, providing vector embeddings for similarity-based retrieval.

```text
Memory Access
     │
     ├── Serena (canonical, always available)
     │   └── .serena/memories/*.md
     │
     └── Forgetful (augmentation, optional)
         └── Vector DB at localhost:8020
```

### Architecture

- **Serena**: Unchanged, file-based lexical search
- **Forgetful**: HTTP MCP server with embedding-based search
- **Access**: Parallel queries with result merging

### Strengths

- Semantic similarity finds conceptually related content
- "PowerShell arrays" finds "array handling gotchas" even without keyword match
- Auto-linking builds knowledge graph connections
- Vector search scales better than file scan

### Limitations

- Forgetful requires running service
- Local-only (doesn't travel with Git)
- No structured learning from past sessions
- No causal understanding of what worked/failed
- Two separate systems to query

### Lessons Learned

1. Semantic search dramatically improves retrieval quality
2. External services require availability handling
3. Need for unified search interface (became ADR-037)
4. Past session context was being lost without episodic memory

### Issue Discovered

Agent sessions were repeating mistakes because:

- No record of what was tried before
- No tracking of decision outcomes
- No pattern recognition across sessions
- Full session logs too large to include in context

This led directly to the Reflexion Memory design.

## Version 0.2.0: Full Memory System (January 2026)

### What Changed

Added Memory Router for unified access and Reflexion Memory for episodic/causal reasoning.

```text
┌─────────────────────────────────────────────────────────────┐
│                    Working Memory (Tier 0)                   │
│                    (Claude context window)                   │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│                   Semantic Memory (Tier 1)                   │
│                                                              │
│  ┌─────────────────────┐    ┌─────────────────────┐         │
│  │      Serena         │    │     Forgetful       │         │
│  │   (Canonical)       │◀──▶│   (Augmentation)    │         │
│  │ .serena/memories/   │    │  localhost:8020     │         │
│  └─────────────────────┘    └─────────────────────┘         │
│                                                              │
│              ┌─────────────────────────────┐                 │
│              │     Memory Router           │                 │
│              │   (ADR-037 Unified)         │                 │
│              └─────────────────────────────┘                 │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│                   Episodic Memory (Tier 2)                   │
│           .agents/memory/episodes/*.json                     │
│                                                              │
│  • Session transcripts (compressed)                          │
│  • Decision sequences with rationale                         │
│  • Event chains (commits, errors, milestones)                │
│  • Outcome tracking (success/partial/failure)                │
│  • Lessons learned                                           │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│                    Causal Memory (Tier 3)                    │
│           .agents/memory/causality/causal-graph.json         │
│                                                              │
│  • Cause-effect relationships                                │
│  • Pattern recognition                                       │
│  • Anti-pattern detection                                    │
│  • Success rate tracking                                     │
└─────────────────────────────────────────────────────────────┘
```

### New Components

| Component | Purpose | Files |
|-----------|---------|-------|
| **Memory Router** | Unified Serena+Forgetful search | `scripts/MemoryRouter.psm1` |
| **Search-Memory Skill** | Agent-facing search interface | `.claude/skills/memory/` |
| **Episode Extraction** | Session-to-episode conversion | `scripts/Extract-SessionEpisode.ps1` |
| **Causal Graph** | Cause-effect tracking | `scripts/Update-CausalGraph.ps1` |
| **Reflexion Memory** | Episodic/causal API | `scripts/ReflexionMemory.psm1` |

### Key Innovations

1. **Serena-First Routing**: Canonical source always available, Forgetful augments
2. **Token Efficiency**: Episodes are 500-2000 tokens vs 10K-50K for full logs
3. **Causal Integrity**: All relationships derived from actual session data
4. **Pattern Learning**: Success rates calculated from outcome tracking

### ADRs Created

- **ADR-037**: Memory Router Architecture
- **ADR-038**: Reflexion Memory Schema

### Strengths

- Single `Search-Memory` interface for all queries
- Learn from past decisions and outcomes
- Proven patterns available for reuse
- Anti-patterns identified and avoided
- Causal tracing for root cause analysis

## Comparison Matrix

| Feature | v0.0.1 | v0.1.0 | v0.2.0 |
|---------|--------|--------|--------|
| File-based storage | ✅ | ✅ | ✅ |
| Git portability | ✅ | ✅ | ✅ |
| Lexical search | ✅ | ✅ | ✅ |
| Semantic search | ❌ | ✅ | ✅ |
| Unified search API | ❌ | ❌ | ✅ |
| Episodic memory | ❌ | ❌ | ✅ |
| Causal reasoning | ❌ | ❌ | ✅ |
| Pattern learning | ❌ | ❌ | ✅ |
| Anti-pattern detection | ❌ | ❌ | ✅ |
| Session outcome tracking | ❌ | ❌ | ✅ |

## Migration Notes

### From v0.0.1 to v0.1.0

No migration needed - Forgetful added alongside Serena.

### From v0.1.0 to v0.2.0

1. **Install Memory Router**: New module, no breaking changes
2. **Create episode directories**: `.agents/memory/episodes/` and `.agents/memory/causality/`
3. **Update calls**: Optional, can still use Serena directly
4. **Extract episodes**: Run on existing session logs

```powershell
# Migrate existing sessions to episodes
Get-ChildItem ".agents/sessions/*.md" | ForEach-Object {
    pwsh scripts/Extract-SessionEpisode.ps1 -SessionLogPath $_.FullName -Force
}

# Build initial causal graph
pwsh scripts/Update-CausalGraph.ps1
```

## Future Direction

### Planned for v0.3.0

- **Cross-session pattern synthesis**: Combine patterns from multiple episodes
- **Counterfactual analysis**: "What if we had chosen X instead?"
- **Automatic memory curation**: Prune low-value memories
- **Memory importance scoring**: Prioritize high-impact memories

### Considered but Deferred

- **External vector DB**: PostgreSQL with pgvector
- **Cloud memory sync**: Cross-machine memory sharing
- **Memory compression**: LLM-based summarization

## Lessons Learned Across Versions

1. **Portability is non-negotiable**: File-based, Git-synced memory must remain canonical
2. **Graceful degradation**: System must work when optional components unavailable
3. **Unified interfaces**: One search API better than multiple system-specific APIs
4. **Learn from failures**: Structured outcome tracking enables pattern learning
5. **Token efficiency**: Compressed episodes beat full transcripts
6. **Causal integrity**: Only derive relationships from actual data

## Related Documentation

- [README.md](README.md) - System overview
- [Memory Router](memory-router.md) - Unified search API
- [Reflexion Memory](reflexion-memory.md) - Episodic/causal API
- [API Reference](api-reference.md) - Complete function signatures
- ADR-037 - Memory Router Architecture
- ADR-038 - Reflexion Memory Schema
