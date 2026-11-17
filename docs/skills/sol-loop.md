# sol-loop

Sends your change to OpenAI's GPT Sol for a second review, after the fresh critic has already reviewed it. Sol is a different model family, so it tends to find different bugs. You answer each finding with the smallest fix, or push back when it is wrong. The loop runs at most 2 rounds.

## When to use it

- The fresh `critic` has reviewed your change and you want a second model family to look at it.
- You want to know which bugs only Sol found, with a log you can total later.
- Trigger phrases: `sol loop`, `run a Sol review`, `cross-family review after the critic`, `second family review`.

## When not to use it

- You want a full pre-merge review across risk-selected axes: use [`review`](review.md).
- You want several models to debate a judgment call, not review a diff: use [`llm-council`](llm-council.md).
- A GPT model wrote the change. The `gate` step skips the pass, because Sol would be the same family.
- The fresh critic has not reviewed the current `HEAD`. Run the critic first, or the `gate` step refuses.
- You want Sol to run in CI. The skill is agent side only and never adds a CI job.

## Quick start

In Claude Code, after a plugin install, run:

```text
/project-toolkit:sol-loop 1234 --author-family anthropic
```

In a Claude Code session inside a checkout of this repository, drop the prefix: `/sol-loop 1234 --author-family anthropic`. In GitHub Copilot CLI, name the skill with a slash in your prompt, such as `Use the /sol-loop skill to ...`.

The argument hint is `[pr-number --author-family anthropic|openai|unknown]`. Name the family of the model that wrote the change. `unknown` still runs, and the log flags it.

The skill checks the scope, runs the `gate` step, starts Sol on the first route your host supports, records the reply, and helps you answer each finding.

## What you get

- A `PROCEED`, `SKIPPED`, or `ESCALATE` verdict from `gate` before each round.
- Sol's findings, kept only when each has a file, a line, and a repro. Nits are dropped.
- A run log per round, with each finding marked `sol_only` when the critic did not cite the same spot.
- A final report: rounds, model, what Sol changed, diff size before and after, fixed and declined findings with reasons, and the Sol-only count.

Sol must reply with `VERDICT: APPROVE` or `VERDICT: CHANGES`, then one line per finding:

```text
S1 [blocker|should|nit] <file>:<line> <claim>. Repro: <test, command, or inputs>. Fix: <suggestion>
```

| Severity | Meaning |
| --- | --- |
| `blocker` | The intended case is wrong. |
| `should` | A real bug that callers will hit, inside the intent. |
| `nit` | Everything else. Dropped. |

A finding with any other label is dropped as `unknown-severity`. A `CHANGES` verdict with no finding lines takes the WARN path.

## Advanced use

### Routes

Use the first route your host supports, and pass it to `gate` with `--route`.

| Route | `--route` | How Sol starts |
| --- | --- | --- |
| T3 Code | `t3` | `delegate_task` with `role: "review"`, one new task per round. |
| Harness subagent | `native` | The host's own subagent on a Sol model, such as the Copilot CLI `task` tool or Codex `spawn_agent`. |
| Native CLI (last resort) | `cli` | `sol_loop.py review` calls `codex exec -m <sol> -s read-only`, or `droid exec` when Codex is absent. |
| None | `none` | `gate` prints `SKIPPED`, writes no log, and the skill says "sol-loop skipped: no Sol route". |

With `--route cli`, `gate` also skips quietly when neither `codex` nor `droid` is on `PATH`.

### Rules the skill enforces

- Sol only. `sol_loop.py` refuses any model id that does not match `gpt-<version>-sol`, such as `gpt-6.1-sol`.
- At most 2 rounds (`MAX_ROUNDS = 2`). Round 1 is full. Round 2 checks open findings and code changed since round 1. A third `gate` returns `ESCALATE`: hand what is open to a human.
- One reviewer. Sol must not start subagents.
- A timeout, error, or empty reply is not approval. Run `unavailable` and stop. Never fall back to a Claude, Gemini, or Grok reviewer.
- Do not edit scoped files while Sol runs. Do not push during the loop.

### Scripts

Run from the root of the checkout under review:

```bash
uv run python .claude/skills/sol-loop/scripts/sol_loop.py --help
uv run python .claude/skills/sol-loop/scripts/sol_loop.py gate --route cli --critic-findings CRITIC_FILE --model gpt-6.1-sol --author-family anthropic
```

| Step | When | Flags beyond the shared set | Exit codes |
| --- | --- | --- | --- |
| `gate` | Before each round | `--route t3\|native\|cli\|none` (required) | `0` proceed or skip (read `verdict`), `1` round cap hit, `2` config error |
| `record` | After Sol replies | `--reply` (required), `--reviewed-head` | `0` logged, `1` round cap hit, `2` config error or log not written, `3` WARN: no verdict, `CHANGES` with no finding lines, or an unreadable reply file |
| `review` | CLI route: runs Sol, then records | `--brief-file` (required), `--timeout` (default 900 seconds) | As `record`, plus `3` when the CLI call fails (WARN) and `2` when no CLI is installed |
| `unavailable` | Sol started and failed | `--failure-class` (required), `--detail` | `3` WARN logged, `2` refused model id |
| `outcome` | After you answer a finding | `--run`, `--id`, `--outcome`, `--evidence` | `0` updated, `2` bad log or id |
| `summarize` | Any time | `--repo`, `--log-base` only | `0` totals printed |

`gate`, `record`, `review`, and `unavailable` share these flags: `--critic-findings` (required), `--model` (required), `--author-family` (required, `anthropic`, `openai`, or `unknown`), `--pr`, `--repo` (default `.`), and `--log-base`.

`--failure-class` takes `timeout`, `5xx`, `rate-limit`, `invalid-output`, `quota`, `model-unsupported`, `auth`, `cancelled`, or `unknown`. `--outcome` takes `fixed`, `disagree`, or `declined`. `--reviewed-head` names the commit Sol reviewed. If `HEAD` moved since, the log keeps that commit and adds `head_at_record`.

The WARN path prints reason `review-model-unavailable` and the message "Review model unavailable, deferring to human." The `unavailable` step still logs when the critic file is unreadable.

### Freshness check

`gate` refuses a missing critic file, or one older than `HEAD`, the last checkout, or any uncommitted change. Save the critic output outside the checkout and keep it out of the brief. A read-only sandbox can still read files outside the checkout, so this makes the file harder for Sol to find. It does not stop Sol from opening it.

### Run log

Each `record`, `unavailable`, escalation, and logged skip writes one JSON file to `metrics/sol-loop/<timestamp>-<branch>-r<round>-<status>.json` under the artifact root. The root is the plugin's default artifact directory in the checkout, or `AI_AGENTS_ARTIFACT_ROOT` when set. Commit each file with the branch it reviewed, because a removed worktree takes uncommitted files with it.

A finding is `sol_only` unless the critic cited the same file within 3 lines of it, or inside a cited range. A critic citation with no `path:line` or `#L` anchor is not matched, so read the count as an estimate. `summarize` totals runs by status, kept and dropped findings, and the outcome of each Sol-only finding.

### Turn it off

Set `AI_AGENTS_SOL_PASS=off`. Also accepted: `0`, `false`, `no`, `disabled`. `gate` then prints `SKIPPED` and logs the skip.

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |
| Hermes | Yes |

## Related

- [`review`](review.md): the pre-merge review. This skill is not a substitute for it.
- [`llm-council`](llm-council.md): several models answer a judgment question, with ranked votes.
- [`autoplan`](autoplan.md): routes a Sol or cross-family review request here.
- [`critic`](../agents/critic.md): the fresh critic that must review first.
- Source: [`SKILL.md`](../../src/claude/skills/sol-loop/SKILL.md)
- Script: [`sol_loop.py`](../../src/claude/skills/sol-loop/scripts/sol_loop.py)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
