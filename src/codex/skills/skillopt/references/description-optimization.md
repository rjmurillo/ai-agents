# Description optimization

Use this procedure when the defect is activation: a skill fails to load when it
should, or loads when it should not. The agent sees only `name` and
`description` before activation, so the description carries all of the
triggering.

Source: <https://agentskills.io/skill-creation/optimizing-descriptions>.

## Writing rules

Read `../../skillforge/references/skill-content-rules.md` (Description rules)
before you draft a candidate. Descriptions grow during optimization, so recheck
the 1024-character limit on every candidate.

## Build the query set

Write about 20 realistic prompts with a `should_trigger` label: 8 to 10 of each.

```json
[
  { "query": "my boss wants a chart from ~/Downloads/q4_final_v2.csv by friday", "should_trigger": true },
  { "query": "write a script that loads this csv into postgres", "should_trigger": false }
]
```

- Positives: vary phrasing, explicitness, detail, and step count. The best ones
  need the skill but do not name its domain.
- Negatives: use near-misses that share keywords but need something else. An
  unrelated prompt tests nothing.
- Realism: include file paths, personal context, specific values, casual
  language, and typos. Prefer prompts mined from real sessions.

## Score a description

1. Run each query 3 times with the skill installed.
2. Count a run as triggered only if the agent loaded the skill's `SKILL.md`.
   If your harness lets you, stop a run early once the detector sees the load.
3. Compute the trigger rate per query. A positive passes above 0.5. A negative
   passes below 0.5.

No skillopt script computes trigger rates or the length check. The runner does
both by hand: count loads over the 3 runs and divide by 3, apply the 0.5
threshold, and confirm `len(description) <= 1024` on every candidate.

Check the detector on one known-trigger run first. A detector that reads the
wrong output field scores every query as not triggered.

## Split before you iterate

Shuffle once, then fix the split for the whole run: about 60% train and 40%
validation, with the same positive and negative mix in each. Upstream's
validation set is skillopt's `sel` split. The runner who scores `sel` queries
keeps them from the author.

## Loop

1. Evaluate the current description on both sets.
2. Read failures from the train set only. Keep validation results out of the
   revision, including any prompt to an LLM.
3. Revise toward the general concept behind the failures.
   - Missed positives: broaden the scope or add contexts.
   - False triggers: state what the skill does not do, and draw the boundary
     with the adjacent skill.
   - Do not paste keywords from failed queries. That is overfitting.
   - If several rounds stall, try a different structure instead of more tweaks.
4. Stop when all train queries pass, improvement stops, or after about five
   iterations.
5. Select the iteration with the best validation pass rate. It may not be the
   last one.
6. The winner must also satisfy `pair-gate` semantics against the incumbent
   description: at least one gain on `sel` and zero regressions. Record each
   query as pass or fail for both descriptions, then run `pair-gate`. If the
   best pass rate still loses a query the incumbent passed, report that
   regression. Do not accept it silently.

If nothing improves, suspect the queries: too easy, too hard, or mislabeled.

## Finish

1. Update the `description` field and recheck the length.
2. Run 5 to 10 fresh queries that were never in the optimization set. Report
   that pass rate with the validation pass rate.

## Example

```yaml
# Before
description: Helps with invoices.

# After
description: Extract line items and totals from invoice PDFs and scans, and reconcile them against a ledger. Use when the user has vendor bills to enter or check, even if they never say "invoice" or "OCR".
```

The rewrite names the work (extract, reconcile) and the cases that should
trigger it. It stays under 1024 characters.

## Gate before you score

Run the cheap deterministic checks before a trigger-rate eval. They decide in
seconds and cost no model calls. The named pre-PR gates exist in the
rjmurillo/ai-agents repository; elsewhere, check the same limits by hand.

1. The description is at most 1024 characters.
2. The pre-PR gate `Skill Description Budget` still passes. A candidate that
   adds length takes it from every other skill's share of the corpus budget.
3. The pre-PR gate `Skill Trigger Phrase Resolution (ratchet)` still passes. Every quoted
   phrase routes to this skill and none routes to a sibling. Add an `intents`
   entry for a new phrase, or drop the phrase.
4. The pre-PR gate `Instruction Bytes (per-fixture)` still passes when the
   skill is always-on or routed in a fixture.

A candidate that fails any of these is rejected without scoring.

## Turn real misses into eval cases

A miss is a session that did a skill's work without loading the skill. Mine
transcripts for the request that led to the work, then add it three ways:

- A resolver fixture under the autoplan route fixtures. It is deterministic,
  so it fails before the fix and passes after.
- A description-router fixture that names the skill and its nearest sibling.
- An autoplan model scenario when the miss came through a plan step.

Include should-trigger queries that never name the domain. The 2026-11-19
`adr-generator` miss came from "go ahead with option B", where the plan said
option B needed an ADR.

## Gotchas

- Simple one-step requests may not trigger a matching skill, because the agent
  can handle them with basic tools. A miss on such a query says little about the
  description.
- Trigger rate shows the skill loads, not that it helps. Keep the output-quality
  gate for any claim about capability.
- Skill-activation counts from one environment are not grounds for removing a
  skill, because they cannot see use in other environments.
