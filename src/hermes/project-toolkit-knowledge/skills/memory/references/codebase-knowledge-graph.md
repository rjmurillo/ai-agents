---
source: wiki/concepts/AI Productivity/Codebase Knowledge Graph for AI Agents.md
created: 2026-04-11
review-by: 2026-07-11
---

# Codebase Knowledge Graph for AI Agents (GitNexus Pattern)

Index a codebase into a knowledge graph exposing dependencies, call chains, clusters, and execution flows via MCP. Gives AI agents structural context that embeddings and RAG cannot provide.

## Knowledge Graph vs Embeddings/RAG

| Approach | What You Get |
|----------|--------------|
| Embeddings/RAG | Semantic similarity: finds similar text |
| Knowledge graph | Structural relationships: call chains, dependencies, blast radius |
| GitNexus | Both: BM25 + semantic + RRF hybrid, backed by graph |

Embeddings say "this code is similar to that code." A knowledge graph says "changing this function breaks these 7 callers in these 3 files."

## Key MCP Tools

| Tool | Value |
|------|-------|
| `impact` | Blast radius: what breaks if you change X |
| `detect_changes` | Git-diff to affected processes (not just files) |
| `context` | 360-degree symbol view: all callers, callees, process participation |
| `query` | Hybrid BM25 + semantic search |
| `rename` | Multi-file coordinated rename with graph validation |
| `cypher` | Raw graph queries for custom analysis |

## Setup

```bash
npx gitnexus analyze  # index + install skills + register hooks + write AGENTS.md
```

Claude Code integration: PreToolUse hooks enrich searches with graph context before the agent acts. PostToolUse hooks auto-reindex after commits.

## Relationship to Memory Tiers

- **Tier 1 (Semantic)**: Facts, patterns, constraints. Knowledge graph is complementary structural memory, not conversational memory.
- **Two-Tier Orientation**: Knowledge graph gives precision during execution. Two-tier orientation gives context at session start.
- **Impact analysis**: `impact` tool directly reduces the "blind edit" problem where changing X silently breaks Y.

## Enterprise Use Cases

- **PR Review**: Automated blast radius analysis catches "you changed X but didn't update Y which calls it"
- **Auto-updating Code Wiki**: Knowledge graph generates always-current documentation
- **Multi-repo contract sync**: Extract and match API contracts across services
- **Regression forensics**: Trace failures back through call chains

## Relevance to ai-agents Repo

- Auto-generates AGENTS.md compatible with the harness pattern
- `detect_changes` maps to test-impact analysis (run only affected tests)
- `group` commands enable multi-repo analysis across project constellation
