---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-21-session-5209-14a6f1844-adr-review-fixes-stacked.json
qaCommit: b386b27cadbda6ee539b5e212beaad4c0d4eb88f
---

# QA: PR #5209 review-round fixes, carried on a stacked branch

**Branch**: `claude/adr-5209-review-fixes`
**Base**: `claude/adr-evaluation-tooling-6od8rd` (PR #5209)
**Validated at commit**: `b386b27cadbda6ee539b5e212beaad4c0d4eb88f`

## Verdict

PASS. The campaign evidence lives in
`.agents/qa/2026-08-21-adr-corpus-campaign-qa.md`, whose addenda 5 and 6 carry
the findings and measurements for these commits. This report covers only what is
specific to the stack: why it exists, and that it clears its gates honestly.

## Why this branch exists

PR #5209 sits at 47 commits against a 40 ceiling. The owner applied
`commit-limit-bypass`, which is the sanctioned escape and which CI honours. The
pre-push hook cannot see it: `check_pr_bypass_label.py` shells out to `gh`, and
`gh` has no GitHub access in this session.

```
$ gh pr view <branch> --repo rjmurillo/ai-agents --json labels
HTTP 403: This GraphQL query is not enabled for this session

$ gh api "repos/rjmurillo/ai-agents/pulls?head=..." --jq '.[].labels[].name'
HTTP 403: GitHub access is not enabled for this session
```

Both transports refused, so the checker fails closed on every label, which is
its documented contract. The `needs-split` allowance calls the same checker and
caps at 5 new commits against these 9, so it does not apply either.

**No hook was bypassed.** `--no-verify`, `LEFTHOOK=0`, `LEFTHOOK_BIN`, a
lefthook config override, a hook edit and `LEFTHOOK_EXCLUDE` were all unused, on
both branches, per `universal.md` MUST-NOT-2.

## The stack clears the ceiling by rule, not by exception

Stacking is a path the gate itself implements. `_unpushed_commit_count`
excludes commits another pushed branch already carries (issue #3610, whose
docstring names the stacked-branch deadlock this avoids), so this push counts 9
rather than 47:

```
NOTE: push has 47 commits from origin/main, but only 9 are not already
      carried by another pushed branch; limit is 40.
```

That is the gate passing on its own terms. Worth stating plainly because a
reader seeing a second branch appear next to an over-limit PR should be able to
tell an end-run from a sanctioned route.

## Two gates that then blocked, and were satisfied rather than worked around

1. **branch-context-policy.** The session log named the branch this one is
   stacked off. Fixed by writing a log for the branch actually being pushed,
   not by editing the other branch's log to point here.
2. **Session End Validation**, twice. First that `startingCommitNoted` cited the
   campaign's starting commit while `session.startingCommit` read `14a6f1844`;
   the difference is real and intended, since this branch starts where the
   pushed work ends. Then that two session logs cannot share one QA report,
   which is why this file exists.

Each was a defect in what I wrote, found by a gate, and fixed at the cause.

## What is deliberately NOT claimed here

This report does not re-attest the campaign's test evidence; the campaign report
owns that and was re-verified at each of these commits. It also does not claim
CI is green on this branch: at the time of writing the branch has just been
pushed and its first run has not completed.

## Verification

```
pre_pr.py                    58 of 59 passed at the previous attempt; the one
                             failure was this file's absence, now fixed
check_adr_lifecycle          99 passed
generate_adr_index           60 passed
detect_adr_changes           56 passed across four trees
ADR-063 structural           26 passed
commit-count gate            PASSED via the stacked-branch rule
```
