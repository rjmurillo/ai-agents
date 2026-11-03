---
source: wiki/concepts/AI Productivity/Agent Architecture Patterns.md
created: 2026-04-11
review-by: 2026-07-11
---

# Agent Architecture Patterns (Planning Context)

Patterns for decomposing agent systems into reliable, maintainable units during planning.

## Skill Budget Rule

Limit each agent to 7-10 skills tied to explicit goals. Reliability decreases as skills increase. Each skill must map to a measurable goal. Clear goals make evaluation binary: pass or fail.

## 3-File Planning Pattern

```
task_plan.md   -> phases with checkboxes
findings.md    -> research (not context stuffing)
progress.md    -> session log and test results
```

Agent reads the plan before every decision. This is attention manipulation, not context reduction. Re-reading keeps goals in the attention window as context grows (needle-in-haystack mitigation).

### For Large Knowledge Bases

```
index.md          -> master list (lightweight, always loaded)
modules/*.md      -> one file per module (loaded when relevant)
active_context.md -> items relevant right now
archive/          -> deprecated items
```

Load what is relevant now. Refresh before every major decision.

## Milestone Decomposition Checklist

When planning agent-based features, validate each milestone against:

1. Does each agent have a single, measurable goal?
2. Are skills limited to 7-10 per agent?
3. Is there a plan re-read mechanism for long-running tasks?
4. Are escalation paths defined (stop, ask human, express uncertainty)?
5. Are constraints testable, not vague?

## Scheduled Autonomous Work

Plan autonomous agent tasks for low-risk, reviewable work only.

| Good candidates | Bad candidates |
|-----------------|----------------|
| Run tests, fix failures | Major features from scratch |
| Update docs, changelogs | High-risk, large blast radius code |
| Remove dead code | Anything not quickly reviewable |
| Auto-create PR from issue | Complex architectural changes |

## Revenue-Closed-Loop Pattern

Four principles for self-improving agent designs:

1. Close loop on outcomes (revenue, conversions), not outputs (task complete)
2. Let agent update its own skill file from performance data
3. Separate automation from human judgment (know which 5% needs a human)
4. Use agent as business advisor, not just task runner
