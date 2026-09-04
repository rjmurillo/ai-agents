---
name: avoiding-manufactured-work
version: 1.1.0
description: Detect and stop manufactured work after a deliverable appears done, and classify a post-completion finding into the four contract classes builder-ethos.md delegates here. Use when a worker has produced a plan, issue, PR, backlog item, research artifact, or follow-up task and you need to verify it was demanded by a real user, acceptance criterion, or blocked decision instead of reward-seeking activity.
license: MIT
---

# Avoiding Manufactured Work

Detect follow-up work that exists because the agent wanted to keep helping, not because a real consumer asked for it.

## Sibling skill

Pair this with the `front-gate-before-pipeline` pattern. Front-gate fires before work begins; this skill fires after work appears done. Same root cause (skipping self-evaluation under reward bias), opposite timing.

## Triggers

`is this work manufactured`, `does this follow-up have a consumer`, `classify this post-completion finding`, `should I file this follow-up`

## Process

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

## Disposition Procedure for Post-Completion Findings

`.claude/rules/builder-ethos.md` section `## 4. Task Completion Contract` owns the completion contract: forming it, precedence, the terminal predicate, and reactivation. Read that section for any of those. Its `### Finding disposition` subsection delegates exactly one step to this skill, verbatim:

> Every post-satisfaction finding is one of four classes; classify it with the `avoiding-manufactured-work` skill's disposition procedure, not a second doctrine.

This section is that procedure. It maps each class onto the keep/shrink/defer/delete dispositions above so a finding raised after the task is terminal gets one named outcome instead of a judgment call. Read the class definitions in `### Finding disposition`; this table adds only the outcome, so there is no second copy of the definitions to drift.

| Class | Disposition |
|---|---|
| Blocker | keep, scoped to the falsified criterion |
| Requested improvement | keep, or shrink to the smallest action that satisfies it |
| Optional enhancement | defer |
| Side quest | delete |

Test the Blocker class first. A finding that falsifies mandatory safety or repository policy is a Blocker whether or not it sits inside the requested objective, so it never reaches the Side quest row and never maps to delete. Classify in table order: Blocker, then Requested improvement, then Optional enhancement, then Side quest.

A defer or a delete is a disposition, not a silent drop. Name the finding and its class in the report, then stop. Naming it is not a reason to reopen the task; only `### Reactivation` in `.claude/rules/builder-ethos.md` can do that.

## Checklist

- [ ] The work product is named concretely, not as a category.
- [ ] A consumer is named, or the disposition is delete.
- [ ] The proposed action is the smallest one that unblocks that consumer.
- [ ] Any post-completion finding was tested against Blocker first.
- [ ] Every finding reached a stated disposition; none was dropped silently.
