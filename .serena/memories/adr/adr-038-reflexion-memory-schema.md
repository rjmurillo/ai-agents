# ADR-038 Reflexion Memory Schema

**Status**: Proposed. Tier 3 removed by ADR-089.
**Date**: 2026-01-01
**Task**: M-004 (Phase 2A)

> Tier 3 (Causal) below was implemented and then deleted. ADR-089 found it was a
> derived cache of the Tier 2 episodes that nothing read, whose aggregated
> patterns were noise. Tiers 0 through 2 stand. Do not implement Tier 3.
> `caused_by`/`leads_to` links inside an episode are unaffected and still ship.

## Summary

Reflexion memory architecture for episodic replay. Originally four tiers; Tier 3 was removed by ADR-089.

## Tiers

| Tier | Name | Storage | Purpose |
|------|------|---------|---------|
| 0 | Working | Context window | Current task focus |
| 1 | Semantic | Serena + Forgetful | Facts, patterns, rules |
| 2 | Episodic | `.agents/memory/episodes/` | Session transcripts, decisions |
| 3 | Causal | REMOVED by ADR-089 | Was cause-effect graphs; had no reader |

## Key Files

- `.agents/architecture/ADR-038-reflexion-memory-schema.md` - Full ADR
- .agents/schemas/episode.schema.json (removed) - Episode JSON schema
- `.agents/memory/causality/causal-graph.json` (removed by ADR-089)

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
3. ~~Implement `Update-CausalGraph.ps1`~~ (built, then removed by ADR-089)

Shipped as Python, not PowerShell: `memory_core/reflexion_memory.py` and
`scripts/extract_session_episode.py` under `.claude/skills/memory/`.

## Related

- [adr-007-augmentation-research](adr-007-augmentation-research.md)
- [adr-014-findings](adr-014-findings.md)
- [adr-014-review-findings](adr-014-review-findings.md)
- [adr-019-quantitative-analysis](adr-019-quantitative-analysis.md)
- [adr-021-quantitative-analysis](adr-021-quantitative-analysis.md)
