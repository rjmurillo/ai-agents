# type-design-analyzer agent

The `type-design-analyzer` agent reviews the design of types. It rates encapsulation, invariant expression, invariant usefulness, and invariant enforcement, and hands back strengths, concerns, and concrete improvements.

## When to use it

- You are adding a new type and want its invariants checked.
- You want every type that a pull request adds reviewed.
- You are refactoring a type and want to improve its design.

## When not to use it

- You want a general code review of a diff: use [`code-reviewer`](code-reviewer.md) instead.
- You want a review of error handling: use [`silent-failure-hunter`](silent-failure-hunter.md) instead.
- You want a review of test coverage: use [`pr-test-analyzer`](pr-test-analyzer.md) instead.

## Quick start

In Claude Code, start your prompt with the agent name:

```text
type-design-analyzer: review the Invoice class in src/billing/invoice.py
```

In GitHub Copilot CLI:

```bash
copilot --agent type-design-analyzer --prompt "review the Invoice class in src/billing/invoice.py"
```

In VS Code or Visual Studio Copilot Chat:

```text
@type-design-analyzer review the Invoice class in src/billing/invoice.py
```

## What you get

A report per type in this layout:

```text
## Type: [TypeName]
### Invariants Identified
### Ratings
### Strengths
### Concerns
### Recommended Improvements
```

The Ratings section scores four dimensions from 1 to 10: Encapsulation, Invariant Expression, Invariant Usefulness, and Invariant Enforcement. Each score carries a count such as `3/4` of sub-criteria met, plus a short justification.

## Advanced use

Each dimension has four sub-criteria. The count maps to one exact score, so the same type gets the same score each time:

| Sub-criteria satisfied | Score |
| --- | --- |
| 4 of 4 | 10 |
| 3 of 4 | 7 |
| 2 of 4 | 5 |
| 1 of 4 | 3 |
| 0 of 4 | 1 |

A sub-criterion counts only when it is fully true. A partial match does not raise the count.

The agent flags these anti-patterns: anemic domain models, types that expose mutable internals, invariants enforced only through documentation, types with too many responsibilities, missing validation at construction, inconsistent enforcement across mutation methods, and types that rely on outside code to keep invariants. It weighs the complexity cost, breaking changes, and performance of each suggestion.

A multi-step prompt:

```text
type-design-analyzer: review every class added in this PR, rate each one, and rank the Recommended Improvements by how many bugs they would prevent.
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

- [`code-reviewer`](code-reviewer.md): reviews a diff for correctness and conventions.
- [`silent-failure-hunter`](silent-failure-hunter.md): audits error handling.
- [`pr-test-analyzer`](pr-test-analyzer.md): assesses test coverage on a PR.
- Source template: [`type-design-analyzer.shared.md`](../../templates/agents/type-design-analyzer.shared.md)
- How to call agents on each host: [Call agents and skills](../call-agents-and-skills.md)
