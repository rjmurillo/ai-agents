# ADR-002: Agent Model Selection Optimization

## Status

Accepted

## Date

2025-12-16

## Context

All 18 agents in the ai-agents repository were configured to use Claude Opus (16 agents) or Claude Sonnet (2 agents) without systematic evaluation of actual task requirements. This created several issues:

1. **Cost inefficiency**: Opus costs ~5x more than Sonnet per token
2. **Latency overhead**: Opus has higher latency (10-60s typical) vs Sonnet (3-15s)
3. **Over-provisioning**: Many agents perform structured, well-defined tasks that don't require Opus-level reasoning

### Current Distribution (Before Change)

| Model | Agent Count | Agents |
|-------|-------------|--------|
| Opus | 16 | analyst, architect, critic, devops, explainer, high-level-advisor, implementer, independent-thinker, orchestrator, planner, pr-comment-responder, qa, retrospective, roadmap, security, task-generator |
| Sonnet | 2 | memory, skillbook |

### New Distribution (After Change)

| Model | Agent Count | Agents |
|-------|-------------|--------|
| Opus | 7 | architect, high-level-advisor, implementer, independent-thinker, orchestrator, roadmap, security |
| Sonnet | 11 | analyst, critic, devops, explainer, memory, planner, pr-comment-responder, qa, retrospective, skillbook, task-generator |

## Decision

Apply a structured evaluation framework to optimize model selection for each agent based on:

1. **Reasoning Depth** (1-5): Multi-step logic, nuance, ambiguity handling
2. **Latency Sensitivity** (1-5): Response time requirements
3. **Error Cost** (1-5): Impact of incorrect answers
4. **Volume** (1-5): Expected request frequency
5. **Tool Complexity** (1-5): Number and complexity of tool orchestration

### Decision Matrix Applied

| Score Profile | Recommended Model |
|--------------|-------------------|
| Reasoning ≥4, Error Cost ≥4 | Opus |
| Reasoning 3-4, balanced needs | Sonnet |
| Latency ≥4 OR Volume ≥4, Reasoning ≤3 | Haiku |
| Tool Complexity ≥4, Reasoning ≥3 | Sonnet or Opus |

### Model Assignment Changes

**Downgrade from Opus to Sonnet (9 agents):**

| Agent | Reasoning | Latency | Error Cost | Volume | Tools | Rationale |
|-------|-----------|---------|------------|--------|-------|-----------|
| analyst | 4 | 2 | 4 | 2 | 3 | Research is thorough but structured; Sonnet handles multi-step analysis |
| critic | 4 | 2 | 4 | 2 | 2 | Plan validation is checklist-based review |
| devops | 3 | 2 | 4 | 2 | 3 | Pipeline configs are structured, well-defined tasks |
| explainer | 3 | 2 | 3 | 2 | 2 | Documentation creation is structured writing |
| planner | 4 | 2 | 4 | 2 | 3 | Milestone breakdown is structured decomposition |
| pr-comment-responder | 3 | 2 | 3 | 2 | 3 | Triage and tracking don't require deepest reasoning |
| qa | 3 | 2 | 4 | 2 | 3 | Test design is structured and pattern-based |
| retrospective | 4 | 1 | 3 | 1 | 3 | Learning extraction benefits from Sonnet speed |
| task-generator | 3 | 2 | 3 | 2 | 2 | Atomic decomposition is pattern-based |

**Retain Opus (7 agents):**

| Agent | Reasoning | Latency | Error Cost | Volume | Tools | Rationale |
|-------|-----------|---------|------------|--------|-------|-----------|
| architect | 5 | 1 | 5 | 1 | 3 | System-wide decisions, breaking changes are critical |
| high-level-advisor | 5 | 1 | 5 | 1 | 2 | Strategic impasses need highest reasoning |
| implementer | 4 | 2 | 5 | 2 | 4 | Code execution errors are expensive |
| independent-thinker | 5 | 1 | 4 | 1 | 2 | Contrarian analysis requires deepest reasoning |
| orchestrator | 5 | 2 | 5 | 2 | 5 | Complex multi-agent coordination and routing |
| roadmap | 4 | 1 | 4 | 1 | 2 | Product direction errors cascade widely |
| security | 4 | 2 | 5 | 2 | 3 | Security bugs are extremely costly |

**Already Optimal (2 agents):**

| Agent | Model | Rationale |
|-------|-------|-----------|
| memory | Sonnet | Context retrieval/storage is simple operations |
| skillbook | Sonnet | Pattern matching and deduplication is straightforward |

## Rationale

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|-------------|------|------|----------------|
| Keep all on Opus | Maximum reasoning capability | 5x cost, unnecessary latency | Over-provisioned for structured tasks |
| Move all to Sonnet | Lowest cost, fastest | Risk errors on strategic decisions | Under-provisioned for critical agents |
| Add Haiku tier | Fastest for simple routing | Additional model complexity | Current tasks don't have high volume/latency needs |

### Trade-offs

- **Quality vs Cost**: Sonnet provides 95%+ quality on structured tasks at 80% cost reduction
- **Latency vs Reasoning**: Faster responses for routine work; slower deep analysis when needed
- **Complexity vs Optimization**: More nuanced model selection requires ongoing evaluation

## Consequences

### Positive

- **~40-50% cost reduction** on agent invocations
- **Faster response times** for 9 frequently-used agents
- **Quality maintained** for high-stakes decisions (architect, security, orchestrator)
- **ROI**: Cost savings enable more agent invocations per workflow
- **Framework established** for future agent model evaluation

### Negative

- **Potential edge cases**: Some complex analyst/planner tasks may benefit from Opus
- **Evaluation overhead**: New agents require scoring before deployment
- **Model drift risk**: As Sonnet/Opus capabilities evolve, assignments may need review

### Neutral

- No change to agent responsibilities or interfaces
- Memory and skillbook already optimal

## Implementation Notes

1. Update frontmatter `model:` field in 9 agent files
2. Run agent generation scripts to propagate changes
3. Monitor agent performance for quality regressions
4. Re-evaluate quarterly or when Claude models update

### Files Changed

```text
src/claude/analyst.md         (opus → sonnet)
src/claude/critic.md          (opus → sonnet)
src/claude/devops.md          (opus → sonnet)
src/claude/explainer.md       (opus → sonnet)
src/claude/planner.md         (opus → sonnet)
src/claude/pr-comment-responder.md (opus → sonnet)
src/claude/qa.md              (opus → sonnet)
src/claude/retrospective.md   (opus → sonnet)
src/claude/task-generator.md  (opus → sonnet)
```

## Related Decisions

- [ADR-001: Markdown Linting Configuration](ADR-001-markdown-linting.md)

## References

- [Claude Model Capabilities](https://docs.anthropic.com/en/docs/about-claude/models)
- Claude Opus 4.5: `claude-opus-4-5-20251101` - Highest reasoning, highest cost
- Claude Sonnet 4.5: `claude-sonnet-4-5-20250929` - Balanced reasoning and speed
- Claude Haiku 4.5: `claude-haiku-4-5-20251001` - Fastest, lowest cost

---

## Agent-Specific Fields

### Agent Names

Multiple agents affected (see Implementation Notes)

### Overlap Analysis

N/A - This ADR changes model selection, not agent responsibilities

### Entry Criteria

| Scenario | Priority | Confidence |
|----------|----------|------------|
| New agent creation | P0 | High |
| Quarterly model review | P1 | Medium |
| Claude model version update | P1 | Medium |
| Quality regression detected | P0 | High |
