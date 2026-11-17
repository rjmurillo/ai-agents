# explainer agent

The `explainer` agent writes PRDs, explainers, and technical specifications that a junior developer can follow without asking questions. It hands back a finished document with its assumptions named.

## When to use it

- You need a PRD for a feature, with goals, non-goals, user stories, and acceptance criteria.
- You need an explainer for a concept or a piece of existing behavior.
- You need requirements that define scope and boundaries in unambiguous terms.

## When not to use it

- You need epics ranked by value: use [`roadmap`](roadmap.md) instead.
- You need a PRD broken into milestones: use [`milestone-planner`](milestone-planner.md) instead.
- You need a spec validated: use [`critic`](critic.md) instead.
- You need the feature built: use [`implementer`](implementer.md) instead.

## Quick start

In Claude Code, start your prompt with the agent name:

```text
explainer: write a PRD for rate limiting on the pr-review API, audience is junior developers
```

In GitHub Copilot CLI:

```bash
copilot --agent explainer --prompt "write a PRD for rate limiting on the pr-review API, audience is junior developers"
```

In VS Code or Visual Studio Copilot Chat:

```text
@explainer write a PRD for rate limiting on the pr-review API, audience is junior developers
```

## What you get

The agent writes a file with a relative path:

| Document | Path |
| --- | --- |
| PRD | `.project-toolkit/planning/PRD-[feature-name].md` |
| Explainer | `.project-toolkit/planning/EXPLAINER-[topic].md` |

It creates a GitHub issue only when you explicitly ask for one, with `gh issue create`.

A PRD has these sections: Overview, Goals, Non-Goals, User Stories, Functional Requirements, Acceptance Criteria, Success Metrics, and Open Questions. Design Considerations and Technical Considerations are optional.

An explainer has these sections: What is it, Why does it matter, How does it work, Key components, Example, Common pitfalls, and Related topics.

## Advanced use

The agent produces output by default and flags assumptions inline. It pushes back first only on vague requests such as "make the dashboard faster", where it asks for measurable targets. It asks questions first for novel features with several stakeholders, or when you ask "what should I consider". Before it asks, it searches code, memory, and docs. When it asks, it names the candidates it found.

It validates every user story against INVEST: Independent, Negotiable, Valuable, Estimable, Small, and Testable. It rejects a story that fails one, and says which and how to fix it.

Audience modes:

| Audience | Reading level | Jargon | Examples |
| --- | --- | --- | --- |
| Junior (default) | Grade 9 | Defined on first use | Required for complex concepts |
| Expert | No limit | Assumed | Only for nuance |

Before it emits prose, the agent runs the `prose-self-check` skill. It never commits absolute paths. It reads with `Read`, `Grep`, and `Glob`, writes with `Write`, searches the web, and uses Serena memory. Serena memory writes happen only from the checkout Serena started in.

The agent cannot delegate. It returns to the orchestrator with a completion status and a next step: a completed PRD goes to `milestone-planner`, a spec that needs validation goes to `critic`, and code-ready work goes to `implementer`.

A multi-step prompt:

```text
explainer: write a PRD for the merge-queue feature, list your assumptions inline, check every story against INVEST, then tell me whether milestone-planner or critic should run next.
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

- [`milestone-planner`](milestone-planner.md): breaks a finished PRD into milestones.
- [`critic`](critic.md): validates the spec.
- [`implementer`](implementer.md): builds from the spec.
- [`roadmap`](roadmap.md): ranks the epics a PRD comes from.
- [`prose-self-check`](../skills/prose-self-check.md): the audit the agent runs on its prose.
- Source template: [`explainer.shared.md`](../../templates/agents/explainer.shared.md)
- How to call agents on each host: [Call agents and skills](../call-agents-and-skills.md)
