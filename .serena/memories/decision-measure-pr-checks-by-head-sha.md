# Decision: read PR check status by head SHA, never from `gh pr checks`

## Question

How do you find out whether a pull request is actually failing CI?

## Conventional answer

`gh pr checks <number>`. It is the purpose-built subcommand, it prints a clean
table of check names and conclusions, and it exits non-zero when something failed.

## First-principles position

It reports check runs from superseded commits as current failures. The output is
a view over every check run associated with the pull request, not over the check
runs of the commit that is actually up for merge. Push a fix and the old failing
run stays in the table beside the new passing one.

The question you care about is a property of a commit, not of a pull request, so
ask it of the commit.

## Evidence

Measured 2026-08-02 on PR #4233.

```
$ gh pr checks 4233
Validate Spec Coverage   fail   2m4s   https://github.com/.../runs/...
```

The same check, queried against the pull request's real head SHA:

```
$ gh pr view 4233 --json headRefOid -q .headRefOid
ccdf4d371d...
$ gh api "repos/rjmurillo/ai-agents/commits/ccdf4d371d.../check-runs?per_page=100" --paginate \
    --jq '.check_runs[] | select(.name=="Validate Spec Coverage") | .conclusion'
success
```

The failing run had judged an older revision of the PR body. Re-measuring all 16
mergeable PRs this way changed the assessment of several of them, and this
subcommand alone sent me chasing two failures that did not exist.

Same class as issue #3978, which records GraphQL `statusCheckRollup` retaining
superseded runs. Two surfaces, one root cause: check runs are retained per pull
request, and neither surface filters to the head commit.

## Decision

Resolve the head SHA first, then read that commit's check runs:

```bash
PR=4233
SHA=$(gh pr view "$PR" --json headRefOid -q .headRefOid)
gh api "repos/rjmurillo/ai-agents/commits/$SHA/check-runs?per_page=100" --paginate \
  --jq '.check_runs[] | select(.conclusion=="failure") | .name'
```

Empty output means nothing is failing on the commit under consideration. Check for
`.status=="in_progress"` separately; a run that has not finished is not a pass.

This applies to any automation that gates on CI state, and to every manual triage
of a red pull request. Treat a `gh pr checks` failure as a hypothesis to confirm
against the head SHA, never as a finding.
