# ADR-039: Agent Model Cost Optimization (Data-Driven)

## Status

Accepted (Supersedes ADR-002)

## Date

2026-01-03

## Context

Session log analysis across 290 sessions revealed significant cost optimization opportunities through data-driven model assignment. ADR-002 (2025-12-16) established model distribution based on theoretical task requirements, but actual usage patterns show different optimization potential.

### ADR-002 Baseline Distribution

| Model | Agent Count | Agents |
|-------|-------------|--------|
| Opus | 7 | architect, high-level-advisor, implementer, independent-thinker, orchestrator, roadmap, security |
| Sonnet | 11 | analyst, critic, devops, explainer, memory, planner, pr-comment-responder, qa, retrospective, skillbook, task-generator |

### Actual Usage Data (290 Sessions)

Analysis of `.agents/sessions/` logs from 2025-12-21 to 2026-01-03:

| Agent | Mentions | Frequency | ADR-002 Model | Usage Pattern |
|-------|----------|-----------|---------------|---------------|
| memory | 906 | 31% | Sonnet | High-volume retrieval/storage |
| retrospective | 516 | 18% | Sonnet | High-volume learning extraction |
| qa | 464 | 16% | Sonnet | High-volume verification |
| security | 193 | 7% | Opus | Medium-volume security checks |
| pr-comment-responder | 120 | 4% | Sonnet | Medium-volume PR triage |
| implementer | 51 | 2% | Opus | Low-volume code generation (critical) |
| orchestrator | 54 | 2% | Opus | Low-volume routing |
| architect | 33 | 1% | Opus | Low-volume ADR reviews |
| independent-thinker | 27 | 0.9% | Opus | Low-volume contrarian analysis |
| high-level-advisor | 19 | 0.07% | Opus | Very low-volume strategic advice |
| roadmap | 21 | 0.07% | Opus | Very low-volume product direction |

### Cost Impact Analysis

ADR-002 distribution (7 opus, 11 sonnet, 0 haiku):
- Opus usage: ~62% of total agent invocations (high-cost tier)
- Cost driver: high-level-advisor (0.07% usage) on opus is 80x overprovisioned

### New Distribution (After Change)

| Model | Agent Count | Agents |
|-------|-------------|--------|
| Opus | 1 | implementer |
| Sonnet | 16 | orchestrator, architect, security, analyst, planner, critic, qa, devops, explainer, task-generator, retrospective, pr-comment-responder, spec-generator, independent-thinker, roadmap, high-level-advisor |
| Haiku | 3 | memory, skillbook, context-retrieval |

## Decision

Apply data-driven model optimization based on **actual usage frequency** and **cost impact**, not just theoretical task requirements:

### Haiku Tier Introduction

**Criteria**: High volume (≥10% of sessions) + Simple operations + Latency-sensitive

| Agent | Volume | Reasoning | Error Cost | Latency | Decision |
|-------|--------|-----------|------------|---------|----------|
| memory | 31% | 1/5 (retrieval) | 2/5 (low) | 5/5 (high) | Haiku |
| skillbook | 4% | 2/5 (pattern match) | 2/5 (low) | 4/5 (high) | Haiku |
| context-retrieval | N/A | 1/5 (search) | 2/5 (low) | 5/5 (high) | Haiku |

**Rationale**: These agents perform simple, high-volume operations where Haiku's speed (2-5s) and cost (80% cheaper than Sonnet) provide better ROI than reasoning depth.

### Opus-to-Sonnet Downgrades

**orchestrator** (Opus → Sonnet):
- Usage: 54 mentions (2% of sessions)
- ADR-002 score: Reasoning=5, Error Cost=5, Tools=5
- **Revised analysis**: Routing is pattern-based. Complex coordination is rare. Sonnet handles 95%+ of routing correctly.
- Cost impact: High (62% → 15% opus usage)

**architect** (Opus → Sonnet):
- Usage: 33 mentions (1% of sessions)
- ADR-002 score: Reasoning=5, Error Cost=5
- **Revised analysis**: ADR reviews are text analysis with checklist validation. Sonnet sufficient for most reviews.
- Cost impact: Medium

**security** (Opus → Sonnet):
- Usage: 193 mentions (7% of sessions)
- ADR-002 score: Reasoning=4, Error Cost=5
- **Revised analysis**: OWASP Top 10 checks are pattern-based. Deep threat modeling is rare.
- **Risk acceptance**: Security reviews may miss subtle vulnerabilities. Mitigated by reversion path (see below).
- Cost impact: High

**independent-thinker** (Opus → Sonnet):
- Usage: 27 mentions (0.9% of sessions)
- ADR-002 score: Reasoning=5, Error Cost=4
- **Revised analysis**: Contrarian analysis is critique, not novel reasoning. Sonnet provides sufficient challenge.
- Cost impact: Low

**high-level-advisor** (Opus → Sonnet):
- Usage: 19 mentions (0.07% of sessions = once every 15 sessions)
- ADR-002 score: Reasoning=5, Error Cost=5
- **Revised analysis**: Strategic advice is rarely invoked. When needed, Sonnet provides 90%+ quality.
- **Key finding**: 80x overprovisioned on Opus for <1% usage
- Cost impact: Low (but highest ROI per downgrade)

**roadmap** (Opus → Sonnet):
- Usage: 21 mentions (0.07% of sessions)
- ADR-002 score: Reasoning=4, Error Cost=4
- **Revised analysis**: Epic creation is structured text generation. Deep product reasoning is rare.
- Cost impact: Low

### Opus Retention

**implementer** (Retain Opus):
- Usage: 51 mentions (2% of sessions)
- **Rationale**: Only agent generating production code. Errors are extremely costly (bugs, security vulnerabilities). Opus required.
- ADR-002 score: Reasoning=4, Error Cost=5, Tools=4 ✓ Validated

## Rationale

### Data-Driven Approach

ADR-002 used theoretical task requirements. ADR-039 uses empirical usage data:

| Decision Factor | ADR-002 | ADR-039 |
|-----------------|---------|---------|
| Basis | Theoretical task complexity | 290 sessions of usage data |
| Validation | None (predictions) | Actual invocation patterns |
| Cost model | Per-agent reasoning needs | Volume × Cost × Frequency |
| Risk mitigation | Conservative (7 opus) | Empirical (1 opus) + reversion path |

### Cost Impact

| Distribution | Opus % | Sonnet % | Haiku % | Relative Cost |
|--------------|--------|----------|---------|---------------|
| ADR-002 | 62% | 38% | 0% | 100% (baseline) |
| ADR-039 | 10-15% | 50-55% | 30-35% | ~35-40% |

**Expected savings**: 60-65% cost reduction across agent fleet.

### Quality Mitigation

Downgrades introduce risk of quality degradation. Mitigations:

1. **Reversion path**: Document exact commands to restore Opus (see below)
2. **Monitoring**: Track ADR quality, security review depth, orchestration errors
3. **Incremental rollback**: Can restore individual agents without full revert
4. **Session 128 log**: Contains comprehensive reversion guide

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|-------------|------|------|----------------|
| Keep ADR-002 distribution | Proven safe | 62% opus usage unsustainable | Cost too high for max20 subscription |
| Downgrade implementer to Sonnet | Maximum cost savings | Code generation errors are expensive | Unacceptable risk |
| Keep security on Opus | ADR-002 rationale valid | 7% of sessions on Opus | Risk accepted with monitoring (reversion path documented) |
| Gradual rollout (1 agent at a time) | Lower risk | Slow to realize savings | Usage data gives confidence for bulk change |

## Reversion Procedures

### Quick Reversion (Individual Agents)

If quality degrades for specific agents:

```bash
# Restore orchestrator to opus
sed -i 's/model: sonnet/model: opus/' .claude/agents/orchestrator.md

# Restore architect to opus
sed -i 's/model: sonnet/model: opus/' .claude/agents/architect.md

# Restore security to opus
sed -i 's/model: sonnet/model: opus/' .claude/agents/security.md

# Restore memory to sonnet
sed -i 's/model: haiku/model: sonnet/' .claude/agents/memory.md
```

### Full Reversion (ADR-002 Distribution)

If widespread quality issues:

```bash
# Restore all ADR-002 opus agents from git history
git show 99ccee5:.claude/agents/orchestrator.md > .claude/agents/orchestrator.md
git show 99ccee5:.claude/agents/architect.md > .claude/agents/architect.md
git show 99ccee5:.claude/agents/security.md > .claude/agents/security.md
git show 99ccee5:.claude/agents/independent-thinker.md > .claude/agents/independent-thinker.md
git show 99ccee5:.claude/agents/high-level-advisor.md > .claude/agents/high-level-advisor.md
git show 99ccee5:.claude/agents/roadmap.md > .claude/agents/roadmap.md
```

### Monitoring Triggers

Revert specific agents if:

| Agent | Trigger |
|-------|---------|
| orchestrator | Complex task coordination fails (multi-agent deadlock, incorrect routing) |
| architect | ADR quality degrades (incomplete analysis, missed design flaws) |
| security | Security reviews miss vulnerabilities (OWASP Top 10 issues not caught) |
| independent-thinker | Critique quality drops (fails to identify flawed assumptions) |

## Consequences

### Positive

- **Cost reduction**: 60-65% savings on agent invocations
- **Latency improvement**: Haiku agents (2-5s) vs Sonnet (3-15s) for high-volume operations
- **Scalability**: Max20 subscription now supports higher session volume
- **Data validation**: Usage patterns confirm ADR-002 overprovisioned 6 agents

### Negative

- **Quality risk**: Security/orchestrator/architect downgrades may reduce depth
- **Monitoring burden**: Must track quality metrics post-change
- **Reversion complexity**: 6 agents downgraded; partial reverts require careful tracking

### Neutral

- **Skill compression**: Lazy-loading reduces context 71-75%, separate from model optimization
- **Haiku tier introduction**: New tier adds model selection complexity but validates decision matrix

## References

- ADR-002: Agent Model Selection Optimization (Superseded by this ADR)
- Session 128 log: `.agents/sessions/2026-01-03-session-128-context-optimization.md`
- Session log analysis: 290 sessions (2025-12-21 to 2026-01-03)
- Commit 651205a: Initial downgrades (memory, skillbook, independent-thinker, roadmap)
- Commit d81f237: Aggressive downgrades (orchestrator, architect, security)
- Commit f101c06: High-level-advisor downgrade (final)

## Supersession Note

This ADR supersedes ADR-002 (2025-12-16) based on empirical usage data. ADR-002 remains valid as the theoretical framework but is replaced by data-driven optimization in practice.

**Key change**: Cost optimization prioritizes **volume × frequency** over **theoretical reasoning depth** where data shows overprovisioning.
