# buy-vs-build-framework

Guides a strategic sourcing decision: build, buy, partner, or defer. It runs a four-phase process with a total cost of ownership (TCO) model and a weighted decision matrix, and it ends in an ADR and a reassessment plan.

## When to use it

- You are choosing between developing in-house, buying a vendor product, partnering, or deferring.
- The decision has a horizon of two years or more and real budget stakes.
- You need a TCO analysis to justify a budget.
- The team is split and needs an objective framework.
- You say `evaluate build vs buy for {capability}`, `should we build or buy {system}`, `core vs context analysis`, `strategic sourcing decision`, or `make or buy decision`.

## When not to use it

- You ask "is there a library for this": use [`programming-advisor`](programming-advisor.md) instead.
- The decision is made and you need to challenge it: use [`decision-critic`](decision-critic.md) instead.
- The decision is made and you need milestones and tasks: use [`plan`](plan.md) instead.
- You cannot tell whether the problem needs analysis or experiments: run [`cynefin-classifier`](cynefin-classifier.md) first.

## Quick start

This skill has no short slash command, so the agent usually loads it for you. In Claude Code you can still type `/project-toolkit:buy-vs-build-framework`. The agent loads it when your request matches. To ask for it by name, say:

```text
Use the buy-vs-build-framework skill to decide whether we build or buy an identity provider, with a 5 year TCO.
```

The skill picks an analysis depth, classifies the capability as Core or Context, computes TCO, scores the options, and recommends build, buy, partner, or defer with an ADR.

## What you get

| Phase | Output |
| --- | --- |
| 0. Depth selection | Quick, Standard, or Deep tier |
| 1. Classify | Core vs Context, a strategic score from 1 to 10, and red lines |
| 2. Analyze | TCO for 3, 5, and 10 year horizons, plus a team capacity check |
| 3. Evaluate | Decision matrix and a pre-mortem on the leading option |
| 4. Decide | Final decision, ADR, and reassessment schedule |

Depth tiers:

| Tier | Budget | Duration |
| --- | --- | --- |
| Quick | Under $50K | 1 to 2 hours |
| Standard | $50K to $500K | 1 to 2 days |
| Deep | Over $500K | 1 to 2 weeks |

The decision matrix weighs Strategic at 40%, Operational at 30%, and Risk at 30%. A gap under 10% between the top options is a tie, and you document the tie-breaker. The default for Core is build, and the default for Context is buy.

## Advanced use

The skill ships four scripts. Run them from the root of a checkout of this repository.

```bash
uv run python .claude/skills/buy-vs-build-framework/scripts/calculate_tco.py --discount-rate 0.12 --years 5 --build-initial 500000 --build-ongoing 100000 --buy-initial 50000 --buy-ongoing 200000
uv run python .claude/skills/buy-vs-build-framework/scripts/score_decision.py --criteria-file decision-criteria.json
uv run python .claude/skills/buy-vs-build-framework/scripts/score_vendor.py --vendor-data vendor.json
uv run python .claude/skills/buy-vs-build-framework/scripts/check_reassessment_triggers.py --adr-file adr-017-build-vs-buy.md --current-state current-state.json
```

`calculate_tco.py` flags:

| Flag | Meaning |
| --- | --- |
| `--discount-rate` | Required. For example `0.12`. |
| `--years` | Required. One of 3, 5, or 10. |
| `--build-initial` | Required. Upfront build cost. |
| `--buy-initial`, `--buy-ongoing` | Required. Upfront and annual buy cost. |
| `--build-ongoing` | Annual build cost, for simple mode. |
| `--engineer-cost`, `--maintenance-hours`, `--maintenance-growth`, `--code-churn-rate` | Realistic mode inputs for build overhead. |
| `--partner-initial`, `--partner-ongoing` | Partner costs. |

`score_decision.py` takes `--criteria-file`, a JSON file with `weights` and per-option scores. Exit 0 means a winner, with scores more than 10% apart and over 20% for high confidence. Exit 1 means a tie within 10% or a rejected path. Exit 2 means the file is missing, invalid, or failed validation.

`score_vendor.py` takes `--vendor-data`, a JSON file. Exit 0 is a pass (score over 70), 100 is a yellow flag (50 to 70), 101 is a red flag (under 50), 1 is a rejected path, and 2 is a missing or invalid file.

`check_reassessment_triggers.py` takes `--adr-file` and `--current-state`, a JSON file. Exit 3 means full re-evaluation: drift over 20%, or 3 or more triggers fired. Exit 2 means monitor closely: drift over 10%, or at least 1 trigger fired. Exit 0 means assumptions hold. Exit 1 means a missing file or invalid JSON.

Run `--help` on each script for the JSON shapes.

The skill chains to other skills: [`pre-mortem`](pre-mortem.md) in Phase 3, [`decision-critic`](decision-critic.md) and [`adr-review`](adr-review.md) in Phase 4 (adr-review for Standard and Deep tiers). Set reassessment checks at 6, 12, and 24 months. [`autoplan`](autoplan.md) routes strategic sourcing decisions here after [`programming-advisor`](programming-advisor.md) finishes prior-art discovery.

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`cynefin-classifier`](cynefin-classifier.md): decides whether the problem needs analysis or experiments first.
- [`pre-mortem`](pre-mortem.md): finds risks in the leading option.
- [`decision-critic`](decision-critic.md): validates the final rationale.
- [`adr-review`](adr-review.md): reaches multi-agent consensus on the ADR.
- [`plan`](plan.md): plans the work after the decision.
- Source: [`SKILL.md`](../../src/claude/skills/buy-vs-build-framework/SKILL.md)
- Reference: [`PHASE1_ANALYSIS.md`](../../src/claude/skills/buy-vs-build-framework/references/PHASE1_ANALYSIS.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
