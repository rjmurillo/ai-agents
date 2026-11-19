# Doc date drift catch rate

This replay runs the current doc-date-drift gate on pinned pull revisions.
It uses the same pre-PR diff each author gets.
A match needs the same file, the same rule, and a line within three.
Either reported location can satisfy the line check.
Recall counts only automatic positives.
Any finding on a negative counts as a false positive.

Run it from the repository root:

```bash
uv run python scripts/eval/docs_review_doc_date_drift_replay.py
```

The receipt is `results/2026-11-19.json`.

## Score

caught 8 of 8 in-scope positives, 0 FP on 12 negatives, 2 manual with reasons

## Cases

| id | PR | scope | result |
|---|---|---|---|
| C3-01 | 7428 | automatic | Caught both subject-drift lines. Line 95 is a third year on the same source. |
| C3-02 | 6925 | automatic | Caught the header pair. The supplied head already fixes it, so replay uses an earlier revision. |
| C3-03 | 7027 | automatic | Caught the stale ADR frontmatter date. |
| C3-04 | 7136 | automatic | Caught the stale ADR frontmatter date. |
| C3-05 | 7196 | manual | Not flagged. Frontmatter date 2026-11-09 equals the commit day, and the diff adds no newer dated marker. |
| C3-06 | 7307 | automatic | Caught the stale ADR frontmatter date. |
| C3-07 | 7370 | automatic | Caught the stale ADR frontmatter date. |
| C3-08 | 7395 | automatic | Caught the stale ADR frontmatter date. Two nearby stale-as-of findings also fired. |
| C3-09 | 6978 | automatic | Caught the stale ADR frontmatter date. |
| C3-10 | 7092 | manual | The expected count claim stays manual. The count provenance and checklist date are 24 lines apart, outside the three-line as-of rule. The same revision also flags ADR-114. |
| N-7452 | 7452 | negative | No findings. |
| N-7431 | 7431 | negative | No findings. |
| N-7377 | 7377 | negative | No findings. |
| N-7412 | 7412 | negative | No findings. |
| N-7146 | 7146 | negative | No findings. |
| N-7415 | 7415 | negative | No findings. |
| N-7174 | 7174 | negative | No findings. |
| N-7313 | 7313 | negative | No findings. |
| N-7324 | 7324 | negative | No findings. |
| N-7446 | 7446 | negative | No findings. |
| N-7294 | 7294 | negative | No findings. |
| N-7253 | 7253 | negative | No findings. |

C3-11 lives in another repository. The unit tests cover a rechecked date left beside a bumped bullet.

## What stays manual and why

C3-05 stays manual. The frontmatter date equals the commit day, and the diff adds no newer dated marker. A same-day Decision edit has no date the rule can compare.

C3-10 stays manual. The dated count and its provenance sit 24 lines apart. The as-of rule only reads three lines. Widening that window would flag unrelated dates.
