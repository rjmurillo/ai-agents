---
source: wiki/concepts/Strategic Thinking/OODA Loop.md
created: 2026-04-11
review-by: 2026-07-11
---

# OODA Loop

Decision-making framework for operating in uncertain, rapidly changing environments.

**O**bserve, **O**rient, **D**ecide, **A**ct

## Stages

| Stage | Action | Key Questions |
|-------|--------|---------------|
| Observe | Gather information | What's happening? What data do we have? |
| Orient | Analyze and synthesize | What does it mean? How does it fit context? |
| Decide | Choose a course of action | What should we do? What are trade-offs? |
| Act | Execute the decision | Implement quickly, then observe again |

## Key Insight

The loop is continuous and iterative. Faster OODA loops create competitive advantage. The goal is not perfect information but faster iteration.

## Application to Codebase Analysis

The analyze skill's phases map directly to OODA:

| Analyze Phase | OODA Stage | Activity |
|---------------|------------|----------|
| Exploration (Step 1) | Observe | Gather codebase structure, dependencies, patterns |
| Focus Selection (Step 2) | Orient | Classify findings by dimension, assign priorities |
| Investigation Planning (Step 3) | Decide | Commit to specific files, questions, hypotheses |
| Deep Analysis (Steps 4 to N-2) | Act | Execute the plan, collect evidence |
| Verification (Step N-1) | Observe (new loop) | Audit completeness, identify gaps |
| Synthesis (Step N) | Orient + Decide | Consolidate findings, recommend actions |

## Application to Incident Response

1. **Observe**: Check metrics, logs, alerts
2. **Orient**: Identify affected services, correlate symptoms
3. **Decide**: Choose fix (rollback, hotfix, config change)
4. **Act**: Execute the fix, then observe again

## Application to Modernization

1. **Observe**: Assess service state, dependencies, tech debt
2. **Orient**: Map constraints (team capacity, risk tolerance, deadlines)
3. **Decide**: Choose migration approach (strangler fig, rewrite, refactor)
4. **Act**: Implement in smallest safe increment

## Anti-Patterns

| Anti-Pattern | Problem | Fix |
|--------------|---------|-----|
| Analysis paralysis | Stuck in Orient | Time-box, accept imperfect info |
| Shooting from the hip | Skip Orient | Force explicit analysis step |
| One-and-done | No iteration | Schedule re-observation |
