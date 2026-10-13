---
source: wiki/concepts/Decision Making/Pre-Committed Metrics Force Honest Evaluation.md
created: 2026-06-01
review-by: 2026-09-01
---

# Pre-Committed Metrics Force Honest Evaluation

## Principle

The metric that proves a strategy worked must be agreed on before the strategy
runs. Pre-commitment closes the most common rationalization loop: judging a
result by whichever number happens to look good after the fact.

## The Three Instantiations

A convergence across three independent management traditions.

| Tradition | Mechanism | What it pre-commits |
|-----------|-----------|---------------------|
| Lean Startup (Innovation Accounting, Ries 2011) | Per-cohort baseline plus per-loop improvement targets | Which metric, if not improved by N percent, would justify a pivot |
| OKRs (Doerr 2018) | Committed key results are 100-percent-or-fail; aspirational are 70-percent-is-success | Which key results carry hard accountability versus stretch ambition |
| Toyota / Lean Operations | Actionable metrics tied to visible operational levers | Which signal triggers an andon-cord stop and which is informational only |

## The Unifying Claim

Without pre-commitment, the team will always find a number that retroactively
justifies whatever happened. Total signups went up, engagement stayed flat,
qualitative feedback was "mixed but encouraging". Pick the favorable framing and
ship the next thing.

Pre-commitment refuses the laundering. The team writes down, before the work
starts, the specific number, the specific threshold, and the specific
consequence ("if X is below Y, we pivot, kill, or re-staff"). When the number
comes in, the response is mechanical, not negotiated.

The political cost is real and is the point. Pre-committing means agreeing in
advance to a future moment of accountability. Most leaders prefer ambiguity,
which is why most orgs operate without these mechanisms even though the
templates are well-known.

## Operating Consequences

- Define the metric before the experiment, not after. A/B tests, OKR cycles, ML
  eval runs all get cooked when the success criteria are set after seeing the
  results.
- Separate informational metrics from decision metrics. A dashboard with 30
  numbers and no pre-committed thresholds is decoration. Pick the 1 to 3 that
  drive a fork in the road.
- Build the consequence into the calendar. Without a forcing function, the
  conversation gets deferred indefinitely.
- Distinguish "we missed" from "we set it wrong". Sometimes the metric was
  wrong, but that conversation has to happen explicitly, not as a stealth
  re-baseline mid-quarter.

## Why This Lens Applies In PR Review

A spec or ADR that proposes a change should state, before merge, the measurable
condition that would prove the change worked and the consequence if it did not.
When the diff stages acceptance criteria, an experiment plan, an eval target, or
a success metric, check that the threshold and its consequence are written down
in advance, not left to a post-hoc reading of whatever number looks good. A
decision that defers "we will see how it goes" or sets the success bar after
results arrive is the laundering loop this concept names. Flag it.

## Decision Critic Application

Use this reference during Challenge (Steps 5 to 6) when a decision proposes a
measurable outcome, an acceptance criterion, or a success metric.

### Verification Questions

1. Is the success metric defined before the work starts, or after results
   arrive?
2. Is there a specific threshold and a specific consequence tied to it?
3. Are decision metrics separated from informational metrics?
4. Is there a calendar forcing function that triggers the evaluation?

### Red Flags In Decisions

| Signal | Risk |
|--------|------|
| "We will measure success after launch" | Metric set after results; laundering loop open |
| "The dashboard will tell us" | Many numbers, no pre-committed threshold |
| "If it does not work we will reconsider" | No threshold, no consequence, no forcing function |
| Acceptance criteria with no numeric bar | Cannot tell pass from fail at review time |

## Related Models

- Survivorship bias: a success metric chosen after the fact often counts only
  the visible winners.
- Pre-mortem: pre-commit the failure threshold the same way you imagine the
  failure.

## Source

Eric Ries, The Lean Startup (2011). John Doerr, Measure What Matters (2018).
