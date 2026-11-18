# world-model-diagnostic

Runs a 20-minute structured audit that maps your team to a world-model paradigm (vector database, structured ontology, or signal-fidelity). It also finds where your organization automates judgment that should stay with people. You get a labeled assessment and a first, second, and third build step, with no numeric readiness score.

## When to use it

- You are choosing knowledge infrastructure (vector DB, ontology, telemetry pipeline) and want to check paradigm fit before you invest.
- Your organization is adopting agent-driven workflows and needs to know where automated judgment is safe.
- Leadership thinned a management layer and wants to know where editorial judgment lives now.
- You say `run the world model diagnostic`, `audit our world model`, `which world model architecture fits us`, `audit where we automate judgment`, or `what should we build first for a world model`.

## When not to use it

- Mapping team operating rhythms or decision flows: use [`work-operating-model`](work-operating-model.md) instead.
- A per-PR code or design review: use the [`analyst`](../agents/analyst.md) or [`architect`](../agents/architect.md) agent.
- Product strategy or roadmap priorities: use the [`roadmap`](../agents/roadmap.md) agent.
- Your organization already picked a paradigm and needs help building it: use the relevant build skill.

## Quick start

This skill has no short slash command, so the agent usually loads it for you. In Claude Code you can still type `/project-toolkit:world-model-diagnostic`. The agent loads it when your request matches. To ask for it by name, say:

```text
Use the world-model-diagnostic skill to audit where our support organization automates judgment, and recommend what to build first.
```

The skill tells you what it will do, asks two or three batches of questions about your signals and decisions, then audits your top information flows. At the end you get a final assessment with every conclusion labeled.

## What you get

The final assessment covers, in order:

1. Company case.
2. Paradigm fit.
3. Five-principle readout.
4. Boundary-layer status.
5. Top simulated-judgment exposures.
6. Starting sequence.
7. Confidence markers.
8. Shift since the last run, if a prior diagnostic is in memory.

Every conclusion carries one label: `Firm finding` (directly supported by your answer or a confirmed record), `Inference` (synthesis from evidence), or `Open question` (missing evidence that affects the recommendation).

The output uses these sections: `Firm Findings`, `Inferences`, `Open Questions`, `Paradigm Fit` (paradigm, plus boundary status of `explicit`, `implicit`, or `missing`), and `Recommended Build Order` (first, second, third). A JSON variant with the field names `firm_findings`, `inferences`, `open_questions`, `paradigm`, `boundary_status`, and `build_order` is acceptable when a tool consumes it.

## Advanced use

### Phases

1. Orientation: the skill checks memory for earlier diagnostics, states what it will do, and states where it will save results.
2. Intake: company size, industry, error cost, the top three to five data sources ranked by fidelity, where decisions and editorial judgment live, removed management layers, how outcomes are recorded, and how long durable systems have run.
3. Classification: a provisional paradigm until the boundary audit finishes.
4. Boundary audit: five to ten flows (top five if time is short). For each flow it records source, consumer, current human editor, a classification of `act on this` or `interpret this first`, the reason, what breaks if the editor disappears, and an exposure level of `high`, `medium`, or `low`.
5. Final assessment.

### Paradigm mapping

| Company type | Paradigm |
| --- | --- |
| Under 100 people, strong senior team | `vector database` |
| Enterprise, regulated, or operationally complex | `structured ontology` |
| Platform business with high-fidelity signal such as transactions or telemetry | `signal-fidelity` |
| Knowledge-work company (conversations, docs, soft context) | `vector database`, paired with boundary-layer work first |

When cues conflict, the skill weighs highest-fidelity signal first, then the cost of a bad interpretive decision, then the amount of senior human judgment available to absorb errors.

### Five-principle evaluation

| Principle | Classifications |
| --- | --- |
| Signal fidelity | `clear`, `mixed`, `low` |
| Earned structure | `earned`, `partially earned`, `imposed` |
| Outcome encoding | `present`, `partial`, `missing` |
| Organizational resistance | `byproduct`, `mixed`, `manual` |
| Time in system | `running`, `starting`, `not started` |

### Rules the skill follows

- No numeric readiness score.
- The boundary layer stays central. Database choice comes after boundary clarity.
- It audits actual flows, not aspirational diagrams, and asks you to rank signal sources.
- It does not pretend judgment is automated when interpretation still lives in people.

### Persistence

Unless you decline, the skill saves three entries to repository memory, keyed by company slug: `diagnostic-{company-slug}-intake`, `diagnostic-{company-slug}-boundary`, and `diagnostic-{company-slug}-assessment`. If you prefer files, it writes date-prefixed notes under `.project-toolkit/analysis/diagnostics/{company-slug}/`.

> [!NOTE]
> Serena memory writes go to the checkout where the Serena server started. From a linked worktree, the skill does not write memory. It returns the content to the parent session instead.

The skill has no scripts. Companion skills named in the source: [`work-operating-model`](work-operating-model.md) after the diagnostic, [`panning-for-gold`](panning-for-gold.md) when it surfaces unstructured brain dumps, and [`codebase-documenter`](codebase-documenter.md) for an engineering-organization follow-up.

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`work-operating-model`](work-operating-model.md): maps team rhythms and decision flows.
- [`panning-for-gold`](panning-for-gold.md): extracts threads from unstructured brain dumps.
- [`codebase-documenter`](codebase-documenter.md): documentation pass for engineering organizations.
- [`analyst`](../agents/analyst.md): per-change investigation.
- Source: [`SKILL.md`](../../src/claude/skills/world-model-diagnostic/SKILL.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
