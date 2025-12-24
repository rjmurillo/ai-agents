# Skill-Memory-TokenEfficiency-001: Optimize for Lexical Discovery Without Embeddings

## Statement

Memory file names and index statements MUST contain dense, high-signal keywords (activation vocabulary) because LLMs map tokens into vector space where association patterns - not symbolic logic - drive selection.

## Context

When designing memory file naming or index entries for the Serena memory system.

## Core Insight: Activation Vocabulary

Imagine generating a list of 5 words that describe a specific skill or memory. That list is **gold** - it's your activation vocabulary.

LLMs break language into tokens and map them into a **vector space**. That space represents **association, not symbolic logic**. Think of it as a word cloud. To optimize memory discovery:

1. **Identify the 5 most associated words** for each memory
2. **Include those words** in file names and index statements
3. **Precision matters** - vague words activate too many associations
4. **Match training data patterns** - use terms from common documentation, not invented jargon

This is "good enough" until we move to a vector database solution with embeddings.

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

2 (PRD-skills-index-registry.md 10-agent consensus, PR #255 evidence)

## Additional Evidence (PR #255)

PR #255 (2025-12-22) demonstrated token optimization in practice:

| Change | Tokens Saved |
|--------|-------------|
| Comment stripping (copilot-synthesis.yml) | ~2,400 |
| Test separation (.github/tests/) | ~1,500 |
| Schema deletion | ~500 |
| Reference extraction | ~200 |
| **Total** | **~4,600** |

These savings apply the same principles to skill files:
- Atomic files with activation vocabulary in names
- Progressive disclosure (workflow vs. reference content)
- Execution-focused content only in skill directories

## Created

2025-12-20

## Updated

2025-12-22 (PR #255 evidence added)
