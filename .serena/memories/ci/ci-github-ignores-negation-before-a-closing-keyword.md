# GitHub Ignores Negation Before a Closing Keyword

## The contradiction

Reading: "This PR does not close #N" states the PR leaves #N open.

GitHub scans the body for `close`, `fix`, or `resolve` (plus their `-s`, `-d`,
`-es`, `-ed` forms) followed by an issue number. It does not parse the words
before it. The sentence closes #N on merge. PR #7126 closed #5410 this way with
a criterion unmet, and nothing warned.

## What guards it now

`scripts/validation/pr_description.py` has `validate_negated_closing_keywords`.
It runs in `main()` beside `validate_closing_links` and reports a CRITICAL
`Negated closing keyword`. Fences, code spans, and HTML comments are skipped,
as GitHub does not scan them. A bare `Closes #N` stays valid.

Tests: `tests/test_pr_description_negated_closing.py`.

## Write it this way

- Mention without closing: `Refs #N`.
- Never put `close`, `fix`, or `resolve` next to `#N` in a sentence about what
  the PR does not do. Say "leaves #N open" or "Refs #N".

## Known limits

- `closing` is not a GitHub keyword, so "not closing #N" closes nothing and is
  not flagged.
- A second keyword joined by "or" or "nor" ("does not close #1 or fix #2") is
  not flagged for the second reference.
- The skill-side check `validate_pr_description.py` (run by `new_pr.py` during
  PR creation via `pr_validations.py`) only counts keywords. It does not look
  for negation.
