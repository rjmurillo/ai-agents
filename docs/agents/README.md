# Agents

An agent is a specialist with one job, such as research, design review, or testing. You give it a task in plain language. It works in its own context and hands back a result in a fixed shape, such as a verdict or a plan.

Each page below covers one agent: when to use it, a prompt you can copy, what you get back, and how advanced users chain it with other agents.

New here? Read [Agents and skills](../agents-and-skills.md) for how the two fit together, then [Call agents and skills](../call-agents-and-skills.md) for the exact syntax on your host.

## Pick an agent by task

| You want to | Use |
| --- | --- |
| Hand off a multi-step job and let the toolkit pick the specialists | [`orchestrator`](orchestrator.md) |
| Find the root cause of a bug or research a question | [`analyst`](analyst.md) |
| Fix a bug with a step-by-step debugging pass | [`debug`](debug.md) |
| Write code from an approved plan | [`implementer`](implementer.md) |
| Review a design or write an ADR | [`architect`](architect.md) |
| Stress-test a plan before you build it | [`critic`](critic.md) |
| Review a diff before you commit | [`code-reviewer`](code-reviewer.md) |
| Test that a change works for real users | [`qa`](qa.md) |
| Threat-model a change or review it for security | [`security`](security.md) |
| Break an epic into milestones | [`milestone-planner`](milestone-planner.md) |
| Break a milestone or PRD into small tasks | [`task-decomposer`](task-decomposer.md) |
| Get a blunt priority call or a go or no-go verdict | [`high-level-advisor`](high-level-advisor.md) |
| Hear the strongest case against your idea | [`independent-thinker`](independent-thinker.md) |
| Write a PRD, spec, or explainer | [`explainer`](explainer.md) |
| Fix a merge conflict | [`merge-resolver`](merge-resolver.md) |
| Learn from a finished session | [`retrospective`](retrospective.md) |

## All agents

Agents fall into four roles. Coordinators route and judge other work. Strategic agents set direction. Executors produce code, tests, and reviews. Support agents research, explain, and clean up.

### Coordinators

| Agent | Use it to |
| --- | --- |
| [`critic`](critic.md) | Stress-test a plan and get a ready-or-revise verdict |
| [`issue-feature-review`](issue-feature-review.md) | Review a feature request and recommend what to do with it |
| [`milestone-planner`](milestone-planner.md) | Turn a roadmap epic into milestones with acceptance criteria |
| [`orchestrator`](orchestrator.md) | Route a multi-step task through the right agents, end to end |

### Strategic

| Agent | Use it to |
| --- | --- |
| [`architect`](architect.md) | Review system design, weigh trade-offs, and write ADRs |
| [`high-level-advisor`](high-level-advisor.md) | Get a ruthless priority call or a go or no-go verdict |
| [`independent-thinker`](independent-thinker.md) | Challenge assumptions with evidence and argue the other side |
| [`roadmap`](roadmap.md) | Decide what to build and why, and rank epics by value |

### Executors

| Agent | Use it to |
| --- | --- |
| [`code-reviewer`](code-reviewer.md) | Review a diff for bugs, project conventions, and duplicated logic |
| [`debug`](debug.md) | Find and fix a bug through a structured root-cause pass |
| [`dependency-auditor`](dependency-auditor.md) | Audit dependencies for vulnerabilities and outdated versions |
| [`devops`](devops.md) | Design or fix CI/CD pipelines, builds, and deployment |
| [`implementer`](implementer.md) | Write production code and tests from an approved plan |
| [`merge-resolver`](merge-resolver.md) | Resolve merge conflicts using history and commit intent |
| [`pr-test-analyzer`](pr-test-analyzer.md) | Check whether a pull request's tests cover the change |
| [`qa`](qa.md) | Verify a change works for users, beyond passing tests |
| [`security`](security.md) | Threat-model a change and gate security-sensitive PRs |
| [`silent-failure-hunter`](silent-failure-hunter.md) | Find swallowed errors and unsafe fallbacks in a change |
| [`type-design-analyzer`](type-design-analyzer.md) | Rate how well new types protect their invariants |

### Support

| Agent | Use it to |
| --- | --- |
| [`analyst`](analyst.md) | Research root causes, unknowns, and feasibility before you build |
| [`code-simplifier`](code-simplifier.md) | Simplify code you just wrote without changing what it does |
| [`comment-analyzer`](comment-analyzer.md) | Check that code comments are accurate and still true |
| [`explainer`](explainer.md) | Write PRDs, explainers, and specs a new developer can follow |
| [`janitor`](janitor.md) | Clean up dead code and pay down small tech debt |
| [`negotiation`](negotiation.md) | Analyze an offer and draft a counter-proposal |
| [`quality-auditor`](quality-auditor.md) | Grade each part of a repository from A to F and track gaps |
| [`retrospective`](retrospective.md) | Turn a finished session into root causes and lessons |
| [`skillbook`](skillbook.md) | Turn lessons into clean, deduplicated skill updates |
| [`task-decomposer`](task-decomposer.md) | Break a PRD or epic into small, testable work items |

## Related

- [Skills](../skills/README.md): the reusable workflows agents run.
- [Agent catalog](../agent-catalog.md): the generated table of every agent template, with line counts.
- [Plan, implement, and review with a team of agents](../plan-implement-review.md): agents working together on one change.
