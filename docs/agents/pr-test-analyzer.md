# pr-test-analyzer agent

The `pr-test-analyzer` agent reviews a pull request for test coverage. It measures behavioral coverage, not line coverage, and hands back a ranked list of gaps with `file:line` evidence and one recommendation.

## When to use it

- You created or updated a pull request and want to know if the tests cover the new behavior and edge cases.
- You want a ranked list of the untested behaviors a real bug would hit.

## When not to use it

- You want a general code review: use [`code-reviewer`](code-reviewer.md) instead.
- You want the missing tests written: use [`implementer`](implementer.md) instead.
- You want verification that the feature works for real users: use [`qa`](qa.md) instead.
- You want the test files themselves analyzed: this is out of scope for the agent.

## Quick start

In Claude Code, start your prompt with the agent name:

```text
pr-test-analyzer: assess test coverage for the changes on this branch against main
```

In GitHub Copilot CLI:

```bash
copilot --agent pr-test-analyzer --prompt "assess test coverage for the changes on this branch against main"
```

In VS Code or Visual Studio Copilot Chat:

```text
@pr-test-analyzer assess test coverage for the changes on this branch against main
```

When you omit the scope, the agent uses your current working changes.

## What you get

Three sections, in this order, with no preamble:

- Summary: three sentences at most. It says what the diff changes, the count of behaviors introduced versus tested, and the most severe gap.
- Findings: up to 10 items in this format:

```text
file:line: [CRITICALITY/10] one-sentence description of the gap.
Behavior at risk: <branch, error path, or boundary the missing test would cover>.
Failure it prevents: <specific bug class the test would catch>.
Proposed test: <name + 1-sentence assertion>.
```

- Recommendation: one sentence, chosen by the highest criticality found.

| Highest rating | Recommendation |
| --- | --- |
| 9 to 10 | `BLOCK: N critical gaps rated 9-10 must be resolved before merge` |
| 7 to 8 | `CONDITIONAL APPROVED: N tests rated 7-8 should be added before merge` |
| 1 to 6 | `APPROVED: coverage adequate for behavior introduced (no findings rated 7+)` |

## Advanced use

Criticality rubric:

| Score | Meaning |
| --- | --- |
| 9 to 10 | Untested paths that could cause data loss, security issues, authentication or authorization bypass, or production-stopping failures |
| 7 to 8 | Untested business logic that would produce user-visible errors or silent data corruption (one severity class) |
| 5 to 6 | Edge cases that produce confusing behavior or subtle bugs |
| 3 to 4 | Coverage that improves regression safety but is not load-bearing |
| 1 to 2 | Nit-level suggestions; omitted by default |

Before it claims a behavior is untested, the agent discovers the test framework and locations from your manifests, runner config, CI scripts, and existing layout. It greps for the function name across those locations and reads at least one matching test file. If grep is too broad, it downgrades the finding to "needs author confirmation."

It checks tests against the repository floor: positive, negative, and edge tests, every branch exercised, and external dependencies mocked. It skips trivial getters and setters, generated code, and vendored dependencies.

Status words:

| Status | Meaning |
| --- | --- |
| `[COMPLETE]` | Findings produced. Hand off to `implementer` to write tests, or to `pr-review` if APPROVED. |
| `[BLOCKED]` | The PR adds a new test framework. Hand off to `architect` first. |
| `[NEEDS_DECOMPOSITION]` | More than 10 findings rated 5 or higher. It returns the top 10 and proposes a follow-up audit issue. |
| `[SECURITY_FLAG]` | A gap touches authentication, authorization, secrets, or input validation. It hands off to `security` for sign-off, whatever the score. |

The agent runs after the `implementer` and QA gates. A `[COMPLETE]` response ends with a recommended next step: `implementer` to write tests when any finding is 7 or higher, or `pr-review` for the final diff check when APPROVED.

A multi-step prompt:

```text
pr-test-analyzer: review PR 123, list findings rated 7 or higher, then give me the test names to hand to implementer.
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

- [`implementer`](implementer.md): writes the proposed tests.
- [`qa`](qa.md): verifies the feature for real users.
- [`security`](security.md): signs off on gaps in security paths.
- [`architect`](architect.md): decides when a PR adds a new test framework.
- [`pr-review`](../skills/pr-review.md): gives the final completion verdict.
- Source template: [`pr-test-analyzer.shared.md`](../../templates/agents/pr-test-analyzer.shared.md)
- How to call agents on each host: [Call agents and skills](../call-agents-and-skills.md)
