# A QA Report May Be Named For A Linked Issue, Not Only For The PR

**Category**: CI Infrastructure
**Source**: Issue #5096, session 14713, 2026-08-15. Contract read from
`scripts/ci/check_pr_qa_report.py` at branch
`fix/issue-5096-qa-report-issue-fallback`.

## The old cost this removes

`Check QA Report Exists` (step 8 of `Validate PR`, see
`ci-validate-pr-is-many-gates-only-some-read-the-body`) used to resolve a report
by one glob:

```python
artifact_dir("qa", base=Path.cwd()).glob(f"*pr-{pr_number}*.md")
```

A PR number does not exist until the PR is opened. So the first push of every
code PR could not satisfy the gate, and clearing it cost a rename commit plus a
second full push cycle at 10 to 20 minutes of pre-push hooks. Session log
`.agents/sessions/2026-08-14-session-14707-4940-model-pin-doc-examples.json`
records that trip verbatim: "Renamed the QA report to carry the PR number".

## The contract now

Resolution order, in `_resolve_qa_report`:

1. `.agents/qa/*pr-{pr_number}*.md`, first match in sorted order. Still
   preferred, so an existing PR-named report keeps winning and no PR-numbered
   report is ever bypassed.
2. Otherwise, fetch the PR body (`gh api repos/{repo}/pulls/{n} --jq .body`),
   extract issue numbers with

   ```text
   (?i)\b(?:close[sd]?|fixe?[sd]?|fix|resolve[sd]?|refs?)\s+#(\d+)
   ```

   and try them **tiered, not numeric**: every closing keyword (`Closes`,
   `Fixes`, `Resolves`) before any bare `Refs`, body-appearance order within
   each tier, deduplicated across both (`check_pr_qa_report.py:_linked_issues`,
   `_CLOSING_KEYWORD` and `LINKED_ISSUE`). For each candidate issue number, in
   that order, glob `.agents/qa/*issue-{n}*.md` and skip any match whose
   filename carries a `pr-<digits>` token for a *different* PR
   (`PR_TOKEN`, `_find_issue_qa_report`): that report belongs to another pull
   request, and resolving it here would validate this PR against another
   PR's QA evidence and ancestry.

   Numeric order was the original design and is wrong: a PR that fixes one
   issue and also refs an older, lower-numbered one would try the referenced
   issue first. Measured live on PR #5107 (this issue, #5096): its body carried
   both `Refs #5074` and `Fixes #5096`, numeric order tried `#5074` first, and
   that matched `pr-5087-issue-5074-merge-resolver-rename-rule.md`, a report
   PR #5087 left on `main` after its squash merge. That report's `qaCommit` was
   a branch commit unreachable from `main`, so the ancestry check failed a PR
   whose own report was valid. The `PR_TOKEN` filter and the closing-keyword
   tiering both come from that failure, not from the original design.

Three consequences worth knowing before you name a file.

**Name the report for the issue and skip the rename.** `issue-5096-<slug>.md`
satisfies the gate on the very first push. There is no reason to name a new
report for a PR that does not exist yet.

**A bare `#123` is not a link.** Only the keyword forms resolve, so a passing
mention of another issue in the body cannot pull in that issue's QA report.
The body must carry a real `Fixes #N` or `Refs #N`, which
`.claude/rules/universal.md` MUST 2 requires anyway.

**A failed body fetch is EXTERNAL_ERROR (exit 3), not "no report" (exit 1).**
Same distinction `_changed_files` draws for a broken `gh api`. A red step at
exit 3 means the API broke, so do not go hunting for a missing file.

Everything downstream is unchanged: whichever report resolves goes through
`_validate_report`, so the `qaSessionLog` binding, the `qaCommit` equals
`endingCommit` rule, and the post-QA staleness walk all still apply. Naming the
file for the issue buys you nothing on those.

## Known sharp edge

Both globs match on a numeric prefix, so `*issue-5096*.md` would also match a
hypothetical `issue-50960-...md`. The PR-numbered glob has carried the same
weakness since it was written. Do not read the issue fallback as the newer or
looser of the two.

The `PR_TOKEN` filter only rejects a filename token for a *different* PR
number; a report that happens to name this PR (`issue-5096-pr-42-qa.md` when
the gate runs as PR 42) is still accepted. It is not a "no PR token allowed"
rule, only a "not somebody else's" rule.

## Related

- `ci-validate-pr-is-many-gates-only-some-read-the-body`. Where this step sits
  in the 25-step job, and why a red `Validate PR` is usually something else.
- `git-rebase-after-push-costs-two-cycles`. The other way a published branch
  buys a second 17-minute push.
