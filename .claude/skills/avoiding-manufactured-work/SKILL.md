---
name: avoiding-manufactured-work
version: 1.0.0
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

## Task Completion Contract

`.claude/rules/builder-ethos.md` section 4 owns the terminal predicate and references this section for the contract, precedence, disposition mapping, and reactivation detail. Use it to decide whether a task is still active.

### Forming the contract

Before non-trivial execution, derive the smallest observable task contract from, in order:

1. the explicit current user goal;
2. explicit requested deliverables;
3. explicit constraints and acceptance criteria;
4. mandatory system/harness, safety, and repository policy;
5. the minimum inferred success criteria required to make an otherwise bounded request observable.

Routine low-risk work does not require user confirmation of obvious inferred criteria. Record or carry the contract before broad execution. Once execution starts, criteria stay fixed unless the user changes them or a mandatory policy was previously omitted. A bounded contract forms even when the user omits explicit acceptance criteria: infer the minimum observable success and proceed.

### Precedence

```text
system / host requirements
    > mandatory safety and repository policy
    > explicit current user request
    > frozen task contract
    > optional improvements and preferences
```

<!-- Deviates from issue #5404's literal precedence text: mandatory policy must outrank a raw user request per security review (PR #5433 threads). -->

"Boil the lake" applies inside the frozen task contract and its direct correctness blast radius. Work is not included merely because it fits in one session.

### Finding disposition

Every post-satisfaction finding maps to exactly one class. Reuse the keep/shrink/defer/delete decision above; do not create a second doctrine.

| Class | Meaning | Keeps task active? | Disposition |
|---|---|---|---|
| Blocker | Concrete evidence falsifies a frozen criterion or mandatory policy | Yes, exact affected scope | keep |
| Requested improvement | Explicit part of the task contract | Yes | keep |
| Optional enhancement | Useful, but no current criterion or consumer requires it | No | defer or delete |
| Side quest | Outside the requested objective | No | delete |

### Terminal predicate

When every requested deliverable satisfies the frozen task contract and no blocker remains, the task is terminal. Stop autonomous work. Retry limits, review rounds, TODO exhaustion, delegation budgets, and circuit breakers are backstops, not proof of completion, and cannot keep a verified-terminal task active merely because budget remains.

### Reactivation

A terminal task reopens only when:

1. concrete evidence falsifies a named frozen criterion;
2. a mandatory safety/repository policy adds a blocker; or
3. the user explicitly reopens the named task or files a new request.

Reviewer preference, optional hardening, a new agent/context, remaining budget, or a generic desire for improvement cannot reactivate it. A child task becoming terminal does not terminate an active parent task. A new user request is new work unless it explicitly reopens the prior task. This predicate is independent of the pipeline `WorkflowStatus` value; do not repurpose that enum to represent it.

### Handoff boundary

A consumer that receives task identity and verified completion evidence must not reopen the task without an authorized reactivation event. Durable transport and restoration across compaction, process restart, and handoff are owned by issue #5417, not this skill.
