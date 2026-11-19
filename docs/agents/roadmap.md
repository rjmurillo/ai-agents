# roadmap agent

The `roadmap` agent acts as the product owner. It decides what to build and why, ranks work by outcome with RICE and KANO scoring, and hands back a prioritized epic list, strategic concerns, and open questions.

## When to use it

- You have a backlog and need a ranked list with a rationale.
- You need an epic written with an outcome, success metrics, a hypothesis, and kill criteria.
- You are weighing build, buy, partner, or defer.
- You suspect the roadmap has drifted from user value.

## When not to use it

- You need an epic broken into milestones: use [`milestone-planner`](milestone-planner.md) instead.
- You need a PRD or an explainer written: use [`explainer`](explainer.md) instead.
- You need tactics for how to build something: leave that to engineering, such as [`implementer`](implementer.md) or [`architect`](architect.md). This agent does not prescribe tactics.
- You need strategic advice when the alignment itself is unclear: use [`high-level-advisor`](high-level-advisor.md) instead.

## Quick start

In Claude Code, start your prompt with the agent name:

```text
roadmap: rank the five open items in docs/roadmap.md by RICE and flag any that lack a user outcome
```

In GitHub Copilot CLI:

```bash
copilot --agent roadmap --prompt "rank the five open items in docs/roadmap.md by RICE and flag any that lack a user outcome"
```

In VS Code or Visual Studio Copilot Chat:

```text
@roadmap rank the five open items in docs/roadmap.md by RICE and flag any that lack a user outcome
```

## What you get

The agent returns four things to the orchestrator:

1. A prioritized epic list with RICE scores and rationale.
2. Strategic concerns: drift, scope creep, and missing outcomes.
3. Open questions that need stakeholder input.
4. A recommended next step: `milestone-planner` to break accepted epics into work packages, `explainer` to draft PRDs for top-priority epics, or `high-level-advisor` if strategic alignment is unclear.

Each epic has these sections: Outcome, Success Metrics, Hypothesis, Scope (in and out), Priority, Dependencies, Risk, Kill Criteria, and Outcome Review. The Outcome Review is filled after the epic ships. Its status is `shipped`, `rolled-back`, or `superseded`. Its hypothesis verdict is `confirmed`, `refuted`, or `inconclusive`. Its next action is `continue`, `iterate`, `kill`, or a new epic.

## Advanced use

Scoring frameworks:

```text
RICE = (Reach x Impact x Confidence) / Effort
Reach: users affected per quarter
Impact: 3 (massive), 2 (high), 1 (medium), 0.5 (low), 0.25 (minimal)
Confidence: 100% (certain), 80% (high), 50% (medium), 0% (speculation)
Effort: person-months
```

KANO classes are Must-Have, Performance, Delighter, and Indifferent. Cut Indifferent items first.

| Priority | Criteria | Action |
| --- | --- | --- |
| P0 | Security, compliance, production blocking | Drop everything |
| P1 | Revenue impact, retention, strategic commitments | Current quarter |
| P2 | Feature requests with user demand | Next quarter |
| P3 | Nice-to-have, experimental | Backlog, revisit |

Rules the agent keeps:

- It does not produce feature lists without outcome statements.
- It does not use RICE without explicit data. Speculation is confidence 0%.
- It does not accept unquantified success criteria. "Improve UX" is not a metric.
- It writes epics in precise technical language, such as "p95 latency under 200ms at 10k RPS".
- It frames build decisions as four options (build, buy, partner, defer) and answers with trade-offs.
- It runs a quarterly drift check: did shipped features move the metrics, and which features would you cut if scope dropped 30 percent.

The agent cannot delegate. It reads with `Read`, `Grep`, `Glob`, `WebSearch`, and `WebFetch`, and it reads Serena memory for prior strategic decisions.

A multi-step prompt:

```text
roadmap: review the epics in docs/roadmap.md, score each with RICE using the data in the file, mark confidence 0% where data is missing, answer build, buy, partner, or defer for the top two, and name the next agent to run.
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

- [`milestone-planner`](milestone-planner.md): breaks accepted epics into milestones.
- [`explainer`](explainer.md): drafts PRDs for top-priority epics.
- [`high-level-advisor`](high-level-advisor.md): resolves unclear strategic alignment.
- [`orchestrator`](orchestrator.md): receives the roadmap handoff.
- Source template: [`roadmap.shared.md`](../../templates/agents/roadmap.shared.md)
- How to call agents on each host: [Call agents and skills](../call-agents-and-skills.md)
