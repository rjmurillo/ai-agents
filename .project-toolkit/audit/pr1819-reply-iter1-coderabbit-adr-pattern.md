Verified against `_ADR_PATTERN` in both:

- `.claude/hooks/PreToolUse/invoke_adr_review_guard.py:61`
- `src/copilot-cli/hooks/preToolUse/invoke_adr_review_guard__Bash_git_commit_442774.py:187`

The narrow `r"ADR-\d+\.md$"` regex does miss slugged filenames like
`ADR-006-thin-workflows-testable-modules.md`. That is a real bug, but
git blame confirms it predates this PR's base commit (`cd30f6a6`) and
the file was last modified on `main` long before REQ-003 work began.

This PR's diff scope (`cd30f6a6..HEAD`) only touches the bootstrap
section of `invoke_adr_review_guard.py`, not the ADR-detection regex.
Per the review-loop protocol, pre-existing findings outside the diff
scope are deferred.

Tracking issue should be filed against `main` for both source and
generated copies.
