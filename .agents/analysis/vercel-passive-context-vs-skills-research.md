# Vercel Research: AGENTS.md Passive Context vs Skills

**Date**: 2026-02-08
**Source**: [Vercel Blog - AGENTS.md outperforms skills in our agent evals](https://vercel.com/blog/agents-md-outperforms-skills-in-our-agent-evals)
**Related**: [Agent Skills FAQ](https://vercel.com/blog/agent-skills-explained-an-faq), [vercel-labs/agent-skills](https://github.com/vercel-labs/agent-skills)

## Executive Summary

Vercel research demonstrates that embedding compressed documentation directly in AGENTS.md achieves 100% pass rates on Next.js 16 API evaluations, compared to 79% for skills with explicit instructions and 53% for baseline. This finding challenges skill-based retrieval architectures and supports "retrieval-led reasoning over pre-training-led reasoning."

## Performance Metrics

| Configuration | Build | Lint | Test | Overall |
|--------------|-------|------|------|---------|
| Baseline (no docs) | 84% | 95% | 63% | **53%** |
| Skill (default behavior) | 84% | 89% | 58% | **53%** |
| Skill + explicit instructions | 95% | 100% | 84% | **79%** |
| AGENTS.md docs index | 100% | 100% | 100% | **100%** |

**Key Insight**: The 47 percentage point improvement (53% → 100%) from passive context demonstrates fundamental architectural advantage.

## Evaluation Methodology

### Hardened Eval Suite

Vercel targeted Next.js 16 APIs absent from model training data:

- `connection()` for dynamic rendering
- `'use cache'` directive
- `cacheLife()` and `cacheTag()`
- `forbidden()` and `unauthorized()`
- `proxy.ts` for API proxying
- Async `cookies()` and `headers()`
- `after()`, `updateTag()`, `refresh()`

### Testing Rigor

- Eliminated ambiguous prompts
- Resolved contradictions
- Shifted to behavior-based assertions over implementation details
- Focus on APIs outside training data (novel knowledge testing)

## Why Passive Context Outperforms Skills

### Three Critical Factors

1. **Elimination of Decision Points**: Documentation is constantly available. No agent judgment required about when to access it.

2. **Consistent Availability**: AGENTS.md content persists in the system prompt every turn. Skills load asynchronously only when invoked.

3. **Avoided Sequencing Problems**: No ordering conflicts about when documentation should be consulted versus project exploration.

**Quote**: "With AGENTS.md, there's no moment where the agent must decide 'should I look this up?'"

### Instruction Fragility

Different wordings produced dramatically different outcomes with skills:

| Instruction Approach | Behavior | Result |
|---------------------|----------|--------|
| "You MUST invoke the skill" | Anchored on documentation patterns | Missed project context |
| "Explore project first, then invoke skill" | Built mental model first | Better results |

**Failure Example**: The "invoke first" approach correctly wrote `page.tsx` but completely missed required `next.config.ts` changes.

### Production Reliability Concern

The fragility of skill-based approaches concerned researchers. Minor prompt changes caused significant behavioral differences, making production reliability unpredictable.

## Context Optimization

### Compression Achievement

- Initial documentation: 40KB
- Compressed format: 8KB
- Reduction: **80%**
- Pass rate maintained: **100%**

### Compressed Format Structure

The optimized format uses:

- Pipe-delimited structure
- Index system pointing to retrievable files
- On-demand file loading rather than upfront embedding

Example structure:

```text
[Next.js 16 APIs]
|connection(): dynamic rendering (see: .next-docs/dynamic.md)
|'use cache': caching directive (see: .next-docs/cache.md)
|cacheLife()/cacheTag(): cache control (see: .next-docs/cache-api.md)
```

## Framework Author Recommendations

### For General Framework Knowledge

Provide compressed AGENTS.md snippets rather than relying on skills.

### When Skills Remain Useful

- Vertical, action-specific workflows
- Explicitly triggered by users
- Version upgrades or migration tasks
- Tasks requiring tool access (file modification, API calls)

### Best Practices

1. Don't wait for improved skill implementation. Results matter now.
2. Compress documentation aggressively. Full content isn't necessary.
3. Build evals targeting APIs outside training data.
4. Structure docs for file-based retrieval rather than upfront loading.

## Implementation

```bash
npx @next/codemod@canary agents-md
```

This command:

1. Detects Next.js version
2. Downloads matching documentation to `.next-docs/`
3. Injects compressed index into `AGENTS.md`

## Theoretical Framework

### Retrieval-Led vs Pre-Training-Led Reasoning

| Aspect | Pre-Training-Led | Retrieval-Led |
|--------|------------------|---------------|
| Source | Model's training data | Context window docs |
| Freshness | Stale (training cutoff) | Current (injected) |
| Reliability | Variable | High (verified content) |
| Coverage | Incomplete | Comprehensive |

The research concludes that shifting agents from "pre-training-led reasoning to retrieval-led reasoning" represents the most reliable current approach to accurate code generation.

### Decision Point Elimination

The fundamental insight is that skills create decision points where agents must choose whether to retrieve documentation. These decision points introduce failure modes:

1. Agent doesn't recognize need for skill
2. Agent retrieves skill too late (after making decisions)
3. Agent retrieves skill but doesn't integrate with project context
4. Skill content conflicts with project exploration order

Passive context eliminates all four failure modes.

## Project Applicability: ai-agents

### Current Architecture Alignment

| Aspect | ai-agents Current | Vercel Recommendation | Status |
|--------|-------------------|----------------------|--------|
| CLAUDE.md under 100 lines | Yes (66 lines) | Yes | ALIGNED |
| @imports for critical context | Yes | Yes | ALIGNED |
| Compressed format | Partial | Full | OPPORTUNITY |
| Pipe-delimited index | No | Yes | OPPORTUNITY |
| Skill-first for actions | Yes | Yes | ALIGNED |
| Passive context for knowledge | Partial | Yes | OPPORTUNITY |

### Integration Opportunities

**High Priority (Immediate)**:

1. **Compress CRITICAL-CONTEXT.md**: Apply pipe-delimited format to reduce token usage while maintaining 100% information density.

2. **Skill vs Passive Decision Framework**: Document when to use skills (actions) vs passive context (knowledge).

3. **Memory Index Optimization**: Convert memory-index from table format to compressed pipe-delimited format.

**Medium Priority (Near-term)**:

4. **Eval Suite Development**: Build evals for our own protocol compliance targeting behaviors outside model training data.

5. **Skill Pruning**: Convert knowledge-heavy skills to passive context, keep action-heavy skills.

**Low Priority (Long-term)**:

6. **Automatic Context Compression**: Tool to compress markdown documentation to minimal tokens.

### Recommended Actions

1. **Create ADR**: Document decision to prefer passive context for framework knowledge, skills for tool-based actions.

2. **Update SKILL-QUICK-REF.md**: Add section clarifying when passive context vs skills applies.

3. **Memory Architecture Update**: Consider moving frequently-used memory patterns into @imported passive context.

4. **Eval Suite**: Build verification tests for session protocol compliance using behavior-based assertions.

## Failure Modes Catalog

### Skills-Based Approach Failures

| Failure Mode | Cause | Impact | Prevention |
|-------------|-------|--------|------------|
| Late retrieval | Decision point ordering | Decisions made without context | Passive context |
| Partial retrieval | Skill scope mismatch | Missing related information | Broader skill or passive context |
| Context burial | Large skill content | Key info not surfaced | Compressed index format |
| Integration failure | Skills vs project order | Correct skill, wrong application | Explore-first instruction |
| Instruction fragility | Minor prompt changes | Unpredictable behavior | Passive context |

### Passive Context Limitations

| Limitation | Cause | Mitigation |
|-----------|-------|------------|
| Token overhead | Always-loaded content | Aggressive compression (80% reduction achievable) |
| Update lag | Manual refresh needed | Automated codemod tools |
| Scope creep | Temptation to add more | 100-line limit enforcement |

## Quantitative Impact Summary

| Metric | Before (Skills) | After (AGENTS.md) | Improvement |
|--------|-----------------|-------------------|-------------|
| Pass rate | 53-79% | 100% | +21-47pp |
| Context size | 40KB (full) | 8KB (compressed) | 80% reduction |
| Decision points | Multiple | Zero | Eliminated |
| Instruction sensitivity | High | None | Eliminated |

## Related Research

- [claude-md-anthropic-best-practices](../serena/memories/claude-md-anthropic-best-practices.md): Anthropic guidance on CLAUDE.md file structure
- [claude-code-skills-official-guidance](../serena/memories/claude-code-skills-official-guidance.md): Skill frontmatter and progressive disclosure
- [prompting-observations](../serena/memories/prompting-observations.md): Prompt fragility and scope explosion findings
- [memory-token-efficiency](../serena/memories/memory-token-efficiency.md): Token optimization patterns

## Sources

- [Vercel Blog: AGENTS.md outperforms skills in our agent evals](https://vercel.com/blog/agents-md-outperforms-skills-in-our-agent-evals)
- [Vercel Blog: Agent Skills Explained FAQ](https://vercel.com/blog/agent-skills-explained-an-faq)
- [GitHub: vercel-labs/agent-skills](https://github.com/vercel-labs/agent-skills)
- [Hacker News Discussion](https://news.ycombinator.com/item?id=46809708)
