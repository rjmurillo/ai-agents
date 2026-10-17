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

## Planner Application

The planner's two-phase workflow (planning, then execution) maps to OODA. Use this mapping to avoid common planning anti-patterns.

### Planning Phase as OODA

| Planner Step | OODA Stage | Activity |
|--------------|------------|----------|
| Confirm preconditions | Observe | Gather problem statement, constraints, existing code |
| Steps 1-N: iterative planning | Orient | Analyze dependencies, risks, decompose milestones |
| Write plan to file | Decide | Commit to milestone order, scope, and approach |
| Review phase (TW + QR) | Act + Observe | Execute review, observe findings, iterate if needed |

### Execution Phase as OODA

| Executor Step | OODA Stage | Activity |
|---------------|------------|----------|
| Step 1: Execution Planning | Observe | Read plan, detect prior work, assess current state |
| Step 2: Reconciliation | Orient | Validate existing code against plan assumptions |
| Step 3: Milestone Execution | Act | Delegate to agents, implement, test |
| Step 4: Post-Implementation QR | Observe (new loop) | Audit quality, identify gaps |
| Steps 5-7: Resolution + Docs | Decide + Act | Fix issues, document, retrospect |

### Anti-Patterns

| Anti-Pattern | Problem | Fix |
|--------------|---------|-----|
| Analysis paralysis | Stuck in Orient during planning | Time-box planning steps, accept imperfect info |
| Skipping review phase | No Orient after planning Act | Always run TW + QR before execution |
| No re-observation | Plan becomes stale during execution | Reconciliation step forces re-observation |
| One-pass execution | No iteration on quality | Post-implementation QR loops back through issues |
