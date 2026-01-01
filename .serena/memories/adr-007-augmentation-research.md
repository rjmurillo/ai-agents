# ADR-007 Augmentation Research (2026-01-01)

## Sources Researched

1. **Forgetful MCP** (https://github.com/ScottRBK/forgetful)
2. **BMAD Method** (https://github.com/bmad-code-org/BMAD-METHOD)
3. **Zettelkasten Method** (https://zettelkasten.de/introduction/)
4. **A-MEM** (https://arxiv.org/abs/2502.12110)

## Key Findings

### Forgetful MCP
- Meta-tools pattern: 3 tools expose 42 underlying operations, preserving context window
- Dual graph architecture: Memory graph (concepts) + Entity graph (real-world objects)
- Auto-linking: Cosine similarity ≥0.7 triggers bidirectional links to top 3-5 matches
- Token budget: Configurable limit (default 8000 tokens, 20 memories max)
- Multi-stage retrieval: Dense search → Sparse search → RRF fusion → Cross-encoder reranking

### BMAD Method
- Sidecar files: Persistent `memories.md` per agent in `{agent-name}-sidecar/` folders
- Critical actions: Memory loading enforced before task execution
- Scale-adaptive routing: Quick Flow / BMad Method / Enterprise Method tracks
- Party Mode: Multi-agent collaboration for complex decisions

### Zettelkasten Principles
- **Atomicity**: One concept per note (300-400 words optimal)
- **Unique IDs**: Stable identifiers enable robust cross-referencing
- **Explicit Linking**: Connections with context explaining relationship
- **Emergence**: Patterns emerge from the growing network

### A-MEM (arXiv 2502.12110)
- Dynamic memory organization with contextual descriptions, keywords, tags
- Intelligent linking based on meaningful similarities
- Memory evolution: New memories trigger updates to existing attributes
- Superior improvement over SOTA baselines across six foundation models

## ADR-007 Changes Applied
- Added Extended Research section with source descriptions
- Added Zettelkasten Principles table with implementation guidance
- Added Dual Memory Architecture section (Serena vs Forgetful routing)
- Added Forgetful Integration section with code examples
- Added BMAD-Inspired Enhancements for future consideration
- Updated References with all source links

## Related

- ADR-007-memory-first-architecture.md (augmented)
- Forgetful memory ID: 15 (research summary) - note: only available on local instances
- memory-architecture-serena-primary.md (critical: Serena as canonical layer)
- memory-index.md (Serena memory catalog)

## Cross-Platform Note

This research is persisted to Serena (this file) as the canonical source. Forgetful memory ID 15 contains the same content but is only accessible on local instances with the Forgetful SQLite database. Hosted platforms (GitHub Copilot) should reference this Serena memory.