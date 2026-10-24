# Evidence: stalled agents and linked worktree recovery

<!-- placement: evidence; reason: records operational incidents and recovery outcomes, not an operating contract -->

Source: P1-batch fix session, 2026-08-27, plus later worktree incidents.

## Observed evidence

- A stalled agent showed no transcript activity after a blocked destructive
  command. A message nudge did not resume it. Stopping the agent and taking
  over its external worktree completed the repair.
- A bare local branch name overlaid stale content in a linked worktree. The
  status output exposed the pollution before it was committed.
- A push rejected by GH007 exposed a shared git identity problem. Worktree
  scoped configuration avoided changing sibling worktrees.
- A message sent to a workflow agent that was still running started a second
  copy of that agent. The send result said "Resuming agent". Both copies then
  wrote to the same worktree. On #6667 one copy reverted the other's commit and
  the unhardened version merged as PR #6908. On #6624 a second copy rewrote the
  parser mid-run. (2026-10-24)
- In both incidents the message went to the agent before its workflow had
  finished. Waiting for the workflow result, or giving the follow-up to a fresh
  agent in a new worktree, would have left one writer per worktree.

## Migration disposition

The host Universal Rules own linked worktree memory safety, evidence-preserving
recovery, and no-fabrication reporting. Git and worktree skills own command
procedures. This memory retains the incidents and outcomes as evidence.
