# critic agent

The `critic` agent stress-tests a plan before you implement it. It runs in fresh context, finds what breaks first, and hands back a verdict with a confidence level and specific findings. It writes a critique document and never edits the plan.

## When to use it

- You say `review this plan`, `stress-test this plan`, `is this plan ready`, or `poke holes in this`.
- You hand it a plan file or planning artifact and need a clear ready-or-revise verdict.
- Every other reviewer approved fast and you want an independent check.
- You want a pre-PR readiness check.

## When not to use it

- You want one decision's reasoning stress-tested: use the [`decision-critic`](../skills/decision-critic.md) skill instead.
- You want an assumption challenged with sourced alternatives: use [`independent-thinker`](independent-thinker.md) instead.
- You want a code diff reviewed for correctness: use [`code-reviewer`](code-reviewer.md) instead.

## Quick start

In Claude Code, start your prompt with the agent name:

```text
critic: review .project-toolkit/planning/PLAN-merge-queue.md
```

In GitHub Copilot CLI:

```bash
copilot --agent critic --prompt "review .project-toolkit/planning/PLAN-merge-queue.md"
```

In VS Code or Visual Studio Copilot Chat:

```text
@critic review .project-toolkit/planning/PLAN-merge-queue.md
```

## What you get

A critique document saved to `.project-toolkit/critique/[NNN]-[plan-name]-critique-[YYYY-MM-DD].md`. It has these sections: Verdict (with confidence of HIGH, MEDIUM, or LOW), Summary, Scores by Axis, Reasoning, Critical Findings, Approval Conditions, and Recommendation.

| Verdict | Meaning |
| --- | --- |
| `APPROVED` | Implementable as-is. All axes score 4 or higher and no critical gaps exist. |
| `APPROVED_WITH_CONCERNS` | Implementable with flagged, non-blocking issues. |
| `NEEDS_REVISION` | A critical gap exists in one or more axes. A specific revision is required. |
| `BLOCKED` | The plan cannot proceed: a missing dependency, misalignment, or a feasibility concern. |

The agent returns to the orchestrator with the verdict and confidence, the path to the critique, the count of critical findings, and a next step. Approved plans go to `implementer`. `NEEDS_REVISION` goes back to `milestone-planner` or `task-decomposer`. `BLOCKED` escalates to the orchestrator.

## Advanced use

Six axes, each scored 1 to 5: Completeness, Alignment, Feasibility, Risk coverage, Testability, and Traceability.

Length caps: a summary of 3 sentences, at most 5 critical findings, and a 1-sentence recommendation.

How it works:

- It reviews fresh. It has not seen the planner's reasoning and does not ask the author for clarification. Missing context is itself a finding.
- It answers three questions before any verdict: what breaks if the plan is wrong, which assumptions contradict project constraints, and what is the strongest counterargument.
- It searches ADRs under `.project-toolkit/architecture/` first and cites the ADR number and section when a finding depends on one.
- It does not invent findings to hit a count. When a full inspection finds nothing, it says what it checked and approves.
- Unanimous approval from other reviewers is a red flag. The agent says so, checks independently, and defaults to `NEEDS_REVISION` unless its own evidence supports the approvals.
- For code diffs it walks an adversarial checklist: boundary inputs, malformed inputs, regex boundaries, path-shape variants, source-of-truth invariants, mirror-obligation drift, status claims that rely on tool output, idempotency, failure paths, and generated-file drift. Each finding names the failed item and a one-sentence test to add. It proposes no fix.
- For prose artifacts it reads as a Naive Reader, a Hostile Expert, and a Cynic.
- It applies Brandolini's Law: when refuting a claim costs more than asserting it, "author supplies evidence first" becomes the finding.

Optional references live in the `decision-critic` skill's `references/` folder: `plan-critique-personas.md` and `plan-critique-brandolini.md`.

Missing information is a finding, not a blocker. A plan with no rollback steps gets a critical finding and a low risk score. The agent still issues a verdict without asking for more. Verdicts are internal judgments and need no confirmation. External or irreversible follow-on actions do.

A multi-step prompt:

```text
critic: review the plan at .project-toolkit/planning/PLAN-merge-queue.md, cite any binding ADR, score all six axes, and tell me what must change to reach APPROVED.
```

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| VS Code and Visual Studio | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`milestone-planner`](milestone-planner.md): revises plans the critic sends back.
- [`task-decomposer`](task-decomposer.md): revises task breakdowns.
- [`implementer`](implementer.md): builds approved plans.
- [`decision-critic`](../skills/decision-critic.md): tests a single decision.
- [`independent-thinker`](independent-thinker.md): challenges assumptions with sources.
- Source template: [`critic.shared.md`](../../templates/agents/critic.shared.md)
- How to call agents on each host: [Call agents and skills](../call-agents-and-skills.md)
