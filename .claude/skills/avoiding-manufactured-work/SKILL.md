---
name: avoiding-manufactured-work
version: 1.0.0
model: claude-sonnet-4-6
description: Detect and stop manufactured work after a deliverable appears done. Use when a worker has produced a plan, issue, PR, backlog item, research artifact, or follow-up task and you need to verify it was demanded by a real user, acceptance criterion, or blocked decision instead of reward-seeking activity.
license: MIT
---

# Avoiding Manufactured Work

Detect follow-up work that exists because the agent wanted to keep helping, not because a real consumer asked for it.

## Sibling skill

Pair this with the `front-gate-before-pipeline` pattern. Front-gate fires before work begins; this skill fires after work appears done. Same root cause (skipping self-evaluation under reward bias), opposite timing.

## Workflow

1. Name the concrete work product under review.
2. Identify the consumer: user, issue, acceptance criterion, failing check, reviewer thread, or blocked downstream decision.
3. If no consumer exists, stop. Do not create a task, issue, PR, memo, or research artifact.
4. If a consumer exists, verify the proposed follow-up is the smallest action that unblocks that consumer.
5. Report the disposition as one of: keep, shrink, defer, or delete.

## Decision Rules

- Keep work that directly satisfies an acceptance criterion, fixes a failing required check, resolves a reviewer thread, or unblocks a named decision.
- Shrink work when the demand is real but the proposed scope exceeds what the consumer needs.
- Defer work when the demand is plausible but no current consumer is blocked.
- Delete work when it is speculative, reputational, performative, or created to make the agent appear thorough.

## Output

Return:

```text
Disposition: keep | shrink | defer | delete
Consumer: <named consumer or none>
Reason: <one sentence>
Next action: <smallest action, or none>
```
