---
name: avoiding-manufactured-work
version: 1.1.0
description: Detect and stop manufactured work after a deliverable appears done, classify post-completion findings into the four builder-ethos classes, and bound drive-by fixes found mid-task. Use when a worker produced a plan, issue, PR, backlog item, research artifact, or follow-up task and you must verify that a real user, acceptance criterion, or blocked decision demanded it.
license: Apache-2.0
---

# Avoiding Manufactured Work

Detect follow-up work that exists because the agent wanted to keep helping, not because a real consumer asked for it.

## Sibling skill

Pair this with the `front-gate-before-pipeline` pattern. Front-gate fires before work begins; this skill fires after work appears done. Same root cause (skipping self-evaluation under reward bias), opposite timing.

## Triggers

`is this work manufactured`, `does this follow-up have a consumer`, `classify this post-completion finding`, `should I file this follow-up`, `should I fix this while I am here`

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

The builder-ethos rule, section `## 4. Task Completion Contract`, owns the completion contract (directory prefix omitted on purpose: this skill ships in the plugin mirrors, where a `.claude/rules/` path dangles; look the rule up by name in whichever instruction tree you are reading, `builder-ethos.md` under `.claude/rules/` or `builder-ethos.instructions.md` under the instructions trees): precedence and the terminal predicate. Read that section for those two. Forming the contract and reactivation moved here; see `## Forming The Contract` and `## Reactivation` below. Its `### Finding disposition` subsection delegates exactly one step to this skill, verbatim:

> Every post-satisfaction finding is one of four classes; classify it with the `avoiding-manufactured-work` skill's disposition procedure, not a second doctrine.

This section is that procedure. It maps each class onto the keep/shrink/defer/delete dispositions above so a finding raised after the task is terminal gets one named outcome instead of a judgment call. Read the class definitions in `### Finding disposition`; this table adds only the outcome, so there is no second copy of the definitions to drift.

| Class | Disposition |
|---|---|
| Blocker | keep, scoped to the falsified criterion |
| Requested improvement | keep, or shrink to the smallest action that satisfies it |
| Optional enhancement | defer |
| Side quest | delete |

Test the Blocker class first. A finding that falsifies mandatory safety or repository policy is a Blocker whether or not it sits inside the requested objective, so it never reaches the Side quest row and never maps to delete. Classify in table order: Blocker, then Requested improvement, then Optional enhancement, then Side quest.

A defer or a delete is a disposition, not a silent drop. Name the finding and its class in the report, then stop. Naming it is not a reason to reopen the task; only the Reactivation section below can do that.

A confirmed defect found nearby is class 3 under Drive-By Fixes below, not a Side quest to delete.

## Drive-By Fixes

Use this when you find something to change that the request did not name. Work the user asked for is the task, not a drive-by: plan it directly and leave these classes out of it. This is the canonical statement; the builder-ethos and voice rules point here. The default answer is no. An exception needs the evidence below. A preference is not evidence.

| Class | What it covers | Where it goes |
|---|---|---|
| 1. Tidy | Tiny, behavior-preserving cleanup in code the change already touches, when it makes the requested diff easier to read: a typo, a missing type hint, a dead local, a clearer local name in the function you edit. Renaming things elsewhere in the file does not qualify. | Same PR, its own commit, named in the PR body. |
| 2. Needed | Anything the requested change needs to be correct: callers, tests, docs, generated output. | Same PR. This is the change itself, not a drive-by. |
| 3. Defect | A confirmed defect with a named impact and its own proof (a reproduction or failing test), when it changes behavior, needs a different reviewer or code owner, or must be revertable alone. | Separate branch and PR with its own proof, only with authority for that extra PR (see below). Otherwise name it, its impact, and its proof in the PR body. |
| 4. Taste | Style or naming preference, whole-file formatting, cross-module renames, refactors with no named consumer. | Do not do it. No issue, no branch, no follow-up PR. |

Classify in this order: class 2, then 3, then 1, then 4. If the requested change needs it to be correct, it is class 2 and stays in the PR, even when it is also a defect.

Stop conditions:

- Class 1 is a few lines. About 20 to 30 changed lines of class 1 cleanup across the whole PR diff is a signal to stop and reassess, not an allowance.
- A drive-by fix never spawns another. Do not fix what the first fix revealed. If it is a confirmed defect, it is class 3; otherwise drop it.
- Once the requested change is proven, stop. Do not sweep for more work, and do not offer follow-ups.

For tidy fixes, name the readability gain and check that behavior stays the same. For defects and needed fixes, name what breaks and how you will prove the fix.

Authority for class 3: a second PR is state the user did not name (builder-ethos section 6). It needs a user order or workflow contract that covers opening PRs for defects found along the way; an order to ship the requested change alone does not. One class 3 PR per task. A second confirmed defect is named in the PR body, not opened. In a question, review, or diagnosis, or once the task is terminal, name the defect, its impact, and its proof in the report instead (builder-ethos section 6). Filing an issue still follows the builder-ethos section 4 flag rule.

Practice behind the classes:

- Google Engineering Practices, [Small CLs](https://google.github.io/eng-practices/review/developer/small-cls.html), section "Separate Out Refactorings": refactorings go in a separate CL from feature changes or bug fixes, but "Small cleanups such as fixing a local variable name can be included inside of a feature change or bug fix CL."
- Martin Fowler, [Opportunistic Refactoring](https://martinfowler.com/bliki/OpportunisticRefactoring.html): the camp site rule, "always leave the code behind in a better state than you found it." Classes 1 and 4 bound how far that reaches.

## Forming The Contract

Before non-trivial execution, derive the smallest task contract, in order: current user goal and deliverables; explicit constraints and acceptance criteria; mandatory system/safety/repository policy; minimum inferred success criteria a bounded request needs to be observable. Routine, low-risk work skips user confirmation of obvious inferred criteria. Record the contract before broad execution (TODO list, stated plan, or per-issue handoff); once started, criteria stay fixed unless the user changes them or a mandatory policy was omitted.

## Reactivation

A terminal task reopens only when evidence falsifies a named frozen criterion, a mandatory policy adds a blocker, or the user reopens it or makes a new request. Reviewer preference, optional hardening, a new context, or remaining budget cannot reactivate it. A child task's completion does not terminate its parent; a new request is new work unless it explicitly reopens the prior one. A consumer holding task identity and completion evidence must not reopen it without one of these events.

## Checklist

- [ ] The work product is named concretely, not as a category.
- [ ] A consumer is named, or the disposition is delete.
- [ ] The proposed action is the smallest one that unblocks that consumer.
- [ ] Any post-completion finding was tested against Blocker first.
- [ ] Every finding reached a stated disposition; none was dropped silently.
- [ ] Each drive-by fix has a Drive-By Fixes class, and no fix spawned another.
