---
name: llm-council
version: 1.0.0
description: Run a cross-vendor LLM council on a hard judgment question. Councillors answer in parallel, rank each other anonymously by Borda count, and a chairman synthesizes. Default frontier members are GPT-6 Astra, GPT-6 Sol, Claude Opus 5.5, and Claude Sonnet 5. Use for "ask the council", "council take", or "what do the models say". Do NOT use for code review (use review) or a Sol-only review (use sol-loop).
license: MIT
argument-hint: "<question> [--mode general|design|plan|research|review] [--models m1,m2] [--cheap]"
user-invocable: true
metadata:
  source_pattern: thevgavini/ghcp-llm-council (MIT); T3 delegate transport from t3dotgg/tstack council (MIT)
  capability:
    kind: orchestrator
    owns: [multi-model-deliberation]
    status: active
  routing:
    role: front-door
    invoker: autoplan
    trigger: autoplan's long-tail resolver matches a request to ask several models for a verdict
    user-facing: true
    intents:
      - ask the council
      - council take
      - llm council
      - what do the models say
---

# LLM Council

Three-stage cross-vendor deliberation:

1. Councillors answer the question in parallel.
2. Each surviving councillor ranks every response anonymously. A Borda count
   aggregates the rankings.
3. A chairman reads Stage 1 and Stage 2 and writes the verdict.

Adapted from `thevgavini/ghcp-llm-council` (MIT License, Copyright (c) 2026
Vivekananda Gavini and ghcp-llm-council contributors,
<https://github.com/thevgavini/ghcp-llm-council>). The T3 Code delegate route
follows `t3dotgg/tstack` `council` (MIT License, Copyright (c) 2026 Theo
Browne, <https://github.com/t3dotgg/tstack>). Full license texts are in this
plugin's third-party notices.

## Triggers

`ask the council`, `council take on X`, `what do the models say`,
`llm council`

## When to use

- **Polystack decisions** where one model drifts toward its own vendor's
  priors: build or buy, framework choice, vendor selection, architecture forks.
- **Judgment-heavy questions** with no clear right answer: prioritization and
  tradeoff calls.
- **Sanity checks** on a decision you are about to commit to.

Do NOT use for:

- Routine single-opinion questions. A frontier council takes about 90 seconds
  and 50 to 80 AI Credits on the script route.
- Anything time-sensitive or already decided.
- Code review: use the `review` skill. For a GPT Sol second opinion on a
  change, use `sol-loop`.

## Members

**Never default to an older or cheaper model when current frontier access is
available.** Councils are task-shaped:

| Mode | Council | Chairman |
|---|---|---|
| `general`, `design` | Astra, Opus 5.5, Sol, Sonnet 5 | Astra |
| `plan` | Astra, Sol, Sonnet 5, Opus 5.5 | Astra |
| `research`, `review` | Sol, Opus 5.5, Sonnet 5, Astra | Opus 5.5 |
| `--cheap` | Llama 3.3 70B, DeepSeek V3, Mistral Medium, GPT-4.1 | GPT-4.1 |

- **Ambiguous judgment or architecture:** GPT-6 Astra owns ambiguity and
  acceptance; Opus 5.5 supplies broad frontier judgment; Sol supplies a
  technical counterweight; Sonnet 5 supplies an investigation-heavy take.
- **Clear implementation plan:** Astra owns the plan and acceptance criteria;
  Sol handles hard technical reasoning; Sonnet 5 probes failure modes; Opus 5.5
  provides a broad alternative.
- **Technical research or review:** Sol leads the specialist lane; Opus 5.5
  checks broad reasoning; Sonnet 5 checks evidence; Astra adjudicates scope.

These are routing defaults, not claims that one model wins every harness. The
member list is configurable: `--models` replaces the council and `--chairman`
replaces the chairman. If the user names members, use those.

## Process

Pick the first route the harness supports. Every route uses the same members,
prompts, and Borda count. **If a member is unavailable, report it. Never
substitute another model for it.** Run with the members you can reach only
while at least 3 remain (or the whole council, if it is smaller); otherwise
stop and report which members were missing.

### Route 1: T3 Code delegates

1. Call `orchestrator_capabilities` and resolve each member to the catalog
   model with the same family and version (`gpt-6-sol` may be listed as
   `gpt-6-sol` or `GPT-6 Sol`). A search by family name finds candidates, but
   a different version, such as `claude-opus-4.7` for `claude-opus-5.5`, is not
   the member: treat the member as unavailable.
2. Write the question to a file and run `council_steps.py init` on a new
   `--run-dir` with
   `--unavailable MODEL=REASON` for each missing member. It writes the Stage 1
   prompt and prints where each reply goes.
3. Start one `delegate_task` per member in parallel, each with the Stage 1
   prompt and a read-only brief: do not edit, commit, push, or start
   subagents. Save each reply to the path `init` printed.
4. Run `council_steps.py rank` once every councillor has answered or failed.
   It freezes the survivors; a Stage 1 reply that lands later is listed as late
   and left out. Start one `delegate_task` per survivor with the Stage 2
   prompt, and save each reply.
5. Run `council_steps.py chair`. It runs the Borda count. Start one
   `delegate_task` on the chairman with the Stage 3 prompt, and save its reply.
6. Run `council_steps.py finish` to write the artifact.

Do not wait idle: read each reply as it arrives. A timeout, error, or empty
reply is a missing answer, not a vote.

### Route 2: harness subagents

Outside T3, use the harness's own subagent tool (Codex `spawn_agent`, a
Copilot CLI task, a Claude Code subagent) with a model per member, and the same
`council_steps.py` steps. A member the harness cannot run is unavailable.

### Route 3: script

`council.py` runs all three stages itself through Copilot CLI
(`copilot -p --model <id>`, charges Copilot AI Credits) and GitHub Models REST
(free tier, needs `gh auth login`). Use it when the harness has no subagent
route, or for scheduled runs.

Delegates on routes 1 and 2 can use tools. The councillor prompt still says to
answer from knowledge only; keep their briefs read-only.

## Scripts

Run each from the root of your working checkout with the plugin locator, for
example:

```bash
( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/llm-council/scripts/council.py "QUESTION" --mode design; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 )
```

### `council.py`

Arguments: `QUESTION`, `--mode`, `--models`, `--chairman`, `--cheap`,
`--out`, `--quiet`, `--min-responses` (default 3, clamped to the council
size). The default output is `<artifact root>/council/runs/<timestamp>.md`.
Stderr shows progress; stdout prints the chairman synthesis.

| Exit | Meaning |
|---|---|
| `0` | Synthesis written (a failed chairman is recorded in the artifact) |
| `1` | A GitHub Models member needs `gh auth login` |
| `2` | Fewer councillors answered than `--min-responses` |

### `council_steps.py`

Subcommands `init`, `rank`, `chair`, `finish` over one `--run-dir`. Each
prints JSON naming the prompt to send and where each reply goes.

| Exit | Meaning |
|---|---|
| `0` | Step done |
| `1` | Fewer councillors answered than the minimum |
| `2` | Config error: missing file, empty question, a reused run directory, `chair` before `rank`, or a bad `--unavailable` value |

`council_core.py` and `council_backends.py` are shared modules, never run
alone.

### Model IDs

Copilot CLI (charges AI Credits): `claude-opus-5.5`, `claude-sonnet-5`,
`claude-opus-4.7`, `claude-sonnet-4.6`, `claude-haiku-4.5`, `gpt-6-astra`,
`gpt-6-sol`, `gpt-6-luna`, `gpt-5.6-sol`, `gpt-5.6-luna`, `gpt-5.5`,
`gpt-5.4`, `gpt-5.4-mini`, `gpt-5.3-codex`, `gpt-5-mini`, `gemini-3.8-flash`,
`grok-4.5`, `kimi-k3`.

GitHub Models REST (free tier): `meta/llama-3.3-70b-instruct`,
`deepseek/deepseek-v3-0324`, `deepseek/deepseek-r1`,
`mistral-ai/mistral-medium-2505`, `openai/gpt-4.1`, `openai/gpt-4.1-mini`,
`microsoft/phi-4`. The script routes any id in its Copilot list through
`copilot -p` and everything else through GitHub Models.

## Artifact

- Chairman synthesis (the verdict)
- Borda ranking with model attribution
- Stage 1: every councillor's full response, labeled and attributed
- Stage 2: every ranker's raw output
- Errors: each member that failed or was unavailable, with the reason

When one response wins consistently, that is the strongest take. When
rankings scatter, the council disagreed and the synthesis is doing real
bridging work.

## Honest limits

- **Self-voting bias is real but bounded.** Anonymous labels prevent direct
  self-recognition, but models still recognize their own style. The chairman
  may also be a councillor; it is not an independent judge.
- **Unanimity is not maximal confidence.** Borda rewards agreement, but blind
  consensus can be correlated failure: models that share training data
  converge on the same plausible but wrong frame (the ensemble "popularity
  trap" in arXiv:2510.21513). Read the Stage 1 reasoning, not only the ranking.
  Agreement reached by different routes is strong; agreement on one framing is
  suspect.
- **Copilot CLI adds 22k to 35k input tokens of harness overhead per call** on
  the script route, so each Copilot councillor takes 15 to 20 seconds.
- **The question must be self-contained** on the script route: councillors
  cannot read your files. Put the context in the question. Questions over
  24 KB may exceed a model's context.
- **No streaming.** You get the synthesis when it is done.

## Anti-Patterns

- Swapping in another model when a member is missing. Report it instead.
- Treating a unanimous council as proof.
- Making the chairman a councillor when you need an unbiased verdict. Pass a
  `--chairman` that is not on the council.
- Running several frontier councils in a row: 4 runs burn about 250 AI
  Credits on the script route. Use `--cheap` for low-stakes questions.

## Pitfalls

- **Generic output** when the question lacks context.
- **Borda parse failures** when a ranker skips the exact `FINAL RANKING:`
  block. That ranker is excluded; if 2 or more fail, treat the Borda result as
  suspect.
- **GitHub Models rate limits** after 3 or more councils in 5 minutes.
- **Copilot CLI wedges** on a permission prompt. The script passes
  `--allow-all-tools` to avoid it, which also means the CLI does not stop a
  councillor from using tools. If a run hangs, check `pgrep -af 'copilot -p'`.

## Verification

- [ ] Every member ran, or is listed as unavailable with a reason; none was
      replaced.
- [ ] At least 3 councillors answered (or the whole council, if smaller).
- [ ] The artifact holds the synthesis, the Borda ranking, and both stages.
- [ ] Unparsed rankers were named.
