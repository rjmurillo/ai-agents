# REQ-048 TASK-001 Label Rubric

Written 2026-11-02, before any candidate was labeled. Labels are fixed once given. A later rubric change starts a new labeling round.

## Who labels

Owner decision D17 (2026-11-02) replaces owner labeling with a separate judge model. AC-19 and SLI 2 name Richard Murillo as the labeler. D17 overrides that for this round. The judge is Claude Sonnet, not the Opus session that picks the weights. The judge sees only a redacted excerpt, this rubric, and no thresholds or scores.

## Label unit

### SLI 2 (consumer B, friction nudge)

The unit is one session. The judge reads the excerpt up to the Stop where the nudge would fire.

Question: "If the user saw a note here suggesting `/retrospective`, would a retrospective have been worth their time?"

| Label | Use when |
|-------|----------|
| `worth_it` | The excerpt shows real friction a retrospective could learn from. Examples: the same failure repeated with no new approach, edits that keep failing the same check, repeated permission denials the agent worked around, or a user correcting the agent more than once. |
| `not_worth_it` | The errors are routine and resolved quickly. Examples: an expected test failure during red-green work, one typo fixed on the next call, a probe that failed by design, or a polling loop. |
| `unclear` | The excerpt lacks the context to decide. |

### SLI 6 (consumer A, check-failures nudge)

The unit is one first-fire of `failure-repeat` or `edit-churn`. The judge reads the excerpt up to that event.

Question: "At this point, was the agent looping: repeating an approach that keeps failing the same way?"

Labels: `looping`, `not_looping`, `unclear`. Same evidence rules as above.

### DENIAL_MARKERS check

The unit is one errored result's first line.

Question: "Is this a permission or user denial?"

Labels: `denial` or `not_denial`.

### AC-40 miss rate

The unit is one successful shell command that AC-40 does not call a check.

Question: "Is this a verification run: a test, build, lint, or typecheck?"

Labels: `verification` or `other`.

## Scoring rules

- Precision counts `worth_it` (or `looping`) over all labeled units. An `unclear` counts as not worth it, so precision is conservative.
- The judge answers from the excerpt alone. The judge does not guess at events outside it.
- Each label carries a one-line reason of at most 25 words. Reasons stay in scratch, outside the repository, because they may quote transcript text.
