# api-doc-authoring

Writes API documentation around the task a developer wants to finish, not around a list of endpoints. Every runnable example gets executed against a local or mock API, and failures come with a cause and an action.

## When to use it

- You are writing, rewriting, or touching API docs after a contract change.
- A developer will call the API to finish a task and needs a working path fast.
- Trigger phrases: `document this API`, `write the API guide`, `quickstart for this endpoint`, `add examples to the API docs`, `document the error responses`.

## When not to use it

- You want to verify claims in existing docs: use [`doc-accuracy`](doc-accuracy.md) instead.
- You are designing the API or its schema. This skill describes the contract and never redefines it.
- The page is a true reference listing, such as a generated schema page, or the API is trivial with one obvious call. Write the reference, mark it as reference, and stop.

## Quick start

In Claude Code, after a plugin install, run:

```text
/project-toolkit:api-doc-authoring
```

In a Claude Code session inside a checkout of this repository, drop the prefix: `/api-doc-authoring`. In GitHub Copilot CLI, name the skill with a slash in your prompt, such as `Use the /api-doc-authoring skill to ...`.

Then describe the API and the goal, for example "document the orders API so a developer can place an order and check it". The skill names the use case, writes the smallest working request and its response, lists likely failures with cause and action, and runs the examples. You end with a doc whose examples have evidence behind them.

## What you get

- A guide ordered by developer goal: minimum working request, expected response, common failures with remediation, then advanced options.
- Failure rows with status or error name, cause, and action. Where the contract or a run does not support a cause or action, the row says `Unknown`.
- An evidence JSON file from `run`, kept next to the doc.

The `api_examples.py` script has three subcommands:

| Subcommand | Purpose | Exit codes |
| --- | --- | --- |
| `list` | List examples in the docs, filtered by `--touching <path prefix>` | `0` listed, `2` bad input |
| `lint` | Find missing ids or status, unverified responses, and error rows without cause or action | `0` clean, `1` findings, `2` bad input or no examples found |
| `run` | Execute examples, compare status and documented response, write evidence | `0` all pass, `1` stale, failing, or lint findings, `2` unverifiable |

Exit `2` means unverified, never pass. It covers no matching example, an unreachable server, a response over 2 MiB, a request slower than 30 seconds, and a run longer than 300 seconds.

## Advanced use

From the root of a checkout of this repository:

```bash
uv run python .claude/skills/api-doc-authoring/scripts/api_examples.py --help
uv run python .claude/skills/api-doc-authoring/scripts/api_examples.py lint docs/orders.md
uv run python .claude/skills/api-doc-authoring/scripts/api_examples.py run docs/orders.md --base-url http://127.0.0.1:8080 --evidence evidence.json
uv run python .claude/skills/api-doc-authoring/scripts/api_examples.py list docs/orders.md --touching /orders
```

An executable example is a fenced `http` block whose info string carries an id and the expected status, for example `http example=create-order expect=201`. Read [`references/example-verification.md`](../../src/claude/skills/api-doc-authoring/references/example-verification.md) for the syntax and the evidence contract.

`run` refuses a non-loopback host unless you pass `--allow-remote`, because a doc example can create or delete data. It sends only to the base URL host and returns redirects as replies without following them. The evidence file is owner-only and refuses a symlink, a non-regular file, or a path outside the working directory. Windows refuses `--evidence`, so run without it there and save the stdout report.

A request that missed its 30 second deadline may still have reached the server. Check a mutating example by hand.

Chaining: the skill hands off to the lifecycle. The `test` skill's Gate 5 and the `review` skill's `doc-accuracy` axis already compose [`doc-accuracy`](doc-accuracy.md) for documentation, so this skill runs no second accuracy gate. After an API contract change, use `list --touching <path>` to find affected examples and re-run them. A changed request shape makes the stale example fail.

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`doc-accuracy`](doc-accuracy.md): checks behavioral and cross-document claims.
- [`test`](test.md): its Gate 5 runs the doc accuracy gate for docs.
- [`review`](review.md): its `doc-accuracy` axis covers docs changes.
- Source: [`SKILL.md`](../../src/claude/skills/api-doc-authoring/SKILL.md)
- Evidence contract: [`example-verification.md`](../../src/claude/skills/api-doc-authoring/references/example-verification.md)
- Entry shape: [`use-case-flow.md`](../../src/claude/skills/api-doc-authoring/references/use-case-flow.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
