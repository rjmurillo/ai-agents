# benchmark-models

Runs one prompt, or one skill file, through Claude, GPT (Codex CLI), and Gemini side by side. You get latency, tokens, cost, tool calls, and optionally a quality score, with a leader for each metric.

## When to use it

- You want to compare models on the same prompt with data.
- You want to see how a skill behaves across providers.
- Trigger phrases: `benchmark models`, `compare models`, `model shootout`, `which model is best`, `cross-model comparison`.

## When not to use it

- You want to measure web page performance: this skill measures models, not pages. Use a web performance tool.
- You want to tune a skill against a scored eval set: use [`skillopt`](skillopt.md) instead.

## Quick start

This skill has no short slash command, so the agent usually loads it for you. In Claude Code you can still type `/project-toolkit:benchmark-models`. The agent loads it when your request matches. To ask for it by name, say:

```text
Use the benchmark-models skill to compare claude and gpt on the prompt in prompts/summarize.md.
```

The skill first runs a dry run that shows which providers are ready. It asks which providers to include, runs them, and reports per-metric leaders. A request for "the best model" gets leaders and a rerun plan, not a winner, because one run per provider is inconclusive.

## What you get

- An availability block per provider: `OK` or `NOT READY` with a fix hint. If every provider is not ready, the skill stops.
- A table, JSON, or Markdown report with fastest, cheapest, and, if judged, highest quality.
- Errors per provider with a remediation path.
- Optionally, a saved JSON baseline so later runs can be diffed for regressions.

Exit codes of `model_benchmark.py`:

| Code | Meaning |
| --- | --- |
| `0` | Success |
| `1` | Logic or runtime error |
| `2` | Config or usage error |
| `3` | External dependency failure |
| `4` | Authentication or authorization failure |

## Advanced use

From the root of a checkout of this repository:

```bash
uv run python .claude/skills/benchmark-models/scripts/model_benchmark.py --help
uv run python .claude/skills/benchmark-models/scripts/model_benchmark.py --prompt "Summarize this repo" --models claude,gpt,gemini --dry-run
uv run python .claude/skills/benchmark-models/scripts/model_benchmark.py prompts/summarize.md --models claude,gpt --output markdown
```

Flags: `--prompt`, `--models` (comma-separated), `--judge`, `--dry-run`, `--output table|json|markdown`, `--workdir`, `--allow-cwd-workdir`, `--timeout-ms`, `--skip-unavailable`.

Safety points:

- The Claude provider uses `claude -p`, GPT uses `codex exec` in read-only mode, and Gemini runs with `--yolo`, which is not sandboxed. Claude and Gemini can write to the working directory.
- By default the script makes a fresh temp directory and removes it after the run. It refuses a `--workdir` inside the repo checkout or equal to the current directory (exit `2`) unless you pass `--allow-cwd-workdir`.
- Claude and Gemini run one after another. Providers run concurrently only when every selected provider is read-only GPT.
- `--judge` needs `ANTHROPIC_API_KEY` and adds real cost per run (about $0.05). The skill never turns it on without your approval. A judge error leaves quality blank and does not abort the run.
- When you benchmark a `SKILL.md` outside the repo and current directory, set `MODEL_BENCHMARK_SKILL_ROOTS` to the skills directory first, or the run exits `2`.
- Do not put secrets in prompts. The `gpt` and `gemini` CLIs receive the prompt as command arguments.
- Pricing comes from a `PRICING` table at the top of the script. An unpriced model costs `0.0` with a warning. Add a row instead of guessing.

The skill is an adjunct of `ai-agents-empirical-probe-toolkit`, which points to it for cross-model behavior comparison inside a checkout of this repository.

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`skillopt`](skillopt.md): gate a skill change against a scored eval set.
- [`ai-agents-empirical-probe-toolkit`](ai-agents-empirical-probe-toolkit.md): points here for cross-model comparison.
- Source: [`SKILL.md`](../../src/claude/skills/benchmark-models/SKILL.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
