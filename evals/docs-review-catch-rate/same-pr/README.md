# Same-PR doc claim replay

This replay runs `doc_accuracy.py --same-pr` on historical pull requests.
It scores prose that drifted from code in the same diff.
The runner is `scripts/eval/docs_review_same_pr_replay.py`.
It touches only this directory.

## Method

Each case fetches `origin pull/<N>/head` and checks out that SHA.
The base is the merge-base of that SHA and the PR `baseRefOid`.
A hit matches the file, the defect class, and the line within 3.
Checklist rows are not findings.
A positive may be `scope: manual` only with a one-line `why`.
The run deletes its worktrees and temporary refs.

## Score

caught 7 of 7 in-scope positives, 0 FP on 12 negatives, 8 manual with reasons.

The corpus has 14 positive cases.
Seven are automatic, and every one was caught.
Seven cases are manual.
C4-02 also has one manual claim, which makes eight manual reasons.
The 12 negatives produced 0 findings.

Manual reasons:

- C4-02: Record cardinality requires distinguishing one admitted regression from multiple built-in admission records.
- C4-05: The count names an allowlist without its symbol; review SECTIONS_TO_COMPARE in the named detector.
- C4-08: Behavioral equivalence needs a reviewer to compare exception handling.
- C4-09: Run counts depend on nested calls and require behavioral review.
- C4-10: The contradiction sits in unchanged review rules outside this diff.
- C4-11: The preflight behavior needs review of an unchanged prose reference.
- C4-12: The deleted scan heading needs a reviewer to assess remaining references.
- C4-14: The legal-only routing claim requires classifier behavior review.

Receipt: `results/2026-11-19.json`.
`same_pr.py` gained a list annotation after this replay.
That edit does not change the rules.
