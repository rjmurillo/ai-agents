# software-engineering-library

Routes a design or code-risk question to the one or two book-derived references that fit it. You get an answer tied to files and validation evidence, without loading every reference.

## When to use it

- You are making an architecture or layer boundary decision.
- You are modeling a domain or splitting bounded contexts.
- You are refactoring, working through code smells, or adding tests to legacy code.
- Your code calls external APIs, queues, or retries, and you need timeouts, circuit breakers, or bulkheads.
- You are deciding on transactions, event ordering, data consistency, schema evolution, or module interface shape.
- You are moving working code to a newer runtime or framework version and want the same behavior.
- You say `architecture review` or `domain modeling bounded context`.

## When not to use it

- Prior art, wheel detection, or build versus buy: use [`programming-advisor`](programming-advisor.md) instead.
- Scoring the maintainability of one file: use [`code-qualities-assessment`](code-qualities-assessment.md) instead.
- Commonality and variability analysis: use [`cva-analysis`](cva-analysis.md) instead.

## Quick start

This skill has no short slash command, so the agent usually loads it for you. In Claude Code you can still type `/project-toolkit:software-engineering-library`. The agent loads it when your request matches. To ask for it by name, say:

```text
Use the software-engineering-library skill to review the dependency direction between the api and storage layers in src/.
```

The skill classifies your task, opens the smallest matching reference set, and applies it. At the end you get a recommendation that names the reference that changed the decision.

## What you get

A recommendation tied to files, user impact, and validation evidence. It names the reference that drove the decision. The skill writes no files and has no scripts.

## Advanced use

The router table maps task types to references:

| Task | Reference |
| --- | --- |
| Architecture, layer boundaries | [`clean-architecture.md`](../../src/claude/skills/software-engineering-library/references/clean-architecture.md), [`philosophy-of-software-design.md`](../../src/claude/skills/software-engineering-library/references/philosophy-of-software-design.md) |
| Domain modeling, bounded contexts | [`domain-driven-design.md`](../../src/claude/skills/software-engineering-library/references/domain-driven-design.md) |
| Persistence, repository, unit of work | [`enterprise-patterns.md`](../../src/claude/skills/software-engineering-library/references/enterprise-patterns.md) |
| Refactoring, code smells | [`refactoring.md`](../../src/claude/skills/software-engineering-library/references/refactoring.md) |
| Legacy code, seams, characterization tests | [`working-with-legacy-code.md`](../../src/claude/skills/software-engineering-library/references/working-with-legacy-code.md) |
| Runtime or framework version uplift, delta catalog, dual-run proof | [`version-uplift.md`](../../src/claude/skills/software-engineering-library/references/version-uplift.md) |
| Data systems, consistency, schema evolution | [`data-intensive-applications.md`](../../src/claude/skills/software-engineering-library/references/data-intensive-applications.md) |
| Production resilience, timeouts, bulkheads | [`release-it.md`](../../src/claude/skills/software-engineering-library/references/release-it.md) |
| DRY, orthogonality, tracer bullets, design by contract | [`pragmatic-programmer.md`](../../src/claude/skills/software-engineering-library/references/pragmatic-programmer.md) |
| Reviewing or generating code against the blocklist | [`forbidden-patterns.md`](../../src/claude/skills/software-engineering-library/references/forbidden-patterns.md) |

The process is: classify the task, open the smallest matching set, apply it, and add a second reference only when it changes the decision. Open no more than two references unless the task spans more than two book domains. Baseline code-quality rules stay the default for routine decisions.

The [`autoplan`](autoplan.md) skill routes design-depth and architecture-boundary questions here. Its long-tail resolver also routes a request that names a runtime, framework, or language upgrade here. Other skills that find a risk condition can also route here from their evidence.

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`programming-advisor`](programming-advisor.md): prior art and build versus buy.
- [`code-qualities-assessment`](code-qualities-assessment.md): single-file maintainability scoring.
- [`cva-analysis`](cva-analysis.md): commonality and variability analysis.
- [`autoplan`](autoplan.md): routes design questions here.
- Source: [`SKILL.md`](../../src/claude/skills/software-engineering-library/SKILL.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
