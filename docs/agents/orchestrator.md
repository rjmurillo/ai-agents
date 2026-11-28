# orchestrator agent

The `orchestrator` agent coordinates specialist agents end to end. It classifies a task, routes it to the right agents, sequences handoffs, and hands back one synthesized result. It does not implement, design, or review.

## When to use it

- A task needs several steps, several specialists, or integration across domains.
- You want complete end-to-end resolution of a problem.
- You are not sure which specialist fits and want triage first.

## When not to use it

- You know the one agent you need: call that agent directly, such as [`implementer`](implementer.md) or [`analyst`](analyst.md).
- You have a request that names no skill and want the front-door router: use the [`autoplan`](../skills/autoplan.md) skill instead. It routes to the orchestrator for multi-agent work. The orchestrator never calls `autoplan`.
- You want code written: the orchestrator delegates that to [`implementer`](implementer.md).
- You want to run each lifecycle step yourself and see every gate: run [`spec`](../skills/spec.md), [`plan`](../skills/plan.md), and [`build`](../skills/build.md) in order instead.

## Quick start

> [!WARNING]
> The orchestrator can hand work to [`implementer`](implementer.md), which commits as it works. Create a feature branch before you start, so the commits do not land on your default branch.

In Claude Code, start your prompt with the agent name:

```text
orchestrator: add a dry-run flag to scripts/export_report.py end to end, from plan through tests
```

In GitHub Copilot CLI:

```bash
copilot --agent orchestrator --prompt "add a dry-run flag to scripts/export_report.py end to end, from plan through tests"
```

In VS Code or Visual Studio Copilot Chat:

```text
@orchestrator add a dry-run flag to scripts/export_report.py end to end, from plan through tests
```

## What you get

One coherent output that you can act on, not raw agent responses stitched together. The agent reports in these sizes:

| Output | Cap |
| --- | --- |
| Triage classification | 6 lines |
| Status update to you | 3 sentences |
| Synthesis | 400 words or 4 paragraphs |
| Continuity entry | 2 sentences per work item |

When an issue stays open, it writes a per-issue handoff to `.project-toolkit/sessions/handoffs/{YYYY-MM-DD}-{ISSUE_NUMBER}-handoff.md` and stores durable findings in Serena memory. It does not create session logs.

## Advanced use

Triage comes first. The agent classifies each task on four dimensions: complexity (Cynefin: clear, complicated, complex, chaotic), scope, urgency (P0 to P3), and reversibility (one-way or two-way door). Before triage it recons the target repository's stack from its docs, manifests, and layout, and it carries the language, build command, and test command into every handoff. If classification is ambiguous, it routes to `analyst` first.

Agents it can route to, by capability:

| Agent | Use for |
| --- | --- |
| `analyst` | Research, root cause, feasibility |
| `architect` | ADRs, design review, patterns |
| `critic` | Plan validation, pre-merge review |
| `debug` | Runtime failures, bug triage |
| `dependency-auditor` | Dependency CVEs, package health |
| `devops` | CI/CD, deployment, infrastructure |
| `explainer` | PRDs, documentation, onboarding |
| `high-level-advisor` | Strategy, priorities |
| `implementer` | Code changes, tests |
| `independent-thinker` | Challenge consensus |
| `issue-feature-review` | Triage feature requests |
| `milestone-planner` | Epic to milestones |
| `qa` | Test strategy, user-outcome validation |
| `pr-test-analyzer` | PR test coverage gaps |
| `quality-auditor` | Domain grading |
| `retrospective` | Post-mortem, learning extraction |
| `roadmap` | Strategic prioritization |
| `security` | Threat modeling, vulnerability review |
| `silent-failure-hunter` | Error suppression, unsafe fallbacks |
| `skillbook` | Capture learnings as skills |
| `task-decomposer` | Plan to atomic tasks |

A standard lifecycle routes sequentially: `/spec`, then `milestone-planner`, then `critic` as a plan gate, then `implementer`, then `qa`, then `critic` for readiness. At the plan gate, `APPROVED` or `APPROVED_WITH_CONCERNS` goes to `implementer`, `NEEDS_REVISION` goes back to `milestone-planner`, and `BLOCKED` is resolved first. Independent subtasks run in parallel with a fan-in synthesis.

Every delegation uses a work order with these fields: `DELEGATE TO`, `OBJECTIVE`, `NON-GOALS`, `CONTEXT`, `RISK TIER`, `ACCEPTANCE`, `STOP CONDITIONS`, `ESCALATE TO`, `ROLLBACK`, `EXPECTED OUTPUT`, `CONSTRAINTS`, `TIMEBOX`, and `TODO`. Non-trivial work without an objective, acceptance criteria, or risk tier is not routed. A worker fixes every defect on its path, with tests, and lists each fix in its receipt. Workers return a completion record under 30 lines with artifacts, commands run, deltas, residual risks, confidence, and acceptance status. A return that lacks the record fails closed.

Cost and effort routing follows task shape and verifier strength, not a vendor default: Bounded, Specified, Judgment, and Escalate tiers. The model labels in the source are advisory.

Budget limits: at most 15 delegations per task (a warning at 10) and at most 4 concurrent delegations per wave. A wave must not contain a repository-wide git operation or two agents writing the same file.

The agent verifies artifacts, not reports. When a worker declares a success criterion (ADR-065), it checks the return against it, and still verifies the artifacts. A "done" with no matching diff or file counts as unverified. It stops after acceptance. It checks session state before it acts after a handoff, compaction, or interruption, and holds when the live repository disagrees with the record. A hook denial is policy feedback, not consent.

In Claude Code, the agent sets no `tools` list, so it inherits every tool the session has. For the full routing algorithm, see [Orchestrator routing algorithm](../orchestrator-routing-algorithm.md).

A multi-step prompt:

```text
orchestrator: take issue 42 from triage to merge-ready. Run issue-feature-review, then milestone-planner, critic as a plan gate, implementer, qa, and security if auth files change. Synthesize one result and list unresolved items.
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

- [`autoplan`](../skills/autoplan.md): the front-door router that hands multi-agent work to the orchestrator.
- [`analyst`](analyst.md): the first stop when classification is ambiguous.
- [`milestone-planner`](milestone-planner.md): plans the work.
- [`implementer`](implementer.md): builds the work.
- [`qa`](qa.md): verifies the work.
- [`critic`](critic.md): gates plans and readiness.
- Source template: [`orchestrator.shared.md`](../../templates/agents/orchestrator.shared.md)
- How to call agents on each host: [Call agents and skills](../call-agents-and-skills.md)
