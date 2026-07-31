---
id: ADR-091
status: proposed
date: 2026-07-30
decision-makers: [rjmurillo]
supersedes: []
superseded-by: null
explainer: null
implemented: true
---

# ADR-091: Judge Verdict Recovery Bounds

## Status

Proposed. Implemented in the same change for issue #3988. The recovery path and its bound both ship in `scripts/eval/eval-rule-activation.py`.

## Date

2026-07-30

## Context

`scripts/eval/eval-rule-activation.py` scores model responses with an LLM judge that is told to answer with a JSON object holding three integers and one `reasoning` string. Some payloads do not parse. The judge quotes the response it is grading, an unescaped quote inside that prose invalidates the object, and the three numbers the eval actually needs sit before the damage.

The script recovers those numbers. Twenty-three rounds of adversarial review found sixteen defects of one class in that recovery: a search picking the wrong candidate object and reporting it as the judge's answer with `judge_failed` false. Each round fixed the instance. Issue #3988 argued the class is the problem and proposed deleting the path outright.

Two facts decided against deletion, and both were measured after the issue was filed.

The zero the deletion argument rested on is a serialization artifact. Issue #3988 reported 0 of 288 archived samples carrying a salvage marker and inferred that recovery had never moved a published number. `.claude/skills/context-optimizer/references/rule-audit-parser-forensics.md` retracts that inference: the artifacts store the state before recovery was applied, so the marker count says when the files were written, not what recovery did. Recovery moved one published cell. Round 16 recovered all 288 raw payloads from the Copilot CLI session transcripts and measured that 24 of 288 cells, 8.3%, would change if the run were re-scored today.

Deleting the path therefore drops 8.3% of samples for a benefit the measurement no longer supports. At three judge samples per cell, that takes 17 Opus cells down to one or two graded samples.

What issue #3988 was right about is that the decision has never been written down. There is no ADR. `judge_salvaged` was written at two sites and read at none, so option 3 of the issue, bounding the run on the marker, did not exist as code. And the round-9 residual is still live: an exemplar object at offset 0 followed by an explicit English refusal still grades 5/5/5.

## Decision

Keep the recovery path. Bound it, mark it, and record the residuals.

1. **Anchor at offset 0.** A payload's verdict is its leading object, ignoring leading whitespace. Position does not establish provenance, but it is cheap, auditable, and it replaced the search that produced every one of the sixteen defects.
2. **Refuse on a second named verdict.** Any payload naming a score field twice is refused rather than resolved. Picking one of two candidates is a guess.
3. **Unwrap a fence only when nothing but whitespace sits outside it.** One fence is not a selection.
4. **Mark every recovery.** A recovered sample carries `judge_salvaged: True`. The marker now survives `_reduce_score_samples` as `salvaged_sample_count` and reaches the run summary as `salvaged_sample_count`, `graded_sample_count`, and `salvaged_sample_fraction`.
5. **Bound the run on the marker.** `--max-salvaged-fraction` defaults to 0.15 and fails the run with exit code 1 when the observed fraction exceeds it. 0.15 sits above the 8.3% the reference run would salvage today, so that run still reproduces, and below the rate a provider that started wrapping verdicts in prose would produce. The rate is disclosed in the rendered report whenever recovery moved anything, so the exit code never contradicts a table that says nothing.
6. **Store the whole payload.** Every failed and every salvaged record keeps `judge_raw` and `judge_model` (issue #3975), so a recovery decision can be re-examined from the artifact instead of from a transcript that may not survive. All three salvage paths do this, not only the two inside `_salvaged_or_failed_judge`: the prefix recovery in `score_response` marked the sample and kept nothing, so the gate counted evidence it had discarded.

### Accepted residuals

Both are recorded rather than fixed, because the fix for each is a search, and the search is the defect class this ADR exists to bound.

- **Exemplar at offset 0 followed by a prose refusal.** `{"activation_score": 5, ...}\nI cannot score the response.` grades 5/5/5. Reproduced at HEAD. Distinguishing a quoted exemplar from an answer requires reading meaning out of a payload already known to be malformed. The refusal text is now retained under `judge_raw`, so the residual is auditable from the artifact even though it is not detected.
- **Adjacent string literals.** Pinned by `test_adjacent_string_literals_are_a_known_undetected_shape` in `tests/eval/test_eval_rule_activation.py`.

### The asymmetry this rests on

A refused sample costs one of three judge samples and is recorded as a failure, so it moves the median visibly through `judge_failed` and the graded sample count. A fabricated sample corrupts a published number and is recorded as a success. The bound above is calibrated to that asymmetry: recovery is allowed, but a run that leans on it more than its reference did fails rather than absorbing the change.

### Exit path

Provider-enforced structured output, a `response_format` or tool-call schema that makes the payload parseable by construction, is the durable answer. No such schema exists anywhere in `scripts/eval/` today, and the Copilot CLI path needs checking. That is out of scope here and belongs in its own issue.

## Rationale

The alternative considered and rejected was option 1 of issue #3988: delete the recovery path and require strict JSON. It is the simplest option and it eliminates the class rather than the instance. It was rejected because its supporting measurement was retracted in-repo before this decision was made, and the replacement measurement (24 of 288 cells would change) says deletion costs 8.3% of the sample pool.

Option 2, provider-enforced structured output, is the right long-term answer and is named above as the exit path. It is not available today without a provider change.

Option 3, bounding the run on the marker, is what this ADR adopts. It preserves samples, makes the reliance measurable rather than assumed, and turns a silent accommodation into a failed run.

## Consequences

Positive:

- A run that starts depending on recovery fails loudly instead of publishing numbers that rest on it.
- `judge_raw` makes every recovery decision re-examinable from the artifact.
- The decision stops being re-litigated implicitly. Round 24 starts here.

Negative:

- The bound can fail a run that a provider hiccup pushed over 15%. The flag is the escape hatch and the failure names the observed fraction, so the operator can decide.
- The two residuals above are live. A payload of either shape still publishes a score the judge did not give.
- The emitted artifact grows by the raw payload on every failed and salvaged sample. Bounded by the judge call's `max_tokens`, and failures are rare (24 of 288 in the reference run).

## Impact on Dependent Components

- `scripts/eval/eval-rule-activation.py`: owns all of it.
- `scripts/eval/_optimizer_adapters.py` and `scripts/eval/optimize-artifact.py` read `score_samples` by key and never enumerate keys, so the additive fields pass through.
- Archived artifacts predate `salvaged_sample_count`. Every reader defaults it rather than requiring it, so the archive replay in `tests/eval/test_eval_rule_activation.py` stays green.

## Rollback and Kill Criteria

Set `--max-salvaged-fraction 1.0` to disable the bound without reverting anything. Roll the ADR back if provider-enforced structured output lands, at which point recovery becomes dead code and deletion is free.

## Related Decisions

- Issue #3988: the argument this ADR settles.
- Issue #3975: full payload retention and model identity on the sample record.
- Issue #4031: the record builder is now named `_salvaged_or_failed_judge` for both branches it produces.
- Issue #3999: the two recovery entry points that disagreed in strictness. Closed.

## References

- `.claude/skills/context-optimizer/references/rule-audit-parser-forensics.md`: rounds 1 through 23 and the retraction of the zero-marker inference.
- `.agents/analysis/eval-artifacts/2026-07-29-unified-software-engineering/recovered-judge-payloads.json`: the 288 raw payloads.
