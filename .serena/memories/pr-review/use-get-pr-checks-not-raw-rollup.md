# Read PR checks with the skill script, not with `gh pr view`

## The instinct that is wrong here

`gh pr view N --json statusCheckRollup` looks like the quick way to see whether
a PR's CI is green. It is quick, and on a small PR it is right. On this repo it
silently truncates, and the truncation is large enough to invert the answer.

Measured on PR #4003, 2026-08-02:

| Source | rows returned |
|---|---|
| `gh pr view --json statusCheckRollup` | 77 |
| REST `check-runs`, `total_count` | **133** |
| REST `check-runs`, `--paginate` | 133 rows, 103 distinct names |

The 56 runs the rollup dropped were not a random sample. They included the six
agent-review jobs and their aggregator, which is exactly the set that a naive
reduction then reports as "never ran".

## What it cost

Two consecutive false findings on the same PR, each confident and specific.
First: seven required contexts had never reported on four PRs. Second, after
switching to REST but passing `per_page=100` against a `total_count` of 133:
`Validate PR title` was missing. Both were artifacts. The paginated measurement
showed all 17 required contexts `completed/success`.

The wrong conclusions were then generalized to the backlog: 28 PRs reading
`BLOCKED` were classified as 24 genuinely red and 4 clean. When each was
actually offered to the merge endpoint, **24 merged on the first attempt** and
all 4 refusals were merge conflicts, not check failures. The classification was
inverted for 24 of 28 cases.

## The repo already had the right tool

`.claude/skills/github/scripts/pr/get_pr_checks.py` does this correctly and has
for some time:

- `contexts(first: 100)` with `totalCount` and `pageInfo { hasNextPage endCursor }`
  (lines 74 to 79)
- a second cursor query with `after: $cursor` (line 112)
- a real fetch loop that extends the node list and advances the cursor until
  `hasNextPage` is false (lines 321 to 325, entered at 385 to 393)
- a latest-per-name dedup that picks a winner per context (lines 274 to 282)

So the correct behavior, pagination plus latest-per-name reduction, was already
written, tested, and one command away. The failure was not a missing capability.
It was reaching past an existing tool for a raw `gh` call.

`AGENTS.md` states the rule this violates directly: **"Raw gh if skill exists"**
is in the Never list, and "Skill-First" is a section heading. That rule is
usually read as being about consistency. This is the other reason for it: the
skill encodes correctness the ad-hoc call does not.

## Use

```bash
uv run --frozen python .claude/skills/github/scripts/pr/get_pr_checks.py \
  --pr <N> --repo rjmurillo/ai-agents
```

Exit codes follow ADR-035: 0 all passing, 1 one or more failed, 2 PR not found,
3 API error, 7 timeout with `--wait`.

## The generalizable rule, stated carefully

Not "always paginate". The correct rule is narrower and survives contact with
real code:

> Either reconcile the rows you received against the count the API reports, or
> prove that truncation cannot change the classification you are about to make.

`scripts/validation/pr_commit_count.py` is the worked example of the second
branch and is **not** a defect. It fetches commits with `per_page=100` and does
not paginate, and its docstring says so, with the reason: the only decision it
makes is against `BLOCK_THRESHOLD = 20`, and a saturated count of 100 is far
above it, so no amount of additional pages can change the verdict. That is a
bounded reduction, correctly argued.

I nearly filed an issue against that file on a blanket "unpaginated call" scan.
Reading the docstring stopped it. A truncated read is only a defect where the
dropped rows could change the answer.

## Pagination is the least important of the three things a reader gets wrong

Measured 2026-08-03. Across one session I wrote three bespoke check readers.
Each one fixed the previous defect and introduced a new one.

| Attempt | What it fixed | What it broke |
|---|---|---|
| `gh pr view --json statusCheckRollup` reduced to a `{name: conclusion}` dict | nothing | two rows share one name, so the dict kept SKIPPED and dropped SUCCESS; reported a green required check as skipped |
| `gh api --paginate --jq` | truncation | `--jq` runs once per page, so the reduction saw a partial list |
| `--paginate --slurp` plus my own reducer | truncation and per-page reduction | counted `cancelled` as a hard failure; reported two clean PRs as FAILURE |

`get_pr_checks.py` already had all three properties before I started.

- It paginates.
- It groups rows by name and lets a passing re-run supersede a prior failure,
  the "OK if any SUCCESS exists" rule from the PR #1887 retrospective.
- Its severity map puts CANCELLED in the failing set so a CANCELLED-only group
  still surfaces, while a CANCELLED row with a sibling SUCCESS does not.

It also returns `IsRequired` per check plus `FailedRequiredChecks` and
`PendingRequiredChecks`. None of my three readers reported required status at
all, so none of them could answer the only question that decides a merge.

The order of danger is the reverse of the order of visibility. Truncation is
the defect you notice, because the row count looks wrong. Severity mapping and
re-run supersession are the ones that hand you a confident, complete-looking
answer with the sign flipped.

`cancelled` on its own means superseded or auto-cancelled by a newer run, not
broken. Treating it as a failure costs a re-run of a green suite at best, and a
false defect report against working CI at worst.

## Related

- `pr-review/mergestatestatus-blocked-can-be-stale.md`. The BLOCKED field is
  advisory; the merge endpoint is authoritative and safe to call. That memory
  carries the 24-of-28 result and the per-check reduction that should have been
  used here.
