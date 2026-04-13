# ADR-038: Reflexion Memory Schema

## Status

Proposed

## Date

2026-01-01

## Context

The ai-agents system currently lacks episodic memory and causal reasoning capabilities. Agents cannot:

1. **Replay past decisions**: No structured storage of decision sequences
2. **Analyze failures causally**: No cause-effect relationship tracking
3. **Perform what-if analysis**: No counterfactual reasoning support
4. **Learn from session history**: Session logs exist but are not queryable

Issue #180 proposes implementing reflexion memory with causal reasoning, based on claude-flow's ReflexionMemory pattern which achieves 84.8% SWE-Bench solve rate through coordinated learning.

### Current Memory Architecture

| Tier | System | Type | Query |
|------|--------|------|-------|
| L1 | Serena | Lexical | Keyword match |
| L2 | Forgetful | Semantic | Vector similarity |
| - | Session logs | Unstructured | Manual reading |

**Gap**: No episodic tier for event sequences or causal tier for cause-effect relationships.

### Forces

1. **Token efficiency**: Session transcripts are large (10K-50K tokens each)
2. **Query latency**: Must support fast retrieval during agent execution
3. **Causal integrity**: Cause-effect links must be verifiable
4. **Integration**: Must work with existing Serena/Forgetful infrastructure

## Decision

Implement a **Four-Tier Reflexion Memory Schema** with episodic replay and causal graph capabilities.

### Tier Architecture

```text
┌─────────────────────────────────────────────────────────────┐
│                    Working Memory (Tier 0)                   │
│         Current context window, recent interactions          │
│                    (Managed by Claude)                       │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│                   Semantic Memory (Tier 1)                   │
│          Facts, patterns, rules - Serena + Forgetful         │
│                    (ADR-037 Memory Router)                   │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│                   Episodic Memory (Tier 2)                   │
│      Session transcripts, decision sequences, outcomes       │
│               (NEW: .agents/memory/episodes/)                │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│                    Causal Memory (Tier 3)                    │
│        Cause-effect graphs, counterfactual analysis          │
│              (NEW: .agents/memory/causality/)                │
└─────────────────────────────────────────────────────────────┘
```

### Episodic Memory Schema (Tier 2)

Episodes are structured extracts from session logs, optimized for replay and analysis.

**Storage**: `.agents/memory/episodes/{session-id}.json`

```json
{
  "id": "episode-2026-01-01-126",
  "session": "2026-01-01-session-126",
  "timestamp": "2026-01-01T17:00:00Z",
  "outcome": "success|partial|failure",
  "task": "Implement MemoryRouter module",
  "decisions": [
    {
      "id": "d001",
      "timestamp": "2026-01-01T17:05:00Z",
      "type": "design|implementation|test|recovery",
      "context": "Choosing routing strategy",
      "options": ["Forgetful-first", "Serena-first", "Parallel"],
      "chosen": "Serena-first",
      "rationale": "Lower latency, no network dependency",
      "outcome": "success",
      "effects": ["d002", "d003"]
    }
  ],
  "events": [
    {
      "id": "e001",
      "timestamp": "2026-01-01T17:10:00Z",
      "type": "tool_call|error|milestone|handoff",
      "content": "Created MemoryRouter.psm1",
      "caused_by": ["d001"],
      "leads_to": ["e002"]
    }
  ],
  "metrics": {
    "duration_minutes": 45,
    "tool_calls": 87,
    "errors": 2,
    "recoveries": 2
  },
  "lessons": [
    "Pre-commit hooks check all markdown, not just staged files",
    "Use --no-verify with documented justification for unrelated failures"
  ]
}
```

### Causal Memory Schema (Tier 3)

Causal graphs track cause-effect relationships across episodes.

**Storage**: `.agents/memory/causality/causal-graph.json`

```json
{
  "version": "1.0",
  "updated": "2026-01-01T18:00:00Z",
  "nodes": [
    {
      "id": "n001",
      "type": "decision|event|outcome|pattern",
      "label": "Choose Serena-first routing",
      "episodes": ["episode-2026-01-01-126"],
      "frequency": 1,
      "success_rate": 1.0
    }
  ],
  "edges": [
    {
      "source": "n001",
      "target": "n002",
      "type": "causes|enables|prevents|correlates",
      "weight": 0.95,
      "evidence_count": 1
    }
  ],
  "patterns": [
    {
      "id": "p001",
      "name": "Pre-commit bypass pattern",
      "description": "When lint errors are in unrelated files, use --no-verify with justification",
      "trigger": "E_MARKDOWNLINT_FAIL on unstaged files",
      "action": "Document justification, use --no-verify",
      "success_rate": 1.0,
      "occurrences": 2
    }
  ]
}
```

### Query Interface

New module: `scripts/ReflexionMemory.psm1`

```powershell
# Episode queries
Get-Episode -SessionId "2026-01-01-session-126"
Get-Episodes -Outcome "failure" -Since (Get-Date).AddDays(-7)
Get-DecisionSequence -EpisodeId "episode-2026-01-01-126"

# Causal queries
Get-CausalPath -From "decision-X" -To "outcome-Y"
Get-WhatIf -Decision "alternative-option" -Episode "episode-X"
Get-SimilarDecisions -Context "routing strategy"

# Pattern queries
Get-Patterns -MinSuccessRate 0.7 -MinOccurrences 3
Get-AntiPatterns -MaxSuccessRate 0.3
```

### Episode Extraction Pipeline

Episodes are extracted from session logs automatically:

```text
Session Log (.agents/sessions/*.md)
         │
         ▼
┌─────────────────────────────┐
│  Extract-SessionEpisode.ps1 │
│  - Parse decisions          │
│  - Identify outcomes        │
│  - Link cause-effect        │
└─────────────────────────────┘
         │
         ▼
Episode JSON (.agents/memory/episodes/*.json)
         │
         ▼
┌─────────────────────────────┐
│  Update-CausalGraph.ps1     │
│  - Add nodes/edges          │
│  - Update weights           │
│  - Identify patterns        │
└─────────────────────────────┘
         │
         ▼
Causal Graph (.agents/memory/causality/causal-graph.json)
```

### Integration with Existing Systems

| System | Integration |
|--------|-------------|
| **Serena** | Episodes reference Serena memories by name |
| **Forgetful** | Episode summaries stored as Forgetful memories |
| **Memory Router** | New `Search-Episode` function in ADR-037 |
| **Retrospective Agent** | Auto-extracts episodes at session end |
| **Session Protocol** | Episode extraction added to session end checklist |

## Rationale

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|-------------|------|------|----------------|
| Store full transcripts | Complete information | 10-50K tokens each, expensive queries | Token cost prohibitive |
| Graph database (Neo4j) | Native graph queries | External dependency, complexity | Overkill for current scale |
| Forgetful only | Already exists | No causal structure, no decision tracking | Insufficient for reflexion |
| Markdown-based | Human readable | Not queryable, no graph traversal | Can't do what-if analysis |

### Trade-offs

1. **JSON vs Markdown**: JSON enables programmatic queries at cost of human readability
2. **Episode extraction vs Full storage**: Reduced token cost, but information loss possible
3. **Single file vs Directory**: Single causal graph file simplifies queries but limits parallelism

## Consequences

### Positive

- Agents can learn from past failures with causal reasoning
- What-if analysis enables better decision making
- Pattern auto-consolidation reduces manual skillbook work
- Structured episodes are more queryable than session logs

### Negative

- Additional storage overhead (~5KB per episode)
- Episode extraction adds processing to session end
- Causal graph may grow large over time (needs pruning strategy)

### Neutral

- JSON format requires tooling for human inspection
- Existing session logs remain canonical; episodes are derived

## Implementation Notes

### Phase 1: M-004 Schema (This ADR)

1. Create `.agents/memory/episodes/` directory structure
2. Create `.agents/memory/causality/` directory structure
3. Define JSON schema validation
4. Document episode format

### Phase 2: M-005 Implementation

1. Create `scripts/ReflexionMemory.psm1` module
2. Implement `Extract-SessionEpisode.ps1`
3. Implement `Update-CausalGraph.ps1`
4. Create Pester test suite

### Phase 3: Integration

1. Update retrospective agent to auto-extract episodes
2. Add episode search to Memory Router
3. Update Session Protocol with episode extraction step
4. Create causal graph visualization (optional)

### Token Budget Targets

| Operation | Target | Rationale |
|-----------|--------|-----------|
| Episode retrieval | <500 tokens | Structured, compressed |
| Causal path query | <200 tokens | Graph traversal only |
| Pattern lookup | <100 tokens | Index-based |
| What-if analysis | <1000 tokens | Includes context |

## Related Decisions

- ADR-007: Memory-First Architecture (establishes memory patterns)
- ADR-017: Tiered Memory Index Architecture (tier structure)
- ADR-037: Memory Router Architecture (unified search)

## References

- Issue #180: Reflexion Memory with Causal Reasoning
- Issue #167: Vector Memory System (prerequisite)
- Claude-flow ReflexionMemory: https://github.com/ruvnet/claude-flow
- Phase 2A Gap Analysis: `.agents/analysis/123-phase2a-memory-architecture-review.md`

---

*Template Version: 1.0*
*Task: M-004 (Phase 2A Memory System)*
