# Cross-Family Sol Pass

A second review on a different model family, run after the fresh critic. The
critic stays as it is. This pass adds to it and never replaces it.

Why add instead of swap: a fresh same-family review finds about as many bugs as
a review from another family. The two find mostly different bugs, so one fresh
review plus one cross-family review covers more than two fresh reviews. The run
log measures whether that holds here.

## When it runs

After the critic's readiness review, on the agent side. It is never a CI job and
never a required check. Save the critic's output to a file first; the script
refuses to run without it.

Run the script from this skill's directory:

```bash
( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/review/scripts/sol_pass.py run --critic-findings CRITIC_OUTPUT_FILE --round 1 --pr PR_NUMBER; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 )
```

Pass `--round 2` for the second round. Round 2 counts only defects the diff
introduced, per `frozen-finding-contract.md`. There is no round 3: the script
exits 1 and the open findings go to a human.

## Contract

| Rule | Behavior |
|------|----------|
| Model | GPT Sol only (`gpt-6.1-sol` by default). Gemini, Grok, Claude, and any other id are refused before a call. |
| Independence | Sol does not see the critic's findings. They are used only afterward, to mark overlap. |
| Findings | Each needs a file, a line, and a repro. A finding missing one, or a style nit, is dropped and logged as dropped. |
| Unavailable | `WARN` with reason `review-model-unavailable` and "Review model unavailable, deferring to human." No second call. No fallback to a same-family reviewer. |
| Rounds | At most 2. |

Exit codes: `0` pass ran or was switched off, `1` round cap hit (escalate),
`2` config error (no critic output, refused model, bad round), `3` Sol
unavailable (WARN, defer to a human).

A Sol `WARN` with findings is advisory input for the author and the human
reviewer. It does not join the `/review` verdict merge and writes no marker.

## Run log

Every run writes one JSON file to
`<artifact root>/metrics/sol-pass/<timestamp>-<pr>-r<round>-<status>.json`. The
artifact root is the plugin's default artifact directory in the reviewed checkout, or
`AI_AGENTS_ARTIFACT_ROOT` when set. A linked worktree is removed when its work
ends, so set that variable to a lasting directory to keep the logs.

Each file holds the PR, branch, head SHA, round, model, status (`ok`,
`skipped`, `unavailable`, `escalated`), failure class, every kept finding with
a `sol_only` flag, every dropped finding with its reason, and counts. A finding
is `sol_only` unless the critic cited the same file within 3 lines of it.

Total the logs:

```bash
( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/review/scripts/sol_pass.py summarize; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 )
```

`sol_only` over `kept` is the share Sol alone found. Check each one by hand
before you count it as a true catch: the log records what Sol raised, not
whether it was right.

## Turning it off

Set `AI_AGENTS_SOL_PASS=off`, or pass `--disable`. The run is logged as
`skipped` so the log still counts it.
