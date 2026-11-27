---
name: avoiding-manufactured-work
version: 1.2.0
description: "Stop manufactured work after a deliverable looks done and classify post-completion findings into the four contract classes builder-ethos.md delegates here. Use when a worker produced a plan, issue, PR, backlog item, or follow-up task and you must verify a real user, criterion, or blocked decision demanded it."
license: Apache-2.0
---

# Avoiding Manufactured Work

Detect follow-up work that exists because the agent wanted to keep helping, not because a real consumer asked for it.

A defect found on the path is not manufactured work. builder-ethos.md section 4 (Own found defects) makes it part of the task: fix it in the same work with its tests, callers, docs, and generated mirrors. This skill stops speculative work, never a fix.

## Sibling skill

Pair this with the `front-gate-before-pipeline` pattern. Front-gate fires before work begins; this skill fires after work appears done. Same root cause (skipping self-evaluation under reward bias), opposite timing.

## Triggers

`is this work manufactured`, `does this follow-up have a consumer`, `classify this post-completion finding`, `should I file this follow-up`

## Process

1. Name the concrete work product under review.
2. Identify the consumer: user, issue, acceptance criterion, failing check, reviewer thread, blocked downstream decision, or an evidenced defect on the path.
3. If no consumer exists, stop. Do not create a task, issue, PR, memo, or research artifact.
4. If a consumer exists, verify the proposed follow-up is the smallest action that unblocks that consumer.
5. Report the disposition as one of: keep, shrink, defer, or delete.

## Decision Rules

- Keep work that directly satisfies an acceptance criterion, fixes a failing required check, resolves a reviewer thread, unblocks a named decision, or fixes a defect on the path.
- Shrink work when the demand is real but the proposed scope exceeds what the consumer needs.
- Defer work when the demand is plausible but no current consumer is blocked. A found defect is never deferred: it is a Blocker.
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

The builder-ethos rule, section `## 4. Task Completion Contract`, owns the completion contract (directory prefix omitted on purpose: this skill ships in the plugin mirrors, where a `.claude/rules/` path dangles; look the rule up by name in whichever instruction tree you are reading, `builder-ethos.md` under `.claude/rules/` or `builder-ethos.instructions.md` under the instructions trees): precedence and the terminal predicate. Read that section for those two. Forming the contract and reactivation moved here; see `## Forming The Contract` and `## Reactivation` below. Its `### Finding disposition` subsection delegates exactly one step to this skill, verbatim:

> Every post-satisfaction finding is one of four classes; classify it with the `avoiding-manufactured-work` skill's disposition procedure, not a second doctrine.

This section is that procedure. It maps each class onto the keep/shrink/defer/delete dispositions above so a finding raised after the task is terminal gets one named outcome instead of a judgment call. Read the class definitions in `### Finding disposition`; this table adds only the outcome, so there is no second copy of the definitions to drift.

| Class | Disposition |
|---|---|
| Blocker | keep, scoped to the falsified criterion or the found defect, fixed completely |
| Requested improvement | keep, or shrink to the smallest action that satisfies it |
| Optional enhancement | defer |
| Side quest | delete |

Test the Blocker class first. A finding that falsifies mandatory safety or repository policy, or an evidenced defect on the path, is a Blocker whether or not it sits inside the requested objective, so it never reaches the Side quest row and never maps to defer or delete. Only a taste change, a speculative feature, or an off-path finding with no defect reaches Optional enhancement or Side quest. Classify in table order: Blocker, then Requested improvement, then Optional enhancement, then Side quest.

A defer or a delete is a disposition, not a silent drop. Name the finding and its class in the report, then stop. Naming it is not a reason to reopen the task; only the Reactivation section below can do that.

## Forming The Contract

Before non-trivial execution, derive the smallest task contract, in order: current user goal and deliverables; explicit constraints and acceptance criteria; mandatory system/safety/repository policy; minimum inferred success criteria a bounded request needs to be observable. Routine, low-risk work skips user confirmation of obvious inferred criteria. Record the contract before broad execution (TODO list, stated plan, or per-issue handoff); once started, criteria stay fixed unless the user changes them or a mandatory policy was omitted.

## Reactivation

A terminal task reopens only when evidence falsifies a named frozen criterion, a mandatory policy adds a blocker, a defect turns up on the path, or the user reopens it or makes a new request. Reviewer preference, optional hardening, a new context, or remaining budget cannot reactivate it. A child task's completion does not terminate its parent; a new request is new work unless it explicitly reopens the prior one. A consumer holding task identity and completion evidence must not reopen it without one of these events.

## Checklist

- [ ] The work product is named concretely, not as a category.
- [ ] A consumer is named, or the disposition is delete.
- [ ] The proposed action is the smallest one that unblocks that consumer.
- [ ] Any post-completion finding was tested against Blocker first, found defects included.
- [ ] No found defect was deferred, filed for later, or left as a PR-body note when the agent could fix it.
- [ ] Every finding reached a stated disposition; none was dropped silently.
