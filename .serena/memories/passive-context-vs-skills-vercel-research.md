# Passive Context vs Skills: Vercel Research Findings

**Date**: 2026-02-08
**Source**: Vercel blog, January 2026
**Confidence**: HIGH (quantitative eval data)

## Core Finding

AGENTS.md passive context achieves 100% pass rate vs 79% for skills with instructions (53% baseline).

## Why Passive Context Wins

1. **No decision points**: Agent never decides "should I look this up?"
2. **Consistent availability**: Every turn, not on-demand
3. **No sequencing conflicts**: Documentation before decisions

## Key Metrics

| Approach | Pass Rate |
|----------|-----------|
| Baseline | 53% |
| Skills (default) | 53% |
| Skills + instructions | 79% |
| AGENTS.md passive | 100% |

## Compression

40KB → 8KB (80% reduction) with 100% pass rate maintained.

## When to Use Which

| Use Case | Approach |
|----------|----------|
| Framework knowledge | Passive context (AGENTS.md) |
| Tool-based actions | Skills |
| User-triggered workflows | Skills |
| Always-needed info | Passive context |

## Project Application

ai-agents is partially aligned:
- CLAUDE.md under 100 lines (ALIGNED)
- @imports pattern (ALIGNED)
- Compressed format (OPPORTUNITY)
- Skill vs passive decision framework (OPPORTUNITY)

## Failure Modes Skills Create

1. Late retrieval (decisions made first)
2. Instruction fragility (prompt changes break behavior)
3. Context burial (skill content overwhelms)
4. Integration failure (skill vs project order)

## Related

- [claude-md-anthropic-best-practices](claude-md-anthropic-best-practices.md)
- [claude-code-skills-official-guidance](claude-code-skills-official-guidance.md)
- [prompting-observations](prompting-observations.md)
- [memory-token-efficiency](memory-token-efficiency.md)

## Analysis

Full analysis: `.agents/analysis/vercel-passive-context-vs-skills-research.md`
