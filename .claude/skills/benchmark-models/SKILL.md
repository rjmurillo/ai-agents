---
name: benchmark-models
version: 1.0.0
description: Cross-model benchmark. Runs one prompt or skill through Claude, GPT (Codex CLI), and Gemini side by side and compares latency, tokens, cost, tool calls, and optionally output quality via an Anthropic-API judge. Answers "which model is actually best for this skill?" with data. Use when you say "benchmark models", "compare models", "which model is best for X", "cross-model comparison", or "model shootout". Do NOT use to measure web page performance.
license: MIT
model: claude-opus-4-8
metadata:
  domains:
  - benchmarking
  - model-evaluation
  - cost-analysis
allowed-tools:
  - Bash
  - Read
  - AskUserQuestion
---

# benchmark-models

Run the same prompt across providers and compare them on data, not vibes. The
deterministic work lives in `scripts/model_benchmark.py` (stdlib-only, ported
from gstack's bun benchmark; no SDKs, no gstack runtime). This skill is the
interactive wrapper: pick a prompt, preview auth with a dry-run, confirm
providers, run, interpret, optionally save.

Providers wrap existing CLIs and their own auth (no API keys needed except the
optional judge):

- `claude` via `claude -p --output-format json`
- `gpt` via `codex exec ... -s read-only --json`
- `gemini` via `gemini -p ... --output-format stream-json`

## Triggers

Invoke this skill when the user says any of:

- `benchmark models`
- `compare models`
- `model shootout`
- `which model is best`
- `cross-model comparison`

Do NOT invoke for web page performance (that is a different concern).

## Preconditions

- At least one provider CLI installed and authenticated. The Step 1 dry-run
  reports exactly which are ready; if none are, the skill stops.
- The optional quality judge needs `ANTHROPIC_API_KEY` (adds ~$0.05/run).

## Process

Resolve the driver first. In a repository checkout, use `BENCH="$(git rev-parse --show-toplevel)/.claude/skills/benchmark-models/scripts/model_benchmark.py"`. From an installed skill copy, use the local skill path: `BENCH="$PWD/scripts/model_benchmark.py"` when your shell is in the `benchmark-models` skill directory.

### Step 1: Pick a prompt and preview auth (dry-run)

Decide the prompt with AskUserQuestion:

- A) Benchmark a skill: pass that skill's `SKILL.md` path as the prompt. To list
  candidates, search the installed skills dir, not just `.` (skills usually live
  under `~/.claude/skills/` or `~/.copilot/skills/`, not the project root).

  Allowed-root constraint: `$BENCH` reads a prompt file only when it
  resolves under the repo checkout, the current directory, or a path listed in
  `MODEL_BENCHMARK_SKILL_ROOTS` (see `resolve_prompt` and `_allowed_prompt_roots`
  in the benchmark script). A `SKILL.md` under `~/.claude/skills/` or
  `~/.copilot/skills/` is outside the repo and cwd, so the run aborts with exit
  code 2 ("prompt file must be under an allowed root") and benchmarks nothing.
  Before running, export the skills dir, for example
  `export MODEL_BENCHMARK_SKILL_ROOTS=~/.claude/skills` (or `~/.copilot/skills`),
  or copy the file into and run from an allowed root. A prompt already inside the
  repo or cwd needs no env var.
- B) Inline prompt: pass `--prompt "<text>"`.
- C) A prompt file on disk: pass its path (verify it exists first).

Then preview availability without spending anything:

```bash
python3 "$BENCH" --prompt "dry-run" --models claude,gpt,gemini --dry-run
```

The "Adapter availability" block shows OK or NOT READY (with a remediation hint)
per provider. If ALL are NOT READY, STOP: nothing can run. Suggest `claude`,
`codex login`, or `gemini login` / `export GOOGLE_API_KEY`.

### Step 2: Confirm providers and judge

From the dry-run, AskUserQuestion which providers to include (default: all
authed). Unauthed providers are skipped cleanly and never abort the batch.

If `ANTHROPIC_API_KEY` is set, AskUserQuestion whether to enable `--judge`
(quality scoring, ~$0.05). Never auto-enable it; it costs real money. If the key
is absent, omit `--judge`.

### Step 3: Run

```bash
python3 "$BENCH" <prompt-spec> --models <picked> [--judge] --output table
```

`<prompt-spec>` is `--prompt "<text>"` (B) or a file path (A/C). Stream the
output; each provider runs the full prompt, so expect 30s-5min.

For an installed-skill path (A) under `~/.claude/skills/` or `~/.copilot/skills/`
(outside the repo and cwd), export `MODEL_BENCHMARK_SKILL_ROOTS` first (see Step 1
Option A) or the run aborts with exit code 2 before any provider starts.

### Step 4: Interpret and optionally save

Summarize: fastest (latency), cheapest (cost), highest quality (if judged), and
a best-overall call that names the tradeoff. Call out any provider that errored,
with its remediation path. Offer to save a JSON baseline so future runs can be
diffed for regressions:

```bash
python3 "$BENCH" <prompt-spec> --models <picked> [--judge] --output json > benchmark-$(date +%Y%m%d)-<slug>.json
```

## Scripts

### model_benchmark.py

Runs the benchmark. Pure stdlib; safe to run directly.

```bash
python3 scripts/model_benchmark.py <prompt-file | --prompt "text"> \
  [--models claude,gpt,gemini] [--judge] [--dry-run] \
  [--output table|json|markdown] [--workdir PATH] [--timeout-ms N] [--skip-unavailable]
```

Exit codes (ADR-035): `0` success, `1` logic/runtime error, `2` config or usage
error, `3` external dependency failure, `4` authentication or authorization
failure.

Notes:

- `--dry-run` resolves auth and prints availability without sending any prompt.
- The judge posts to the Anthropic Messages API via stdlib `http.client` (no SDK)
  and fails soft: a judge error warns and leaves quality blank, it never aborts
  the run.
- Do not place secrets in prompts. The `gpt` and `gemini` CLIs receive the prompt
  through command arguments, which some systems expose through process listings
  or crash reports.
- Safety asymmetry: the `gpt`/codex adapter runs `-s read-only`; the `gemini`
  adapter passes `--yolo` (auto-approve), which is NOT sandboxed. Benchmark in a
  disposable `--workdir` if the prompt could trigger file writes.
- The driver only runs providers concurrently when every selected provider is
  read-only GPT/Codex. Claude and Gemini run sequentially because they can mutate
  the workdir.
- Pricing lives in the `PRICING` table at the top of the script. An unpriced
  model costs `0.0` with a stderr warning; add a row rather than guess.

## Anti-Patterns

| Avoid | Why | Instead |
| --- | --- | --- |
| Running the benchmark before the dry-run | Spends API calls on unauthed providers that will just error | Always Step 1 dry-run first; only run authed providers |
| Auto-enabling `--judge` | It adds real per-run cost the user did not approve | Opt-in only, after the Step 2 question |
| Benchmarking in a live repo with a write-prone prompt | The gemini adapter is not sandboxed (`--yolo`) | Use a disposable `--workdir` |
| Guessing a price for an unlisted model | Produces a wrong cost number that looks authoritative | Add a row to the `PRICING` table; unlisted stays `0.0` with a warning |
| Listing skills to benchmark via `find .` only | Installed skills live under `~/.claude` / `~/.copilot`, not the project root | Search the installed skills dir |

## Verification

The skill run is complete when:

- [ ] Step 1 dry-run ran and its availability block was shown to the user.
- [ ] If zero providers were authed, the run STOPPED (no benchmark attempted).
- [ ] The benchmark ran only the user-confirmed providers.
- [ ] If the prompt was a skill `SKILL.md` outside the repo/cwd,
      `MODEL_BENCHMARK_SKILL_ROOTS` was set (or the file staged under an allowed
      root) so the run did not abort with exit code 2.
- [ ] `--judge` was included only after explicit user opt-in.
- [ ] Results name the fastest, cheapest, and (if judged) highest-quality model,
      with errors and their remediation surfaced.
- [ ] `python3 -m pytest .claude/skills/benchmark-models/tests` passes (the
      driver carries unit tests at 100% coverage).
