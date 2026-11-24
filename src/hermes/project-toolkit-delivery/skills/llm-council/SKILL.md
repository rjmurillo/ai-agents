---
name: llm-council
version: 1.0.0
description: Cross-vendor LLM council for hard judgment calls, with parallel answers, Borda ranking, and a chairman verdict. Use for "ask the council". Not for code review (use review).
license: MIT
argument-hint: "<question> [--mode general|design|plan|research|review --models m1,m2 --cheap]"
user-invocable: true
---

# LLM Council

Three-stage cross-vendor deliberation:

1. Councillors answer the question in parallel.
2. Each surviving councillor ranks every response anonymously. A Borda count
   aggregates the rankings.
3. A chairman reads Stage 1 and Stage 2 and writes the verdict.

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
| `general`, `design` | GPT-6.2 Astra, Opus 5.5, GPT-6.2 Sol, Grok 4.7 | GPT-6.2 Astra |
| `plan` | GPT-6.2 Astra, GPT-6.2 Sol, Grok 4.7, Opus 5.5 | GPT-6.2 Astra |
| `research`, `review` | GPT-6.2 Sol, Opus 5.5, Grok 4.7, GPT-6.2 Astra | Opus 5.5 |
| `--cheap` | Llama 3.3 70B, DeepSeek V3, Mistral Medium, GPT-4.1 | GPT-4.1 |

- **Ambiguous judgment or architecture.** Astra resolves ambiguity and sets acceptance criteria.
  Opus weighs tradeoffs. Sol checks technical feasibility. Grok challenges assumptions.
- **Clear implementation plan.** Astra owns the plan and acceptance criteria.
  Sol handles technical reasoning. Grok probes failure modes. Opus considers alternatives.
- **Technical research or review.** Sol leads the technical analysis.
  Opus checks the reasoning. Grok checks evidence. Astra adjudicates scope.

These are routing defaults, not claims that one model wins every harness. The
member list is configurable: `--models` replaces the council and `--chairman`
replaces the chairman. If the user names members, use those.

For a Google perspective, add Gemini 4 Argon (`gemini-4-argon`) to the chosen roster.
Pass the full roster to `--models`, including Argon.

## Process

Use the first route the harness supports: T3 Code first, then the harness's
own subagents, then each member's own CLI. Every route uses the same members,
prompts, and Borda count. **If a member is unavailable, report it. Never
substitute another model for it.** Run with the members you can reach only
while at least 3 remain (or the whole council, if it is smaller); otherwise
stop and report which members were missing.

### Route 1: T3 Code delegates

1. Call `orchestrator_capabilities` and resolve each member to the catalog
   model with the same family and version (`gpt-6.2-sol` may be listed as
   `gpt-6.2-sol` or `GPT-6.2 Sol`). A search by family name finds candidates, but
   a different version, such as `claude-opus-4.7` for `claude-opus-5.5`, is not
   the member: treat the member as unavailable.
   Use the Antigravity provider for `gemini-4-argon`.
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
5. Run `council_steps.py chair`. It runs the Borda count and names rankers
   that never replied. Start one `delegate_task` on the chairman with the
   Stage 3 prompt, and save its reply. If `chairman_unavailable` is set, do not
   pick another chairman: `finish` records the reason.
6. Run `council_steps.py finish` to write the artifact.

Do not wait idle: read each reply as it arrives. A timeout, error, or empty
reply is a missing answer, not a vote.

### Route 2: the harness's own subagents

Outside T3, a harness that already runs several model families delegates with
its own subagent tool, one subagent per member, with the same
`council_steps.py` steps:

- **Copilot CLI**: the `task` tool, which takes a `model` per call.
- **Factory Droid, OpenCode**: a subagent (droid or agent) definition whose
  `model:` names the member.
- **Hermes**: its subagent delegation with a model per subagent.

A single-family harness reaches only its own family this way: a Claude Code
subagent runs Claude members, a Codex `spawn_agent` runs GPT members. A member
the harness cannot run moves to route 3, alone and on the same model. If route
3 cannot reach it either, it is unavailable.

### Route 3: each member's own CLI (last resort)

`council.py` runs all three stages itself, calling each member's own vendor
harness:

- Claude members: `claude -p --model <id> --tools ""`, prompt on stdin.
- GPT members: `codex exec -m <id> -s read-only -`, prompt on stdin.
- Other Copilot catalog ids, or a member whose CLI is not installed:
  `copilot -p --model <id>`. Charges Copilot AI Credits.
- Open-weight `--cheap` members: GitHub Models REST (needs `gh auth login`).

No call can write. Copilot keeps `--allow-all-tools` so a permission prompt
cannot wedge it. `--available-tools view` hides every other tool, including
MCP servers that plugins add. Deny rules (which win over every allow) also
remove shell, write, url, memory, and the built-in and user MCP servers.
The CLI route uses Copilot for Grok 4.7 and Gemini 4 Argon.
For long prompts, Copilot reads a prompt file with `view`.
That tool can also read the system temp directory. Codex `-s read-only`
blocks writes but not
reads, so a member steered by an earlier reply could read files outside its
temp directory. Use this route when neither route above can reach the council,
or for scheduled runs.

Delegates on routes 1 and 2 can use tools. The councillor prompt still says to
answer from knowledge only; keep their briefs read-only.

## Review loop mode

For a code review, run the members as scored reviewers instead of the three
stages (after `t3dotgg/tstack` `council`). Default members are the `review`
mode council; use members the user names instead.

1. Before the first round, answer open PR comments, fix known issues, and run
   the relevant checks, so reviewers see current code. Skip fixes to code the
   user wants to replace.
2. Start one delegate per member through the routes above, read-only, with the
   change and its context. Each ends its reply with one line `SCORE: N/10`.
   Save each reply as `<review-dir>/round-<n>/<member>.md`, where `<member>` is
   the member id with any character other than letters, digits, `.`, `_`, or
   `-` replaced by `_` (so `openai/gpt-4.1` is `openai_gpt-4.1.md`).
3. Do not wait idle: check each result against the code as it arrives. Do not
   edit files while a delegate still reviews the same checkout. A delegate the
   user marked non-blocking is not waited for, and a late result is feedback
   whose score is not recorded.
4. Fix what you agree with, then start a fresh round. Each full review pass is
   one round. Continue until every delegate is satisfied. Fight scope creep:
   decline what the change does not need.
5. Run `council_review.py table` and put the section in the PR description,
   before the model and harness line. Edit the open PR's description; do not
   post a comment. With no PR, put it in the final reply. A delegate with no
   score shows `no score`; never invent one.

## Scripts

Run each from the root of your working checkout with the plugin locator, for
example:

```bash
( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/llm-council/scripts/council.py "QUESTION" --mode design; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 )
```

When no plugin root holds `lib/ptk_run.py` (for example Codex, or a plain
checkout), run the script beside this SKILL.md directly. Each script finds its
own plugin's `lib/`:

```bash
python3 "<folder that holds this SKILL.md>/scripts/council.py" "QUESTION" --mode design
```

### `council.py`

Arguments: `QUESTION`, `--mode`, `--models`, `--chairman`, `--cheap`,
`--out`, `--quiet`, `--min-responses` (default 3, at least 1, clamped to the
council size). The default output is `<artifact root>/council/runs/<timestamp>.md`.
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

### `council_review.py`

`table --review-dir DIR --members m1,m2,m3` prints the `## Council review`
section from `DIR/round-<n>/<member>.md`, reading each `SCORE: N/10`.

| Exit | Meaning |
|---|---|
| `0` | Table printed |
| `2` | No `round-<n>` directories, no members, or an unreadable directory |

`council_core.py` and `council_backends.py` are shared modules, never run
alone.

### Model IDs

The script uses the installed Claude or Codex CLI for matching model families.
The bundled council core defines the Copilot allowlist as `COPILOT_MODELS`.
Copilot charges AI Credits.

GitHub Models REST (free tier): `meta/llama-3.3-70b-instruct`,
`deepseek/deepseek-v3-0324`, `deepseek/deepseek-r1`,
`mistral-ai/mistral-medium-2505`, `openai/gpt-4.1`, `openai/gpt-4.1-mini`,
`microsoft/phi-4`. The script tries GitHub Models after the native and Copilot checks.

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
  `--allow-all-tools` to avoid it; `--available-tools view` and its deny rules
  keep the call from writing.
  If a run hangs, check `pgrep -af 'copilot -p'`.

## Verification

- [ ] Every member ran, or is listed as unavailable with a reason; none was
      replaced.
- [ ] At least 3 councillors answered (or the whole council, if smaller).
- [ ] The artifact holds the synthesis, the Borda ranking, and both stages.
- [ ] Unparsed rankers were named.
