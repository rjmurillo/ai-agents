# Skill: A PR closes only the issues GitHub parsed, not the ones you meant (95%)

## Statement

Writing `Fixes #N` in a PR body is a request. GitHub decides what it linked, and
it silently drops the rest. Read the decision back before you merge:

```bash
gh pr view <N> -R OWNER/REPO --json closingIssuesReferences \
  -q '[.closingIssuesReferences[].number] | sort | join(",")'
```

Compare that list element by element against the issues you intended to close.
Run it AFTER the body is final, because an edit after the check invalidates it.

## The two syntax traps

`Fixes #A #B #C` on one line links only `#A`. The keyword binds one reference,
so the trailing numbers render as plain issue links and close nothing. Each
issue needs its own line:

```markdown
Fixes #4405
Fixes #4415
Fixes #4416
```

`Refs #N` never closes anything. It reads like a weaker `Fixes` and is not on
the closing-keyword list at all. The closing keywords are `close`, `closes`,
`closed`, `fix`, `fixes`, `fixed`, `resolve`, `resolves`, `resolved`.

## Why this is worth a memory rather than a shrug

The failure is silent and it is invisible at exactly the moment you would catch
it. The PR merges, CI is green, the diff is correct, the work is genuinely on
`main`. Only the issue stays open. It then reappears in every "what is still
uncovered" query as though nothing shipped, so the same work gets scheduled
again. Nothing in CI, review, or the merge path reports it.

Measured 2026-08-03 across the 60 most recent merged PRs in this repo: 7 named
issues in the body that were absent from `closingIssuesReferences`. Three of
those were merged the same day.

| PR | Body claimed | API linked | Cause |
|---|---|---|---|
| #4467 | 4405, 4415, 4416 | 4405, 4415 | third number on a shared line |
| #4475 | 4345 | (none for 4345) | written as `Refs #4345` |
| #4471 | 4464 (in prose) | (none) | no closing keyword at all |
| #4478 | 4248 | (none) | no closing keyword at all |

## The verification failure underneath the syntax failure

The syntax rules are the cheap half. The expensive half is that I reported
"verified closing refs as 4405, 4415, 4416" for #4467 when the API said
`4405, 4415`. I had verified my own INTENT LIST, read it back to myself, and
called that an API result.

So the rule is not "remember the syntax." It is: the artifact you check must be
the one the other system produced, never the one you wrote. Same shape as
grading a push log before `PUSH_RC=` prints, or trusting a mutation harness that
never invoked the suite.

## Cleanup recipe when it has already happened

Audit merged PRs in bulk rather than one at a time:

```bash
gh pr list -R OWNER/REPO --state merged --limit 60 \
  --json number,title,body,closingIssuesReferences > ~/src/scratch/merged_audit.json
```

Then for each PR, extract every `#N` that appears on a line carrying a closing
keyword and subtract the `closingIssuesReferences` set. Expect false positives:
a `#N` in the body may be a PR number rather than an issue, and many candidates
will already be closed by some other route. Of the 7 hits above, only #4248 was
still genuinely open.

Before closing any survivor, verify the fix is actually on `main` with `git grep`
or `git show <sha>`. If it is not there, do NOT close the issue. An unlinked ref
plus a missing fix means the change was lost, which is a different and worse
problem than a bookkeeping miss.

## Anti-Pattern

Treating the PR body as the record of what will close. The body is the request.
`closingIssuesReferences` is the record.

## Related

- `github-skill/pr-creation-rules.md` (the surrounding PR construction rules)
- `pr-review/triage-003-confirming-supersession-by-main.md` (verifying a fix is
  genuinely on `main` before closing anything)
