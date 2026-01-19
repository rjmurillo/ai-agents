# PRD: Standalone Memory Plugin for AI Agents

**Status**: Draft
**Author**: Claude
**Created**: 2026-01-19
**Related Issues**: #724 (Traceability Graph), #584 (Serena Integration)
**Inspiration**: [GitHub Copilot Agentic Memory System](https://github.blog/ai-and-ml/github-copilot/building-an-agentic-memory-system-for-github-copilot/)

---

## 1. Problem Statement

### 1.1 Current State

AI coding agents lose context between sessions. Existing solutions require:

- **External databases** (Neo4j, Postgres) that add deployment complexity
- **MCP servers** (Forgetful, Serena) that aren't available on all platforms
- **Vendor lock-in** to specific memory implementations

### 1.2 Core Tension

There's a fundamental conflict between:

| Need | Current Solutions |
|------|-------------------|
| Semantic search (find related concepts) | Requires vector DB (Chroma, Pinecone) |
| Cross-session persistence | Requires external state |
| Portability (works everywhere) | Tied to specific MCP implementations |
| Human-readable storage | Binary embeddings aren't inspectable |

### 1.3 Project Constraint (from Issue #724)

> **Everything should be markdown and accessible without special tools, configuration, or context bloat.**
>
> This means no external graph database or MCP dependencies - the implementation must be a "poor man's graph database" built on markdown files.

### 1.4 Opportunity

GitHub Copilot's memory system demonstrates that **citation-backed validation** and **just-in-time verification** can replace complex encoding schemes. Combined with the markdown-first constraint, we can build a memory system that:

1. Works with zero external dependencies
2. Travels with the git repository
3. Is human-readable and grep-able
4. Optionally enhances with vector search when available

---

## 2. Goals and Non-Goals

### 2.1 Goals

| Priority | Goal | Success Metric |
|----------|------|----------------|
| P0 | **Markdown-canonical storage** | All memories readable via `cat`/`grep` |
| P0 | **Zero required dependencies** | Works with Python stdlib only |
| P0 | **Git-synchronized** | Memories travel with repository |
| P1 | **Citation validation** | Detect stale memories via file references |
| P1 | **Graph traversal** | Navigate memory relationships without external DB |
| P2 | **Progressive enhancement** | Optional vector search when Chroma available |
| P2 | **Multi-agent reinforcement** | Agents can validate/update each other's memories |

### 2.2 Non-Goals

| Explicitly Out of Scope | Rationale |
|------------------------|-----------|
| Real-time sync with external DBs | Violates markdown-canonical principle |
| Binary storage formats | Must be human-readable |
| Required MCP server | Must work standalone |
| Cloud-hosted memory | Must work fully offline |
| Automatic memory creation | Agents must explicitly save (intentionality) |

---

## 3. User Stories

### 3.1 Core Personas

| Persona | Description |
|---------|-------------|
| **Agent** | AI coding assistant that needs cross-session memory |
| **Developer** | Human who reviews/curates agent memories |
| **Platform** | CI/CD system that validates memory integrity |

### 3.2 User Stories

#### US-1: Agent Searches Memory (P0)

**As an** agent starting a new session,
**I want to** search for relevant memories by topic,
**So that** I don't repeat past mistakes or rediscover known patterns.

**Acceptance Criteria:**
- [ ] Search returns memories ranked by relevance
- [ ] Works without any external services running
- [ ] Results include memory content and metadata
- [ ] Search completes in <500ms for 1000 memories

#### US-2: Agent Saves Memory (P0)

**As an** agent that discovered a new pattern,
**I want to** save it as a memory with citations,
**So that** future sessions can benefit from this knowledge.

**Acceptance Criteria:**
- [ ] Memory saved as markdown file with frontmatter
- [ ] Citations reference specific file:line locations
- [ ] Memory ID is deterministic and stable
- [ ] File is immediately visible in git status

#### US-3: Agent Verifies Memory (P1)

**As an** agent retrieving a memory,
**I want to** verify its citations are still valid,
**So that** I don't act on stale information.

**Acceptance Criteria:**
- [ ] Verification checks each citation file:line exists
- [ ] Stale citations are flagged with specific details
- [ ] Verification result includes confidence score
- [ ] Agent can choose to skip or flag stale memories

#### US-4: Agent Traverses Memory Graph (P1)

**As an** agent investigating a topic,
**I want to** follow links between related memories,
**So that** I can build comprehensive understanding.

**Acceptance Criteria:**
- [ ] Graph traversal uses only markdown file operations
- [ ] Supports BFS/DFS with configurable depth
- [ ] Returns adjacency structure for visualization
- [ ] Handles cycles without infinite loops

#### US-5: Developer Inspects Memories (P0)

**As a** developer reviewing agent behavior,
**I want to** read memories using standard tools,
**So that** I can understand and curate agent knowledge.

**Acceptance Criteria:**
- [ ] `cat memories/mem-*.md` shows readable content
- [ ] `grep -r "api versioning" memories/` finds relevant files
- [ ] Frontmatter is valid YAML parseable by any tool
- [ ] No binary files or encoded content

#### US-6: Platform Validates Memory Integrity (P2)

**As a** CI/CD pipeline,
**I want to** validate all memory citations,
**So that** stale memories are detected before merge.

**Acceptance Criteria:**
- [ ] Batch validation of all memories in directory
- [ ] Exit code reflects validation status
- [ ] Report lists all stale citations
- [ ] Can be run as pre-commit hook or CI job

---

## 4. Technical Requirements

### 4.1 Memory Schema

```yaml
# Frontmatter schema (YAML)
id: string           # Unique identifier (e.g., "mem-api-versioning-001")
subject: string      # Brief subject line (< 80 chars)
created: datetime    # ISO 8601 timestamp
verified: datetime   # Last verification timestamp (nullable)
confidence: float    # 0.0-1.0 confidence score
citations:           # Code references
  - path: string     # Relative file path
    line: integer    # Line number (optional)
    snippet: string  # Expected content (optional)
links:               # Graph edges
  - type: enum       # related | supersedes | blocks | references
    target: string   # Target memory ID
tags: list[string]   # Classification tags
```

```markdown
# Content schema (Markdown body)

**Fact**: <single sentence stating the knowledge>

**Reasoning**: <why this is true, how it was discovered>

**Action**: <what to do with this knowledge>
```

### 4.2 File Layout

```
memories/
├── index.md                    # Optional: human-curated index
├── mem-api-versioning-001.md
├── mem-deployment-checklist-003.md
├── mem-security-headers-012.md
└── .memory-config.yaml         # Optional: plugin configuration
```

### 4.3 Tool Interface

| Tool | Purpose | Required |
|------|---------|----------|
| `memory_search` | Find memories by query | Yes |
| `memory_save` | Create/update memory | Yes |
| `memory_get` | Retrieve by ID | Yes |
| `memory_verify` | Validate citations | Yes |
| `memory_list` | List all memories | Yes |
| `memory_graph_traverse` | Navigate relationships | Yes |
| `memory_graph_related` | Find referencing memories | Yes |
| `memory_delete` | Remove memory | Yes |
| `memory_batch_verify` | Validate all memories | No (P2) |
| `memory_sync_index` | Sync to vector DB | No (P2) |

### 4.4 Search Behavior

**Default (Lexical):**
```
Query: "api versioning"
→ Tokenize: ["api", "versioning"]
→ Score each memory by keyword overlap in subject + content
→ Return top N sorted by score
```

**Enhanced (Semantic, opt-in):**
```
Query: "api versioning"
→ Lexical search (always)
→ If Chroma available: semantic search
→ Merge, deduplicate by content hash
→ Return top N
```

### 4.5 Performance Requirements

| Operation | Target | Constraint |
|-----------|--------|------------|
| Search (1000 memories) | < 500ms | Lexical only |
| Search (1000 memories) | < 1000ms | With semantic |
| Save | < 100ms | File write |
| Verify (single) | < 200ms | File existence + content check |
| Graph traverse (depth 3) | < 500ms | BFS with 100 nodes |

### 4.6 Dependency Requirements

| Dependency | Status | Purpose |
|------------|--------|---------|
| Python 3.10+ | Required | Runtime |
| PyYAML | Required | Frontmatter parsing |
| chromadb | Optional | Semantic search enhancement |
| sentence-transformers | Optional | Embeddings for Chroma |

---

## 5. Architecture

### 5.1 Component Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                         Tool Layer                               │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────────┐   │
│  │ search   │ │ save     │ │ verify   │ │ graph_traverse   │   │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────────┬─────────┘   │
│       │            │            │                 │              │
└───────┼────────────┼────────────┼─────────────────┼──────────────┘
        │            │            │                 │
        ▼            ▼            ▼                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                        Core Layer                                │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐   │
│  │ MemoryStore  │  │ Citations    │  │ MarkdownGraph        │   │
│  │              │  │              │  │                      │   │
│  │ - search()   │  │ - verify()   │  │ - traverse()         │   │
│  │ - save()     │  │ - parse()    │  │ - find_related()     │   │
│  │ - get()      │  │ - update()   │  │ - find_roots()       │   │
│  └──────┬───────┘  └──────────────┘  └──────────────────────┘   │
│         │                                                        │
└─────────┼────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────┐
│                       Index Layer (Optional)                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐   │
│  │ NullIndex    │  │ ChromaIndex  │  │ ForgetfulIndex       │   │
│  │ (default)    │  │ (opt-in)     │  │ (opt-in)             │   │
│  └──────────────┘  └──────────────┘  └──────────────────────┘   │
│         │                  │                    │                │
│         └──────────────────┴────────────────────┘                │
│                            │                                     │
│                   MemoryIndex (ABC)                              │
│                   - add(memory)                                  │
│                   - search(query) -> [(memory, score)]           │
│                   - health_check() -> bool                       │
└─────────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Storage Layer                               │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                    memories/*.md                          │   │
│  │                    (Git-synchronized)                     │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### 5.2 Data Flow

```
┌─────────┐     ┌─────────────┐     ┌─────────────┐     ┌──────────┐
│ Agent   │────▶│ memory_save │────▶│ MemoryStore │────▶│ .md file │
└─────────┘     └─────────────┘     └──────┬──────┘     └──────────┘
                                           │
                                           ▼ (optional)
                                    ┌─────────────┐
                                    │ ChromaIndex │
                                    └─────────────┘
```

```
┌─────────┐     ┌───────────────┐     ┌─────────────┐
│ Agent   │────▶│ memory_search │────▶│ MemoryStore │
└─────────┘     └───────────────┘     └──────┬──────┘
                                              │
                      ┌───────────────────────┼───────────────────────┐
                      ▼                       ▼                       ▼
               ┌─────────────┐        ┌─────────────┐         ┌─────────────┐
               │ Lexical     │        │ ChromaIndex │         │ Merge &     │
               │ (grep-like) │        │ (optional)  │         │ Deduplicate │
               └─────────────┘        └─────────────┘         └─────────────┘
```

### 5.3 Configuration

```yaml
# .memory-config.yaml (optional)
storage:
  directory: memories           # Default: "memories"
  file_extension: .md          # Default: ".md"

search:
  default_limit: 10            # Default: 10
  min_keyword_length: 3        # Default: 3

index:
  type: null                   # null | chroma | forgetful
  chroma:
    persist_dir: .chroma
    collection: memories
  forgetful:
    endpoint: http://localhost:8020

verification:
  on_retrieval: false          # Verify citations on every get
  stale_threshold_days: 30     # Flag memories not verified in N days

graph:
  max_traversal_depth: 5       # Safety limit for BFS/DFS
```

---

## 6. API Specification

### 6.1 memory_search

```python
def memory_search(
    query: str,
    limit: int = 10,
    verify: bool = False,
    tags: list[str] | None = None
) -> list[MemoryResult]:
    """
    Search memories by query.

    Args:
        query: Search query (keywords or natural language)
        limit: Maximum results to return
        verify: If True, exclude memories with stale citations
        tags: Filter to memories with these tags

    Returns:
        List of MemoryResult with id, subject, content, score, citations
    """
```

### 6.2 memory_save

```python
def memory_save(
    subject: str,
    content: str,
    citations: list[Citation] | None = None,
    links: list[Link] | None = None,
    tags: list[str] | None = None,
    id: str | None = None  # Auto-generated if not provided
) -> SaveResult:
    """
    Save a new memory or update existing.

    Args:
        subject: Brief subject line (< 80 chars)
        content: Full content (Fact + Reasoning + Action)
        citations: Code references [{path, line?, snippet?}]
        links: Graph edges [{type, target}]
        tags: Classification tags
        id: Memory ID (auto-generated if not provided)

    Returns:
        SaveResult with id, path, created flag
    """
```

### 6.3 memory_verify

```python
def memory_verify(
    memory_id: str,
    update_timestamp: bool = True
) -> VerifyResult:
    """
    Verify a memory's citations are still valid.

    Args:
        memory_id: ID of memory to verify
        update_timestamp: If True and valid, update verified timestamp

    Returns:
        VerifyResult with valid flag, stale_citations list, confidence
    """
```

### 6.4 memory_graph_traverse

```python
def memory_graph_traverse(
    root_id: str,
    max_depth: int = 3,
    link_types: list[str] | None = None  # Filter by link type
) -> GraphResult:
    """
    Traverse memory graph from a root node.

    Args:
        root_id: Starting memory ID
        max_depth: Maximum traversal depth
        link_types: Only follow these link types (None = all)

    Returns:
        GraphResult with nodes dict and edges list
    """
```

---

## 7. Implementation Phases

### Phase 1: Core Foundation (Week 1-2)

**Deliverables:**
- [ ] Memory dataclass with YAML frontmatter serialization
- [ ] MemoryStore with save/get/list/delete
- [ ] Lexical search (keyword-based)
- [ ] Basic tool interface (search, save, get, list)
- [ ] Unit tests with >80% coverage

**Exit Criteria:**
- Agent can save and retrieve memories
- All memories are readable markdown files
- Works with zero external dependencies

### Phase 2: Citation System (Week 3)

**Deliverables:**
- [ ] Citation dataclass with path/line/snippet
- [ ] Citation verification (file exists, content matches)
- [ ] memory_verify tool
- [ ] Stale memory detection
- [ ] Integration with memory_search (verify flag)

**Exit Criteria:**
- Memories reference specific code locations
- Stale citations are detected and reported
- Agent can filter out stale memories

### Phase 3: Graph Operations (Week 4)

**Deliverables:**
- [ ] Link dataclass with type/target
- [ ] MarkdownGraph with traverse/find_related/find_roots
- [ ] memory_graph_traverse tool
- [ ] memory_graph_related tool
- [ ] Cycle detection in traversal

**Exit Criteria:**
- Agent can navigate memory relationships
- Graph operations use only file I/O
- No external graph database required

### Phase 4: Progressive Enhancement (Week 5-6)

**Deliverables:**
- [ ] MemoryIndex abstract base class
- [ ] NullIndex (no-op default)
- [ ] ChromaIndex adapter
- [ ] Lazy initialization (import only when used)
- [ ] Configuration file support

**Exit Criteria:**
- Semantic search available when Chroma installed
- No performance regression without Chroma
- Clear opt-in mechanism

### Phase 5: Integration & Polish (Week 7-8)

**Deliverables:**
- [ ] Claude Code skill integration
- [ ] Batch verification tool
- [ ] Pre-commit hook for CI
- [ ] Documentation and examples
- [ ] Migration guide from Serena memories

**Exit Criteria:**
- Plugin works as Claude Code skill
- CI can validate memory integrity
- Existing Serena memories can be migrated

---

## 8. Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Zero-dependency operation | 100% | Works with stdlib only |
| Memory readability | 100% | All memories parseable by `cat`/`grep` |
| Search latency (1000 memories) | < 500ms | Benchmark suite |
| Citation verification accuracy | > 95% | True positive rate |
| Graph traversal correctness | 100% | Test suite with known graphs |
| Adoption | 3+ projects | GitHub search |

---

## 9. Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Lexical search too imprecise | Medium | Medium | Tune keyword extraction; offer semantic opt-in |
| Graph traversal performance | Low | Medium | Lazy loading; depth limits; caching |
| Memory file conflicts (git) | Medium | Low | Stable IDs; merge-friendly format |
| Citation drift (false stales) | Medium | Medium | Fuzzy matching; snippet tolerance |
| Scope creep to require vector DB | High | High | P0 requirement: zero dependencies |

---

## 10. Open Questions

1. **ID Generation**: Deterministic (content hash) vs. random (UUID)?
   - Deterministic allows deduplication but complicates updates
   - Recommendation: `mem-{topic_slug}-{short_hash}`

2. **Link Semantics**: What link types should be supported?
   - Current proposal: `related`, `supersedes`, `blocks`, `references`
   - Should we add `contradicts` for conflict detection?

3. **Multi-repo Memories**: Should memories reference other repositories?
   - Current: No, memories are repo-scoped
   - Future: Consider cross-repo links with full URLs

4. **Memory Expiration**: Should memories auto-expire?
   - Current: No, manual curation
   - Alternative: `expires` field in frontmatter

---

## 11. Appendix

### A. Example Memory File

```markdown
---
id: mem-api-versioning-001
subject: API version must be synchronized between client and server
created: 2026-01-18T10:30:00Z
verified: 2026-01-18T10:30:00Z
confidence: 0.92
citations:
  - path: src/client/constants.ts
    line: 42
    snippet: "export const API_VERSION = 'v2'"
  - path: server/routes/api.ts
    line: 15
    snippet: "router.use('/v2', v2Routes)"
links:
  - type: related
    target: mem-deployment-checklist-003
  - type: supersedes
    target: mem-api-v1-deprecated-012
tags:
  - api
  - versioning
  - client-server
---

**Fact**: Client SDK API_VERSION constant must exactly match server route prefix.

**Reasoning**: Discovered during incident on 2026-01-10 when client was updated to v2 but server routes still used v1 prefix. All API calls returned 404 until routes were updated. The version constant is used in request URL construction.

**Action**: When updating API version:
1. Search for `API_VERSION` in client code
2. Search for route prefix in server code
3. Update both in the same commit
4. Verify with integration tests before merge
```

### B. Comparison with Alternatives

| Feature | This Plugin | Serena | Forgetful | mem0 |
|---------|-------------|--------|-----------|------|
| Markdown canonical | ✅ | ✅ | ❌ | ❌ |
| Zero dependencies | ✅ | ❌ (MCP) | ❌ (MCP) | ❌ (API) |
| Git-synchronized | ✅ | ✅ | ❌ | ❌ |
| Semantic search | Opt-in | ❌ | ✅ | ✅ |
| Citation validation | ✅ | ❌ | ❌ | ❌ |
| Graph traversal | ✅ | ❌ | ✅ | ❌ |
| Human-readable | ✅ | ✅ | ❌ | ❌ |

### C. References

- [GitHub Copilot Agentic Memory System](https://github.blog/ai-and-ml/github-copilot/building-an-agentic-memory-system-for-github-copilot/)
- [Issue #724: Traceability Graph Implementation](https://github.com/rjmurillo/ai-agents/issues/724)
- [ADR-007: Memory-First Architecture](/.agents/architecture/ADR-007-memory-first-architecture.md)
- [ADR-037: Memory Router Architecture](/.agents/architecture/ADR-037-memory-router-architecture.md)
