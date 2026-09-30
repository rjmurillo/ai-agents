# Memory Architecture: Serena as Primary Persistence Layer

## Critical Insight

Serena memories (`.serena/memories/*.md`) are the **only truly shared persistent memory** across:

- Multiple VMs running in parallel
- Different platforms (GitHub Copilot, Claude Code, local development)
- Hosted environments where local databases aren't accessible

## Why Serena Over Claude-Mem

| Layer | Scope | Persistence | Cross-Platform |
|-------|-------|-------------|----------------|
| **Serena** | Project | Git-synchronized markdown | ✅ Yes |
| **Claude-mem** | Local | SQLite database | ❌ No |

**Key insight**: Claude-mem may be available on hosted platforms, but **the database contents are not**. Only Serena memories travel with the repository.

Forgetful was decommissioned (#5574, PR #6008, ADR-106). It is no longer a supplementary layer.

## Implications for Memory-First Architecture (ADR-007)

1. **Serena is canonical**: All important patterns, decisions, and cross-references MUST be in Serena
2. **Serena is the only durable layer**: Forgetful is decommissioned (ADR-106), so no other store holds findings
3. **Bi-directional linking**: Capture relationships explicitly in Serena markdown (no auto-linking available)
4. **Cross-reference format**: Use explicit links like `See: [memory-name]` to enable manual graph traversal

## Memory Workflow

```text
1. Discover with `search_memory.py` or `memory-index.md`
2. Persist to Serena → markdown files with explicit cross-refs
3. Commit with code → Git synchronizes to all platforms
```

## Related

- ADR-007-memory-first-architecture.md (augmented with Zettelkasten, Forgetful, BMAD concepts)
- adr-007-augmentation-research.md (research summary)
- memory-index.md (Serena memory catalog)

## Related

- [memory-001-feedback-retrieval](memory-001-feedback-retrieval.md)
- [memory-index](../memory-index.md)
- [memory-size-001-decomposition-thresholds](memory-size-001-decomposition-thresholds.md)
- [memory-system-fragmentation-tech-debt](memory-system-fragmentation-tech-debt.md)
- [memory-token-efficiency](memory-token-efficiency.md)
