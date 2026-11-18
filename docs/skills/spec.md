# spec

Turns a problem into testable requirements with acceptance criteria. Two gates run first: a first-principles gate that asks whether the work should exist, and a memory-first gate that searches prior art. The result is a structured requirements document.

## When to use it

- You have a problem statement or issue and need requirements that can be judged pass or fail.
- You say `spec this out`, `what should we build`, `define the requirements`, or `turn this into acceptance criteria`.
- You are about to run [`plan`](plan.md).

## When not to use it

- You want requirements sequenced into milestones: use [`plan`](plan.md).
- You want code: use [`build`](build.md).
- You want the REQ, DESIGN, and TASK files emitted directly: use [`spec-generator`](spec-generator.md). This skill invokes it.
- You want a PRD or explainer written for people to read, not testable requirements: use the [`explainer`](../agents/explainer.md) agent.

## Quick start

In Claude Code, after a plugin install, run:

```text
/project-toolkit:spec Add rate limiting to the API
```

In a Claude Code session inside a checkout of this repository, drop the prefix: `/spec`. In GitHub Copilot CLI, name the skill with a slash in your prompt, such as `Use the /spec skill to ...`. The argument can be a problem statement or an issue number. With no argument, the skill asks what problem to solve and does not proceed without one.

First it asks six forcing questions. Answer them with specifics, because later steps read your answers verbatim.

## What you get

A structured requirements document that mirrors the PRD schema. Sections include:

- Problem statement, user stories, ontology, and data model
- Integrations, failure modes, security, and observability
- Acceptance criteria: numbered, in EARS syntax, each independently pass or fail
- Out of scope, deferred items, and open questions
- CVA summary (what is common, what varies)
- Buy-vs-build decision, or `N/A (bug fix / doc / refactor)`
- Complexity classification: engineering tier 1 to 5, plus problem domain (Clear, Complicated, Complex, Chaotic)
- Operating Model Context (Tier 5 only) and ADR cross-reference (Tier 4 and 5 only)

## Advanced use

**Step 0: first-principles gate.** This step is blocking and runs before any clarification. You answer six questions in order and the answers are written to a `## Step 0 First Principles` block with `### Q1` to `### Q6` subheads:

| Label | Question |
| --- | --- |
| Q1 Demand Reality | Who has explicitly requested this? |
| Q2 Status Quo | What is the exact workaround today, step by step? |
| Q3 Desperate Specificity | Who or what is most blocked right now, and on what? |
| Q4 Narrowest Wedge | What is the smallest deliverable that unblocks Q3? |
| Q5 Observation | What production signal proves the gap exists? |
| Q6 Future-fit | If the system grows 10x, is this still worth having? |

While the architecture is still open, a reframing check runs with Q2. End the Q2 answer with one of: `Reframing: skipped (<reason>)`, `Reframing: automation only`, or `Reframing: capability invention, check: <falsifiable signal>`. The pass criteria and kill criteria live in the `spec-generator` skill's `references/spec-step0-gates.md`.

**Step 0.5: memory-first gate.** Searches prior art before new spec work. It halts when the blast-radius count meets the mode threshold, or when a risky change type (such as removing an ADR constraint) has no prior record. Check 9e can also halt a Tier 5 spec that contradicts the elicited operating model. Finding that prior work already answers the question does not halt it. Read [`references/step-0-5-memory-gate.md`](../../src/claude/skills/spec/references/step-0-5-memory-gate.md) before running it, because the halt conditions are the point.

**Evaluation axes.** Problem clarity, requirement testability, completeness, traceability (REQ to DESIGN to TASK), and feasibility.

**Scripts.** Two helpers ship inside the skill. Run them from the root of a checkout:

```bash
uv run python .claude/skills/spec/scripts/redact_secrets.py --help
uv run python .claude/skills/spec/scripts/metrics_writer.py --help
```

| Script | Purpose | Exit codes |
| --- | --- | --- |
| `redact_secrets.py` | Redacts secrets from Step 0 and Step 0.5 tally text before any durable write. Takes an optional `file` argument, or reads stdin. | `0` success, `2` usage or read error |
| `metrics_writer.py` | Appends one tally line. Takes `--path PATH` plus `--line LINE` or `--stdin`. Refuses a symlinked target or a path outside the working directory. | `0` appended, `1` refused, `2` usage error |

The redaction step is blocking: if it fails, do not write.

**Chaining.** The skill calls [`requirements-interview`](requirements-interview.md), [`spec-generator`](spec-generator.md), [`threat-modeling`](threat-modeling.md), [`slo-designer`](slo-designer.md), [`cynefin-classifier`](cynefin-classifier.md), and [`pre-mortem`](pre-mortem.md) at named steps. It calls [`adr-generator`](adr-generator.md) at Tier 4 and 5, and [`work-operating-model`](work-operating-model.md) at Tier 5. Run [`plan`](plan.md) next.

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`plan`](plan.md): the next lifecycle step.
- [`spec-generator`](spec-generator.md): emits the durable REQ, DESIGN, and TASK files.
- Source: [`SKILL.md`](../../src/claude/skills/spec/SKILL.md)
- Reference: [`step-0-5-memory-gate.md`](../../src/claude/skills/spec/references/step-0-5-memory-gate.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
