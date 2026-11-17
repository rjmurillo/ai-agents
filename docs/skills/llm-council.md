# llm-council

Asks several models from different vendors the same hard question, then combines their answers. Councillors answer in parallel, rank each other's answers without names, and a chairman writes the verdict. Use it when one model's habits could bias a judgment call.

## When to use it

- You face a decision where one model may lean toward its own vendor's priors: build or buy, framework choice, vendor selection, architecture forks.
- The question has no clear right answer, such as a prioritization or tradeoff call.
- You want a cross-check before you commit to a decision.
- Trigger phrases: `ask the council`, `council take on X`, `what do the models say`, `llm council`.

## When not to use it

- You have a routine question with one answer. A frontier council takes about 90 seconds and 50 to 80 AI Credits on the script route.
- The question is time-sensitive or already decided.
- You want a code review: use [`review`](review.md). For a GPT Sol second opinion on a change, use [`sol-loop`](sol-loop.md).
- You want one model to attack one decision: use [`decision-critic`](decision-critic.md).

## Quick start

In Claude Code, after a plugin install, run:

```text
/project-toolkit:llm-council Should we build our own feature flag service or buy one? --mode design
```

In a Claude Code session inside a checkout of this repository, drop the prefix: `/llm-council ...`. In GitHub Copilot CLI, name the skill with a slash in your prompt, such as `Use the /llm-council skill to ...`.

The argument hint is `<question> [--mode general|design|plan|research|review --models m1,m2 --cheap]`. Put all the context in the question. On the script route, councillors cannot read your files.

## What you get

A Markdown artifact. The script route writes it to `council/runs/<timestamp>.md` under the artifact root, and prints the chairman synthesis to stdout. The delegate route writes `council.md` in its run directory.

- The chairman synthesis, which is the verdict.
- The Borda ranking (a vote count where each ranker gives points by position), with model names.
- Stage 1: every councillor's full response, labeled and attributed.
- Stage 2: every ranker's raw output.
- Errors: each member that failed or was unavailable, with the reason.

When one response wins consistently, that is the strongest take. When rankings scatter, the council disagreed and the synthesis is bridging the gap.

## Advanced use

### Modes and members

Each mode picks a council and a chairman. `--models` replaces the council. `--chairman` replaces the chairman.

| Mode | Council | Chairman |
| --- | --- | --- |
| `general`, `design` | `gpt-6-astra`, `claude-opus-5.5`, `gpt-6-sol`, `claude-sonnet-5` | `gpt-6-astra` |
| `plan` | `gpt-6-astra`, `gpt-6-sol`, `claude-sonnet-5`, `claude-opus-5.5` | `gpt-6-astra` |
| `research`, `review` | `gpt-6-sol`, `claude-opus-5.5`, `claude-sonnet-5`, `gpt-6-astra` | `claude-opus-5.5` |
| `--cheap` | `meta/llama-3.3-70b-instruct`, `deepseek/deepseek-v3-0324`, `mistral-ai/mistral-medium-2505`, `openai/gpt-4.1` | `openai/gpt-4.1` |

If a member is unavailable, the skill reports it and never swaps in another model. The run goes on only while at least 3 members remain, or the whole council if it is smaller.

### Routes

Use the first route your host supports. Every route uses the same members, prompts, and Borda count.

| Route | How members run |
| --- | --- |
| 1. T3 Code | One `delegate_task` per member. `council_steps.py` writes the prompts. |
| 2. Harness subagents | One subagent per member, such as the Copilot CLI `task` tool with a `model`. A single-family host reaches only its own family. |
| 3. Member CLIs (last resort) | `council.py` runs all three stages. Claude members use `claude -p`, GPT members use `codex exec -s read-only`, other Copilot ids use `copilot -p`, and `--cheap` members use GitHub Models REST. |

A member the host cannot run moves to route 3, alone. Use route 3 when the other routes cannot reach the council, or for scheduled runs.

### Scripts

Run from the root of your working checkout:

```bash
uv run python .claude/skills/llm-council/scripts/council.py --help
uv run python .claude/skills/llm-council/scripts/council.py "QUESTION" --mode design --quiet
```

`council.py` takes `QUESTION`, `--mode`, `--models`, `--chairman`, `--cheap`, `--out`, `--quiet`, and `--min-responses` (default 3, at least 1, clamped to the council size).

| Script | Exit codes |
| --- | --- |
| `council.py` | `0` synthesis written (a failed chairman is recorded in the artifact), `1` a GitHub Models member needs `gh auth login`, `2` fewer councillors answered than `--min-responses`, or a config error such as an empty council |
| `council_steps.py` | `0` step done, `1` fewer councillors answered than the minimum, `2` config error: missing file, empty question, reused run directory, `chair` before `rank`, or a bad `--unavailable` value |
| `council_review.py` | `0` table printed, `2` no `round-<n>` directories, no members, or an unreadable directory |

`council_steps.py` has four subcommands over one `--run-dir`: `init` (takes `--question-file`, `--mode`, `--models`, `--chairman`, `--cheap`, `--min-responses`, and repeatable `--unavailable MODEL=REASON`), `rank`, `chair`, and `finish`. Each prints JSON that names the prompt to send and where each reply goes. `rank` freezes the survivors, and a Stage 1 reply that lands later is listed as late and left out.

### Review loop mode

Use this for scored code reviews instead of the three stages. Each member reviews the change read-only and ends its reply with one line `SCORE: N/10`. Save each reply as `<review-dir>/round-<n>/<member>.md`, then print the table:

```bash
uv run python .claude/skills/llm-council/scripts/council_review.py table --review-dir REVIEW_DIR --members m1,m2,m3
```

Put the `## Council review` section in the PR description. A member with no readable score shows `no score`. The skill never invents one.

### Honest limits

- Anonymous labels block direct self-recognition, but models still recognize their own style. The chairman may also be a councillor, so it is not an independent judge. Pass a `--chairman` that is not on the council when you need one.
- Unanimity is not proof. Models with shared training data can agree on the same wrong frame. Read the Stage 1 reasoning, not only the ranking.
- Codex `-s read-only` blocks writes but not reads. A member steered by an earlier reply could read files outside its temp directory.
- Copilot runs in an empty directory with only the `view` tool, but `view` can still read the system temp directory.
- Copilot CLI adds 22k to 35k input tokens of overhead per call, so each Copilot councillor takes 15 to 20 seconds.
- Questions over 24 KB may exceed a model's context. There is no streaming.
- Four frontier runs in a row burn about 250 AI Credits. Use `--cheap` for low-stakes questions.

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

- [`review`](review.md): the code review skill. Use it instead of review mode here when you want one verdict.
- [`sol-loop`](sol-loop.md): a GPT Sol second opinion on a change.
- [`decision-critic`](decision-critic.md): stress-tests one decision with one model.
- [`buy-vs-build-framework`](buy-vs-build-framework.md): a typical question to put to the council.
- [`autoplan`](autoplan.md): routes a council request here.
- Source: [`SKILL.md`](../../src/claude/skills/llm-council/SKILL.md)
- Script: [`council.py`](../../src/claude/skills/llm-council/scripts/council.py)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
