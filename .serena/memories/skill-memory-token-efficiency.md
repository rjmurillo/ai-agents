# Skill-Memory-TokenEfficiency-001: Optimize for Lexical Discovery Without Embeddings

## Statement

Memory file names and index statements MUST contain dense, high-signal keywords because agents select memories based on word frequency matching, not semantic similarity.

## Context

When designing memory file naming or index entries for the Serena memory system.

## Evidence

PRD-skills-index-registry.md (2025-12-20) - 10-agent consensus validated that:

- Serena MCP operates without embeddings or vector databases
- Agents must "want to choose" a memory based on its name before reading content
- Consolidating files reduces `list_memories` token cost but degrades discoverability
- Atomic files with descriptive names maximize selection probability

## The Trade-off

| Approach | `list_memories` Cost | Per-read Cost | Discovery |
|----------|---------------------|---------------|-----------|
| Many small files | Higher (100+ names) | Lower (focused) | Name-based |
| Few large files | Lower (15 names) | Higher (scanning) | Content-based |

**Current architecture choice**: Many small files + index registry

## Why Atomic Files Win

1. **Word frequency density**: Each file name is a mini-summary that triggers relevance matching
2. **Focused reads**: No token waste scanning irrelevant content in consolidated libraries
3. **Two-layer discovery**: File name (coarse filter) → Index statement (fine filter) → Read (precision)

## Anti-pattern

```text
# BAD: Consolidated library
skills-powershell.md  # 15 skills inside, must read entire file to find one

# GOOD: Atomic file with descriptive name
skill-powershell-null-safety-contains-operator.md  # Name tells you what's inside
```

## Future Evolution

Embeddings + vector database would provide ~10x improvement:

- Semantic similarity search instead of lexical matching
- Automatic relevance ranking
- Cross-skill concept linking

Until then, maximize discoverability within lexical constraints.

## Atomicity

92%

## Tag

architecture

## Validation

1 (PRD-skills-index-registry.md 10-agent consensus)

## Created

2025-12-20
