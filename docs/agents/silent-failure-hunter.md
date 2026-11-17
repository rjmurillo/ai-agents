# silent-failure-hunter agent

The `silent-failure-hunter` agent audits error handling in a pull request. It finds suppressed errors, inadequate handling, and unsafe fallbacks, and hands back findings with a severity and a corrected example. It reviews and reports. It does not edit code.

## When to use it

- A change adds or edits `try`/`catch` blocks, fallback logic, or retry logic.
- You want a check on code that could swallow errors, such as optional chaining, null coalescing, or default return values.
- You finished a chunk of work with error handling and want it reviewed before the PR.

## When not to use it

- You want a general correctness review: use [`code-reviewer`](code-reviewer.md) instead.
- You want the findings applied: use [`implementer`](implementer.md), or let the PR author apply them.
- You want test coverage assessed: use [`pr-test-analyzer`](pr-test-analyzer.md) instead.

## Quick start

In Claude Code, start your prompt with the agent name:

```text
silent-failure-hunter: audit the error handling in the changes on this branch against main
```

In GitHub Copilot CLI:

```bash
copilot --agent silent-failure-hunter --prompt "audit the error handling in the changes on this branch against main"
```

In VS Code or Visual Studio Copilot Chat:

```text
@silent-failure-hunter audit the error handling in the changes on this branch against main
```

## What you get

For each issue, the agent reports:

1. Location: file path and line numbers.
2. Severity.
3. Issue description.
4. Hidden failure: the specific exceptions, error codes, or rejected promises the code could suppress.
5. User impact.
6. Recommendation.
7. Example of the corrected code.

| Severity | Meaning |
| --- | --- |
| CRITICAL | The error never surfaces: an empty catch, a broad or bare catch, caught-and-continue with no log, null or a default returned on error without logging, a retry that exhausts silently, or a fallback to a mock in production code. |
| HIGH | The error surfaces but handling is inadequate: a generic message, an undocumented fallback, or an error logged locally that should propagate. |
| MEDIUM | The error is handled but diagnostics are weak, such as missing context. |

## Advanced use

The agent follows six rules: failures must surface to someone who can act, user-facing messages must be actionable, fallbacks must be documented and observable, catch blocks must be specific, mocks belong only in tests, and secrets and private data never appear in logs.

It looks at every failure mechanism the language uses: exceptions, `Result` and error-value returns, error callbacks, sentinel values, exit codes, and async rejections. It asks about log quality, user feedback, catch specificity, fallback behavior, and error propagation. It also flags a test or lint rule disabled to hide a failure.

Before it flags, it checks three cases that can be valid:

- Best-effort cleanup that swallows its own failure while the original error still propagates and the cleanup failure stays observable.
- Documented optional operations, such as a telemetry ping, that fail without telling the user but are still logged or counted.
- Boundary translation to a domain error or status code, as long as the original error and stack are logged first.

Each of these needs documentation and preserved diagnostics. Without them the finding stands.

A multi-step prompt:

```text
silent-failure-hunter: audit PR 7361, list every CRITICAL finding with the hidden failures it masks, then give me the corrected code for each so implementer can apply it.
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

- [`code-reviewer`](code-reviewer.md): reviews overall correctness and conventions.
- [`implementer`](implementer.md): applies the recommended fixes.
- [`pr-test-analyzer`](pr-test-analyzer.md): checks that error paths have tests.
- [`type-design-analyzer`](type-design-analyzer.md): reviews type invariants.
- Source template: [`silent-failure-hunter.shared.md`](../../templates/agents/silent-failure-hunter.shared.md)
- How to call agents on each host: [Call agents and skills](../call-agents-and-skills.md)
