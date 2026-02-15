# ADR-038 Reflexion Memory Schema

**Status**: Proposed
**Date**: 2026-01-01
**Task**: M-004 (Phase 2A)

## Summary

Four-tier reflexion memory architecture for episodic replay and causal reasoning.

## Tiers

| Tier | Name | Storage | Purpose |
|------|------|---------|---------|
| 0 | Working | Context window | Current task focus |
| 1 | Semantic | Serena + Forgetful | Facts, patterns, rules |
| 2 | Episodic | `.agents/memory/episodes/` | Session transcripts, decisions |
| 3 | Causal | `.agents/memory/causality/` | Cause-effect graphs |

## Key Files

- `.agents/architecture/ADR-038-reflexion-memory-schema.md` - Full ADR
- .agents/schemas/episode.schema.json (removed) - Episode JSON schema
- .agents/schemas/causal-graph.schema.json (removed) - Causal graph schema
- `.agents/memory/causality/causal-graph.json` - Initial empty graph

## Episode Structure

```json
{
  "id": "episode-YYYY-MM-DD-NNN",
  "session": "session-id",
  "outcome": "success|partial|failure",
  "decisions": [...],
  "events": [...],
  "lessons": [...]
}
```

## Next Steps (M-005)

1. Create `.claude/skills/memory/scripts/ReflexionMemory.psm1` module
2. Implement `Extract-SessionEpisode.ps1`
3. Implement `Update-CausalGraph.ps1`

## Related

- [adr-007-augmentation-research](adr-007-augmentation-research.md)
- [adr-014-findings](adr-014-findings.md)
- [adr-014-review-findings](adr-014-review-findings.md)
- [adr-019-quantitative-analysis](adr-019-quantitative-analysis.md)
- [adr-021-quantitative-analysis](adr-021-quantitative-analysis.md)
