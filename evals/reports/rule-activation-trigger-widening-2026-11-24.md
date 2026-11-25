# Rule-Activation: Skill Trigger Widening (2026-11-24)

PR #7541 kept 11 path rules because routing to their skills lost capability.
This run asks whether wider skill descriptions fix that routing.
A rule is cut only when its skill route scores close to the loaded rule.

## Method

- Model: `claude-opus-5-5` for responses, routing, and the judge.
- Provider: `EVAL_PROVIDER=claude-cli`, harness `scripts/eval/eval-rule-activation.py`.
- Rule arm: scenario file with `rule_path`, scored on the `full` mechanism.
- Routed arm: same scenarios with `skill_path` and `reference_path`, scored on `description`.
- The routed arm used `--distractors 8`. The router saw the 8 skills whose descriptions overlap the target most.
- Routing at K above 0 has two steps. Step one picks a skill from the catalog alone.
- Only a pick of the target skill opens its router to choose a reference.
- Scenarios were split before any trigger text was written.
- Each rule's positive scenarios alternated into a tuning half and a held-out half.
- Every negative scenario went to the held-out half.
- The trigger author saw only rule text and the tuning half.
- A separate author wrote 44 new held-out scenarios, 4 per rule (3 positive, 1 negative).
- Scores below use only the 79 held-out scenarios.

## Gate

- Cut: routed positive score within 0.35 of the rule arm.
- 0.35 is the noise floor measured in the earlier diet eval.
- Negatives must not score worse when routed.
- Rules within 0.1 of the gate were re-scored with 3 judge samples per cell.

## Results

Scores are 1 to 5. `+` means positive scenarios, `-` means negative scenarios.

| Rule | Baseline + | Rule + | Routed + | Gap | Rule - | Routed - | Route hits | Judge samples | Verdict |
|---|---|---|---|---|---|---|---|---|---|
| push-lock | 2.42 | 4.83 | 4.83 | 0.00 | 3.17 | 5.00 | 4/4 | 3 (2026-11-25) | Cut |
| security | 1.67 | 5.00 | 5.00 | 0.00 | 3.17 | 5.00 | 4/4 | 3 (2026-11-25) | Cut |
| tool-use-hook-bar | 1.71 | 4.76 | 4.81 | -0.05 | 4.17 | 4.83 | 7/7 | 3 | Cut |
| python | 4.00 | 4.80 | 4.93 | -0.13 | 4.67 | 5.00 | 5/5 | 3 | Cut |
| retros | 2.60 | 5.00 | 4.93 | 0.07 | 4.00 | 5.00 | 5/5 | 3 | Cut |
| testing | 3.07 | 4.93 | 4.87 | 0.07 | 2.83 | 4.50 | 5/5 | 3 | Cut |
| plugin-self-containment | 2.00 | 4.83 | 4.22 | 0.61 | 4.33 | 5.00 | 4/6 | 1 | Keep |
| templates | 1.53 | 4.93 | 4.20 | 0.73 | 2.67 | 4.50 | 4/5 | 1 | Keep |
| adr-records | 1.33 | 5.00 | 3.92 | 1.08 | 3.83 | 3.50 | 3/4 | 1 | Keep |
| claude-agents | 2.00 | 4.93 | 3.73 | 1.20 | 4.44 | 5.00 | 2/5 | 1 | Keep |
| knowledge-persistence | 1.73 | 4.93 | 3.47 | 1.47 | 4.17 | 5.00 | 3/5 | 1 | Keep |

## Findings

- Six rules route as well as the loaded rule. They move into their skills.
- Routed negatives scored at or above the loaded rule for every cut rule.
- `adr-records`, a kept rule, fell on negatives from 3.83 to 3.50.
- A loaded rule often fires on tasks it does not cover. Routing avoids that.
- The five kept rules lose to overlapping skills, not to missing triggers.
- `ai-agents-generation-and-release` took cases from three of them.
- `memory-gate` took an `adr-records` case.
- `skillforge` drew misses for `claude-agents` and `plugin-self-containment`.

## Changes after the run

- The kept rules' references and trigger text were removed.
- `skillforge` now names only the per-call hook trigger.
- `tool-use-hook-bar` was re-scored on that final text: gap -0.05, 7 of 7 routes.
- The first pass at 1 judge sample put python, retros, and testing at 0.27, 0.27, and 0.33.
- Their 3-sample re-scores are the rows above.

## Limits

- Held-out sets are small: 6 to 9 scenarios per rule.
- push-lock and security first used 1 judge sample, with gaps of 0.00 and 0.17.
- On 2026-11-25 at d8d140bb2e, both were re-scored with 3 judge samples.
- d8d140bb2e no longer holds either rule file.
- The rule arm used the rule text from c77c9ba999^, restored for the run.
- The routed arm used the skill text at d8d140bb2e.
- Both 3-sample gaps are 0.00, and routed negatives scored 5.00 against 3.17.
- A distractor pick answers with no skill loaded. It scores the missed route, not the other skill.
- The distractor pick is lexical. Production routing sees about 120 skills, not 9.
- Global user instructions loaded in every arm, as in the earlier diet eval.
