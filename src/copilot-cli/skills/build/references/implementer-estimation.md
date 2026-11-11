# Complexity Estimation Detail

Loaded by the `implementer` agent when it estimates complexity or reports an estimate. The agent body keeps the size table, the XL blocker, and the range rule.

Before starting non-trivial work, estimate complexity:

| Size | Hours | Signals |
|------|-------|---------|
| XS | 1-2 | Config change, single file |
| S | 2-4 | Known pattern, isolated change |
| M | 4-8 | Multiple files, some unknowns |
| L | 8-16 | New integration, cross-cutting |
| XL | 16+ | Should be split before starting |

Flag XL as a blocker. Request decomposition before proceeding.

## Before Estimating

1. **Write down the overall approach** first
2. **Explore the code**, read documentation, read memories. Use the `context-gather` skill
3. **Break down the task** into steps, update TODO list so you don't lose track
4. **Find similar tasks** in same domain or involving similar technologies

## Estimation Principles

| Principle | Application |
|-----------|-------------|
| Give ranges, not points | "2-4 days" not "3 days" |
| Scale reflects accuracy | Hours implies precision; days acknowledges uncertainty |
| Find analogous work | Search memories for similar past tasks |
| Uncertainty needs margin | New domain: 100-400% factor |
| Underestimating hurts more | Overestimating is safer than underestimating |

## Uncertainty Factors

| Situation | Factor | Example Range |
|-----------|--------|---------------|
| Done similar task before | 1.0-1.25x | 2-2.5 days |
| Similar domain, new tech | 1.5-2x | 3-4 days |
| New domain, familiar tech | 2-3x | 4-6 days |
| Completely new territory | 3-4x | 6-8 days |

## Estimation Checklist

```markdown
- [ ] Explored code and read relevant memories
- [ ] Broke task into small items (each estimable)
- [ ] Searched for similar past tasks
- [ ] Gave range estimate, not point estimate
- [ ] Applied uncertainty factor based on novelty
- [ ] Asked "can it take less?" - if no, estimate is optimistic
- [ ] Communicated estimate to orchestrator
- [ ] Scheduled re-estimation checkpoint mid-task
```

## Communicating Estimates

**To orchestrator**:

```markdown
## Estimate: [Task Name]

**Range**: [Low] - [High] [unit]
**Confidence**: [Low/Medium/High]
**Basis**: [Similar to X / New domain / etc.]
**Uncertainty Factor**: [1.5x / 2x / etc.]

**Assumptions**:
- [Assumption that affects estimate]

**Will revisit**: [When you'll re-estimate]
```

**Key**: Inaccuracies go both ways. Revisit and refine as you learn more. The effects of underestimating are usually more detrimental than overestimating.
