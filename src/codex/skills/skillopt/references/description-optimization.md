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
3. Compute the trigger rate per query. A positive passes above 0.5. A negative
   passes below 0.5.

Check the detector on one known-trigger run first. A detector that reads the
wrong output field scores every query as not triggered.

## Split before you iterate

Shuffle once, then fix the split for the whole run: about 60% train and 40%
validation, with the same positive and negative mix in each.

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

If nothing improves, suspect the queries: too easy, too hard, or mislabeled.

## Finish

1. Update the `description` field and recheck the length.
2. Run 5 to 10 fresh queries that were never in the optimization set. Report
   that pass rate with the validation pass rate.

## Gotchas

- Simple one-step requests may not trigger a matching skill, because the agent
  can handle them with basic tools. A miss on such a query says little about the
  description.
- Trigger rate shows the skill loads, not that it helps. Keep the output-quality
  gate for any claim about capability.
- Skill-activation counts from one environment are not grounds for removing a
  skill, because they cannot see use in other environments.
