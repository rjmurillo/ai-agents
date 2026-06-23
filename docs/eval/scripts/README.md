# Reproducing the moq.analyzers cross-provider comparison

These are the exact tools behind
[`../moq-analyzers-provider-comparison.md`](../moq-analyzers-provider-comparison.md).
Every table in that doc is reproducible from here.

## Prerequisites

- A checkout of [`rjmurillo/moq.analyzers`](https://github.com/rjmurillo/moq.analyzers):
  `export MOQ_REPO=~/src/moq.analyzers`
- Python deps: `pip install tiktoken openai`
- The `codex` CLI (OpenAI) and `claude` CLI (Anthropic), both logged in.
  Both use subscription auth, which bypasses metered API budgets. That is the
  whole point: it is how the run continued while the `ANTHROPIC_API_KEY` budget
  was exhausted.
- For the github-models table only: set `GITHUB_TOKEN` or `GH_TOKEN` through your secret manager.
- Output goes to `./out` by default; override with `export EVAL_OUT=...`.

## Files

| File | Purpose |
| :--- | :--- |
| `evalkit.py` | Shared core: the one rubric, score parsing, codex/claude transports, token + latency capture. |
| `run_sweep.py` | Generalized sweep: runs `(config x file)` cells, captures scores + tokens + latency. Drives every codex/claude table. |
| `run_github_comparison.py` | First table: multi-vendor via the github-models transport (PR #2710 `_providers`). |
| `analyze.py` | Computes the stats in the doc: distributions, paired gaps + 95% CI, cost (token + human). |
| `select_files.py` | Regenerates `eval_files24.json` (24 size-diverse product files). |
| `eval_files24.json` | The exact 24-file sample used. |
| `codex_eval_schema.json` | JSON output schema that forces the 5-quality + findings shape. |
| `configs/*.json` | One config set per doc table. |

## Reproduce each table

```bash
export MOQ_REPO=~/src/moq.analyzers

# Statistical run (N=24): family gap + version gap + economics
python3 run_sweep.py --configs configs/flagship_xhigh.json --out out/flagship.json
python3 analyze.py out/flagship.json \
  --pair opus-4-8/xhigh gpt-5.5/xhigh \
  --pair gpt-5.4/xhigh gpt-5.5/xhigh

# Lesser / cheaper-tier models (xhigh)
python3 run_sweep.py --configs configs/lesser_xhigh.json --out out/lesser.json
python3 analyze.py out/flagship.json out/lesser.json   # combined ranking

# Lesser-model effort sweep (sweet spot) + workflow cross-check configs
python3 run_sweep.py --configs configs/lesser_effort.json --out out/lesser_effort.json
python3 run_sweep.py --configs configs/crosscheck.json    --out out/crosscheck.json
python3 analyze.py out/flagship.json out/lesser.json out/lesser_effort.json out/crosscheck.json \
  --pair opus-4-8/high opus-4-8/xhigh --pair gpt-5.5/high gpt-5.5/xhigh

# Within-family version sweep (Opus 4.8/4.7/4.6, codex 5.5/5.4)
python3 run_sweep.py --configs configs/versions.json --out out/versions.json

# Effort sweeps
python3 run_sweep.py --configs configs/effort_codex.json  --out out/effort_codex.json
python3 run_sweep.py --configs configs/effort_claude.json --out out/effort_claude.json

# First comparison: multi-vendor via github-models (needs GITHUB_TOKEN)
python3 run_github_comparison.py
```

## Notes

- One sample per cell. Score wobbles of a single point are noise; the paired gaps
  (with CIs from `analyze.py`) are the load-bearing numbers. Re-run for tighter
  intervals.
- `claude -p` has no output-schema flag, so its JSON is best-effort and very
  occasionally returns an empty result; `run_cell` retries once.
- `max` effort is Claude-only; codex caps at `xhigh`. `gpt-5.3-codex`,
  `gpt-5.5-mini`, `gpt-5.4-nano`, `gpt-5-mini` are rejected by codex on ChatGPT
  accounts (they exist on the platform / Copilot, just not via this CLI path).
- Per-token rates live in `analyze.py` (`RATES`), verified against GitHub Copilot,
  OpenAI, and Anthropic pricing. Batch API is 50% off. Edit if prices move.
- The CLIs add ~16-18k tokens of harness context per call; cost uses the clean
  rubric+file input (`in_clean`) because that is what an API integration sends.
