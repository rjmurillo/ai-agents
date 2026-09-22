<!-- placement: evidence; reason: the Sessions 40-41 shared-branch incident and its detection delay, kept as the observation behind worktree isolation -->

# Coordination: Sessions 40-41 Shared-Branch Incident

Authoritative owner: `.claude/agents/orchestrator.md` requires each agent in a
concurrent wave to get its own worktree. `.claude/rules/universal.md` and the
worktree path rules carry the placement constraint.

## Observation (2025-12-20, Sessions 40-41)

Several agents committed to the same branch because no check ran before the
wave started. Detection took 30 minutes, and recovery needed a hybrid of manual
and scripted repair.

The three signals that would have caught it earlier, in the order they became
available:

1. Each agent's own `git branch --show-current` output, before any work.
2. An explicit branch assignment per agent, recorded where the coordinator
   could read it back.
3. Active commit hooks on each worktree.

## Transferable reading

The failure was not that agents ignored an instruction. It was that the
coordinator had no readable record of which branch each agent was on, so the
collision was invisible until the commits landed. Give each agent its own
worktree and the class of failure disappears rather than being detected faster.

## Related

- [git/git-never-place-worktrees-inside-the-checkout](../git/git-never-place-worktrees-inside-the-checkout.md)
- [git/git-worktree-parallel](../git/git-worktree-parallel.md)
- [orchestration-parallel-execution](orchestration-parallel-execution.md)
