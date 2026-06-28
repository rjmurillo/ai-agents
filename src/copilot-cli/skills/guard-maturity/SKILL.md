---
name: guard-maturity
version: 1.0.0
model: haiku
description: Classify push guards by Hook Maturity Model tier. Aggregates EVENT lines emitted by push_guard_base.py and assigns each guard a tier (Budding, Growing, Mature, Proficient, Inert, Harmful) based on age, intercept count, and fitness derived from block rate. Use to decide when to promote a new guard, when to prune dead weight, and when to remove a harmful one. Triggers `guard maturity report`, `classify push guards`, `hook maturity tiers`.
license: MIT
---

# Guard Maturity

Hook Maturity Model fitness scoring for the push guards (M2/M3/M4/M5
and any future siblings built on `push_guard_base.py`).

Hooks accumulate without measurement: a guard ships, gets some
intercepts, and stays forever even if it has stopped catching anything
real or has started blocking on a stale rule. This skill is the
measurement: real intercept counts feed real tier assignments, and the
tier dictates whether a guard gets kept, promoted, or pruned.

<!-- vendor-portability: declared. This skill reads push-guard telemetry from the consumer's .agents/telemetry/ and cites .agents/retrospective/2026-05-05-pr-1887-iteration-paradox.md as background. The telemetry directory is a read/append target created on demand; the retrospective is a documentation citation. A vendored install without .agents/ produces an empty report (no guards classified) rather than a silent failure. Issue #2050. -->

## Triggers

- `guard maturity report`
- `classify push guards`
- `hook maturity tiers`
- `prune inert guards`

## When to use

- **Periodic review** (recommended every 30 days once telemetry is
  flowing): run the report, prune Inert guards, promote Proficient
  ones, remove Harmful ones immediately.
- **Before adding a new guard**: confirm no existing guard already
  covers the case at a higher tier.
- **Pre-release**: include the report in the release notes so the team
  can see which guards are paying for themselves.

## What it does

1. Calls `python3 build/scripts/aggregate_guard_intercepts.py` against
   `.agents/telemetry/` (or stdin if no telemetry has landed yet).
2. Pipes the JSON summary into
   `python3 build/scripts/classify_guard_maturity.py`.
3. Prints a table (one row per guard) sorted by tier severity:
   `Harmful` first, then `Inert`, then `Budding`, `Growing`, `Mature`,
   `Proficient`.

## Tier definitions

| Tier | Age | Intercepts | Fitness | Action |
|---|---|---|---|---|
| Harmful | any | ≥3 | < -0.02 | Remove immediately |
| Proficient | ≥60 days | ≥10 | ≥ +0.02 | Promote, keep watching |
| Mature | ≥30 days | ≥5 | ≥ 0 | Keep, low review |
| Growing | 14-30 days | ≥1 | any | Adolescent, hold |
| Inert | ≥30 days | 0 | n/a | Prune candidate |
| Budding | <14 days | any | any | New, anything goes |

Fitness is `block_rate - 0.5` (centered). The full rationale lives in
the classifier's module docstring.

## Quick start

```bash
# Default: read .agents/telemetry/*.jsonl, classify, print report.
python3 build/scripts/aggregate_guard_intercepts.py \
  --guard markdown-lint --guard manifest-count --guard pr-description --guard session-log-field \
  | python3 build/scripts/classify_guard_maturity.py
```

The `--guard` flags ensure that guards which have NEVER fired still
appear in the report (otherwise an Inert guard with zero events would
silently drop out of the summary).

## Production wiring

The capture pipeline that writes to `.agents/telemetry/` is TBD; the
push guards already emit the right `EVENT=` lines on stderr per
`.claude/hooks/PreToolUse/push_guard_base.py`. Until the pipeline lands,
you can capture events ad-hoc:

```bash
git push 2>&1 | tee /tmp/push.log
grep '^EVENT=' /tmp/push.log >> .agents/telemetry/$(date +push-guard-events-%G-%V).jsonl
```

Then run the aggregator + classifier as above.

## Process

1. **Aggregate**: run `aggregate_guard_intercepts.py` against `.agents/telemetry/` (or stdin), passing `--guard` for every guard so never-fired guards still appear.
2. **Classify**: pipe the JSON summary into `classify_guard_maturity.py`, which assigns each guard a tier from age, intercept count, and fitness (`block_rate - 0.5`).
3. **Report and act**: read the tier table sorted by severity (Harmful, Inert, Budding, Growing, Mature, Proficient); remove Harmful guards, prune Inert ones, promote Proficient ones.

`run_report.py` runs steps 1 and 2 end-to-end.

## Scripts

| Script | Purpose | Exit codes |
|---|---|---|
| `scripts/run_report.py` | Wrapper that runs `aggregate_guard_intercepts.py` then `classify_guard_maturity.py` and prints the tier table (raw JSON to stderr). | `0` success; `3` external error (a build script is missing or fails per ADR-035); non-zero passthrough of a failed child process. |

## Verification

- [ ] Report lists one row per guard, including guards that never fired.
- [ ] Each guard has a tier assigned from the tier-definitions table.
- [ ] Rows are sorted by tier severity (Harmful first).
- [ ] Harmful and Inert guards are flagged for the operator to act on.

## See also

- `docs/guard-maturity-runbook.md` (how to read the report and what
  action each tier suggests).
- `.claude/hooks/PreToolUse/push_guard_base.py` (the EVENT contract
  this skill consumes).
- `.agents/retrospective/2026-05-05-pr-1887-iteration-paradox.md`
  (Phase 5 action items, Layer 5 of the iteration-paradox stack).
