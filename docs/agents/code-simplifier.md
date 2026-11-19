# code-simplifier agent

The `code-simplifier` agent simplifies recently modified code for clarity, consistency, and maintainability without changing what it does. It hands back either a rewrite diff or a list of named refactors, always with code.

## When to use it

- You just wrote or changed code and want it simplified before review.
- You want guard clauses, table lookups, or named functions in place of nesting and long `if` chains.
- You want refactors that keep every observable behavior.

## When not to use it

- You want deletion of dead code, unused dependencies, or tech debt: use [`janitor`](janitor.md) instead.
- You want a behavior change or feature: use [`implementer`](implementer.md) instead.
- You want a correctness review of a diff: use [`code-reviewer`](code-reviewer.md) instead.

## Quick start

In Claude Code, start your prompt with the agent name:

```text
code-simplifier: simplify the functions I changed in src/billing/invoice.py
```

In GitHub Copilot CLI:

```bash
copilot --agent code-simplifier --prompt "simplify the functions I changed in src/billing/invoice.py"
```

In VS Code or Visual Studio Copilot Chat:

```text
@code-simplifier simplify the functions I changed in src/billing/invoice.py
```

## What you get

One of two outputs, and no third option.

Option A, a rewrite diff for a small, self-contained change:

```text
file:start-end
<before-code>
<after-code>
Rationale: one sentence on why the after is simpler and preserves behavior.
```

Option B, a refactor list for several independent changes:

```text
N. file:line: <named transformation>
   Before: <code snippet, max 10 lines>
   After: <code snippet, max 10 lines>
   Rationale: one sentence.
```

The agent ends with one status word:

| Status | Meaning |
| --- | --- |
| `[COMPLETE]` | Refactors produced. Next step is `qa` for regression validation. |
| `[BLOCKED]` | Code is too broken to simplify safely, or callers cannot be located. Hands off to `implementer`. |
| `[NEEDS_DECOMPOSITION]` | More than 10 high-impact refactors apply. It returns the top 10 and proposes a follow-up session. |
| `[SECURITY_FLAG]` | A refactor would alter authentication, authorization, secret handling, or input validation. It stops and hands off to `security`. |

## Advanced use

Before it proposes anything, the agent reads the function end to end, greps for every caller, and reads at least one test when one exists. It works through three steps: what the code does, whether it is correct, and the simplest correct version. It will not simplify broken code.

Bounds: at most 10 refactors per response, at most 20 lines per before and after pair, and one sentence per rationale. Deferred refactors are named at the end as "Out of scope this pass."

Hard rules, from the Functionality Preservation section: same inputs give the same outputs, same side effects in the same order, same error modes, and same public API names. Renames are a separate refactor.

It skips generated files, vendored dependencies, and fixtures that hold ugly cases on purpose. It asks first when repository conventions conflict with its defaults, or when a refactor crosses an architectural or ownership boundary.

In the delegation flow it runs after `implementer` and before `qa`. When an orchestrator delegated the task, a `[COMPLETE]` response ends with a recommended next step to `qa`. When you call it directly, it ends on the result.

A multi-step prompt:

```text
code-simplifier: review the files changed on this branch, return the top refactors as a numbered list with before and after code, and flag anything that touches input validation.
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

- [`implementer`](implementer.md): writes the code this agent refines.
- [`qa`](qa.md): validates the simplified files still pass their tests.
- [`security`](security.md): takes over when a refactor touches security-sensitive code.
- [`janitor`](janitor.md): removes dead code and tech debt.
- Source template: [`code-simplifier.shared.md`](../../templates/agents/code-simplifier.shared.md)
- How to call agents on each host: [Call agents and skills](../call-agents-and-skills.md)
