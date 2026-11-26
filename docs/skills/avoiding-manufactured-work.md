# avoiding-manufactured-work

Checks whether follow-up work has a real consumer. It also sorts any finding that appears after a task is done into one of four classes, so each finding gets a named outcome.

## When to use it

- A worker produced a plan, issue, PR, backlog item, research artifact, or follow-up task, and you need to know if a user, acceptance criterion, or blocked decision asked for it.
- You hold a finding that surfaced after the task was terminal and need to classify it.
- Trigger phrases: `is this work manufactured`, `does this follow-up have a consumer`, `classify this post-completion finding`, `should I file this follow-up`.

## When not to use it

- You need to decide whether the work should exist before you start it: use a front gate before the work starts, such as the external `front-gate-before-pipeline` skill (not part of this toolkit) or Phase 0 of [`panning-for-gold`](panning-for-gold.md). This skill fires after work looks done. <!-- orphan-ref-ignore -->
- You want to check a vendor or third-party claim against its primary source: use [`ai-agents-external-claims`](ai-agents-external-claims.md). That skill routes here when a deliverable has no consumer.

## Quick start

This skill has no short slash command, so the agent usually loads it for you. In Claude Code you can still type `/project-toolkit:avoiding-manufactured-work`. The agent loads it when your request matches. To ask for it by name, say:

```text
Use the avoiding-manufactured-work skill to check whether the follow-up issue I drafted for the retry logic has a consumer.
```

The skill names the work product, looks for its consumer, and returns a four-line disposition.

## What you get

The skill returns this block:

```text
Disposition: keep | shrink | defer | delete
Consumer: <named consumer or none>
Reason: <one sentence>
Next action: <smallest action, or none>
```

It also defines the friction report. When an agent works around a gap in a process, script, skill, or tool, its final report carries three lines per item:

```text
Hit: <process, script, skill, or tool, and what failed or was missing>
Did instead: <the workaround, with the script path if one was written>
Permanent fix: <the smallest change that removes the workaround, and where it lives>
```

The agent reports the item and does not fix it or file an issue. You decide whether to integrate it. Style opinions are not friction. With no workaround, omit the section.

| Disposition | Meaning |
| --- | --- |
| `keep` | The work satisfies an acceptance criterion, fixes a failing required check, resolves a reviewer thread, or unblocks a named decision. |
| `shrink` | The demand is real, but the proposed scope exceeds what the consumer needs. |
| `defer` | The demand is plausible, but no current consumer is blocked. |
| `delete` | The work is speculative, reputational, performative, or made to look thorough. |

If no consumer exists, the skill stops. It does not create a task, issue, PR, memo, or research artifact.

## Advanced use

The skill also owns the procedure that `builder-ethos.md` hands it for post-completion findings. Classify in this order, testing Blocker first:

| Finding class | Disposition |
| --- | --- |
| Blocker | `keep`, scoped to the falsified criterion |
| Requested improvement | `keep`, or `shrink` to the smallest action that satisfies it |
| Optional enhancement | `defer` |
| Side quest | `delete` |

A finding that falsifies mandatory safety or repository policy is a Blocker even when it sits outside the requested objective. It never maps to `delete`. A `defer` or `delete` is a disposition, not a silent drop: name the finding and its class in the report, then stop.

The skill also covers two related steps:

- **Forming the contract.** Before non-trivial work, record the smallest task contract: the user goal and deliverables, explicit constraints and acceptance criteria, mandatory policy, and the minimum inferred success criteria. Once work starts, the criteria stay fixed unless you change them or a mandatory policy was omitted.
- **Reactivation.** A terminal task reopens only when evidence falsifies a named frozen criterion, a mandatory policy adds a blocker, or you reopen it or make a new request. Reviewer preference, optional hardening, a new context, or leftover budget cannot reopen it.

Checklist the skill ends with:

- The work product is named concretely.
- A consumer is named, or the disposition is `delete`.
- The proposed action is the smallest one that unblocks that consumer.
- Any post-completion finding was tested against Blocker first.
- Every finding reached a stated disposition.

[`ai-agents-external-claims`](ai-agents-external-claims.md) points here to stop a deliverable that no consumer demanded.

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`ai-agents-external-claims`](ai-agents-external-claims.md): the skill that invokes this one.
- Source: [`SKILL.md`](../../src/claude/skills/avoiding-manufactured-work/SKILL.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
