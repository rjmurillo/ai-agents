# Stalled-investigation strategy comparison: protocol v3

Issue #7350. Supersedes `PROTOCOL-v2.md` for the run. Committed and pushed
before any v3 launch. Nothing here may change after the first v3 launch.

## Why v2 produced no result

The v2 run started at 2026-11-15T20:13Z at runner commit
`faf2837b6a77fd0acf6c0c59975432acc06201c0`, with the retry added in v2. It ran
under the subscription login (`--real-home`, no forwarded variables). By
20:33Z it had recorded 0 cells, and no CLI child was alive between checks. The
v1 batch had already shown that login path returning `rate_limit_error` on the
first launch. I read this as the retry waits cycling on a login that is rate
limited or failing on this machine, which the operator also reported. I stopped
the process (exit 143). It left no records and no `report.json`, so the v2 run
directory held nothing to archive. No cell ever reached a reproduction, a
held-out check, or a decision, so no outcome was seen.

## The one change

The auth path. The model calls go to the operator's local API hub instead of the
subscription login. The harness forwards two variables to the CLI child with
`--pass-env`, names only: `ANTHROPIC_BASE_URL` and `ANTHROPIC_API_KEY`. The
operator's env file sets them outside the repository. Their values appear in no
report, file, commit, or PR, and the runner masks them in recorded output.
`--real-home` stays, so `~/.claude` still loads in both arms as in v1.

The frozen model is unchanged and the hub serves it. A one-line check before this
file was written returned a stream whose resolved model was `claude-sonnet-5-5`
and whose result was `OK`. The harness still rejects any launch whose resolved
model differs from the requested one, so a substitution would fail the run
rather than pass silently. Billing is now API cost reported in each stream's
`total_cost_usd`. The hub's own pricing is not independently verified, so
spend figures are as the stream reports them.

Confound, shared by both arms: a hub route may differ from the first-party
endpoint in latency and rate behavior. Wall time is therefore not comparable to
any run made under the login, and the report makes no such comparison.

## Unchanged from v1 and v2

Task file (SHA-256 `bad0f411a3a6681037942b45c760fab949dffa3a3ee50d2a35cfde0cce8ab315`),
base and fix commits, reproductions, held-out checks, `known_good` and
`known_bad`, arms, role files and hashes, instructions, prompt templates, tools,
model `claude-sonnet-5-5`, effort `medium`, harness version, 3 repetitions per
arm per task, 2 repair rounds, 600 s per launch, `--max-cells 12`,
`--max-cost-usd 20`, the v2 transient-retry rule, per-run fields, abort
conditions, limits, and the decision rule.

## Run command

```bash
. /path/to/operator/eval-env.sh   # sets ANTHROPIC_BASE_URL and ANTHROPIC_API_KEY
uv run python scripts/eval/eval_handoff_strategy.py \
  --tasks scripts/eval/examples/handoff-strategy-tasks.json \
  --repeats 3 --model claude-sonnet-5-5 --effort medium --max-cells 12 \
  --max-cost-usd 20 --timeout 600 --real-home \
  --pass-env ANTHROPIC_BASE_URL,ANTHROPIC_API_KEY \
  --workspace-root "$(mktemp -d)" \
  --output-dir evals/handoff-strategy-historical/runs/2026-11-15-v3
```
