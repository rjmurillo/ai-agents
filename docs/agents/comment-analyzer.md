# comment-analyzer agent

The `comment-analyzer` agent checks code comments against the code they describe. It flags mismatches with `file:line` evidence and proposes a specific change. It never edits code or comments itself.

## When to use it

- A pull request adds or changes comments or docstrings.
- You suspect comment rot: stale TODOs, outdated parameter names, or references to removed functions.
- You wrote large documentation comments and want them verified.
- A reviewer asks for a comment audit.

## When not to use it

- You want the changes applied: use [`implementer`](implementer.md) or the [`pr-comment-responder`](../skills/pr-comment-responder.md) skill instead.
- You want a general review of code correctness: use [`code-reviewer`](code-reviewer.md) instead.
- You want license headers or copyright notices reviewed: they are out of scope for this agent.

## Quick start

> [!NOTE]
> In Claude Code, this agent's GitHub tools need a GitHub MCP server, which the plugin does not provide. Without one, the agent still runs but cannot read pull requests or issues. See [GitHub MCP prerequisite](../installation.md#github-mcp-prerequisite).

In Claude Code, start your prompt with the agent name:

```text
comment-analyzer: check the docstrings changed in src/billing/invoice.py against the code
```

In GitHub Copilot CLI:

```bash
copilot --agent comment-analyzer --prompt "check the docstrings changed in src/billing/invoice.py against the code"
```

In VS Code or Visual Studio Copilot Chat:

```text
@comment-analyzer check the docstrings changed in src/billing/invoice.py against the code
```

## What you get

Three sections, in this order, with no preamble:

- Summary: three sentences at most. It gives the total analyzed, the count per bucket, and the highest-impact finding.
- Findings: up to 10 items in this format:

```text
file:line: [BUCKET] one-sentence description of the issue.
Evidence: <verbatim comment quote> | Code at line N: <verbatim code line>.
Proposed change: <specific edit, or "remove" with one-sentence rationale>.
```

- Recommendation: one sentence, one of `APPROVE: all comments accurate`, `CONDITIONAL APPROVE: N updates required`, or `BLOCK: N comments materially misleading; resolve before merge`.

## Advanced use

Every comment lands in exactly one bucket, assigned by this precedence:

| Order | Bucket | Rule |
| --- | --- | --- |
| 1 | Update | The comment mismatches the current code at its `file:line`, even if it also restates the code. |
| 2 | Remove | The comment is accurate but adds no information beyond the code. |
| 3 | Preserve | The comment is accurate and carries information the code cannot, such as intent, an invariant, performance rationale, security context, or an ADR reference. |

Before it flags a comment, the agent reads the code at the cited location and greps for every symbol the comment names. If the codebase is too large to grep, it downgrades the finding to "needs author confirmation."

It asks first when a comment is part of a public API contract, or when intent needs the original author. It skips generated files, vendored dependencies, lockfiles, and fixtures that hold wrong comments on purpose.

Status words:

| Status | Meaning |
| --- | --- |
| `[COMPLETE]` | Findings produced. Hand off to the `pr-comment-responder` skill for a PR thread, or to `implementer` for direct edits. |
| `[BLOCKED]` | Intent cannot be determined without the author. It flags and routes to the author. |
| `[NEEDS_DECOMPOSITION]` | More than 10 findings. It returns the top 10, ranked Update, then Remove, then Preserve. |

When an orchestrator delegated the task, a `[COMPLETE]` response ends with a recommendation to run `pr-review` to confirm the final diff.

A multi-step prompt:

```text
comment-analyzer: audit the comments changed on this branch, then list only Update findings with the proposed edit so I can pass them to implementer.
```

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| VS Code and Visual Studio | Yes |
| Codex | No |
| Cursor | Yes |
| Muse | No |

Codex and Muse cannot limit an agent's tools, so the build leaves this agent out.

## Related

- [`implementer`](implementer.md): applies the proposed comment changes.
- [`pr-comment-responder`](../skills/pr-comment-responder.md): applies changes when the findings come from a PR thread.
- [`pr-review`](../skills/pr-review.md): confirms the final diff after edits.
- [`code-reviewer`](code-reviewer.md): reviews code correctness and conventions.
- Source template: [`comment-analyzer.shared.md`](../../templates/agents/comment-analyzer.shared.md)
- How to call agents on each host: [Call agents and skills](../call-agents-and-skills.md)
