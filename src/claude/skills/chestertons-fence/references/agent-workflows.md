# Chesterton's Fence: agent workflows

## Integration with agent workflows

| Agent | How to Integrate |
|-------|------------------|
| **Analyst** | Run this skill first when investigating changes. The report is a prerequisite for any change proposal. |
| **Architect** | ADRs that deprecate or replace existing patterns MUST include a "Prior Art Investigation" section. Use this skill to generate it. |
| **Implementer** | Before implementing deletions or major refactoring, verify an investigation report exists. If missing, route to analyst. |
| **Critic** | When validating plans that remove or replace existing systems, check for investigation evidence. Auto-reject proposals without historical context. |

## Anti-patterns

| Avoid | Why | Instead |
|-------|-----|---------|
| Removing code you do not understand | May break hidden invariants | Investigate first, then decide |
| Assuming dead code is unused | Hyrum's Law: someone depends on it | Run dependency analysis |
| Skipping PR/ADR search | Loses original design rationale | Always check git history and PRs |
| Proposing replacement without evidence | Cannot compare tradeoffs | Document original constraints first |
