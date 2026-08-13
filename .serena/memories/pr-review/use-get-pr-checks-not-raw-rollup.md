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

## The repo had the right pagination tool, not an authoritative reducer

`.claude/skills/github/scripts/pr/get_pr_checks.py` paginates the full rollup.
Its same-name reduction is not authoritative when independent state disagrees.

PR #4721 proved the boundary on 2026-08-11. At head
`cff4f397931579491f95a891472f2160be48e852`, the helper reported all passing,
zero failed required checks, and merge ready. GitHub reported
`mergeStateStatus: BLOCKED`. The required `Run Python Tests` context had two
runs on the same SHA: an earlier pull request run succeeded, then a later push
run failed. The helper grouped by display name and allowed the success to hide
the later failure.

First rule out conflicts, unresolved reviews, deployments, and other non-check
protection rules. If the remaining blocker is required-check-related:

1. Use `get_pr_checks.py` for pagination and the normal case.
2. Treat helper-green plus GitHub `BLOCKED` as a contradiction, not success.
3. Page the full rollup for the current head SHA.
4. Group by context identity and choose the latest timestamp.
5. Compare that result with the current ruleset's required context list.

Eureka: an existing wrapper can be safer than raw API access and still be the
wrong authority when its reduction policy discards event identity. Reuse the
wrapper first, then challenge its result when authoritative state contradicts
it.

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

## The second truncation is per-name, and pagination does not fix it

The row count is only half of it. Those 133 rows carried 103 distinct names, so
about 30 names appear more than once, and a reduction keyed on the name alone
silently keeps one row and discards its twin.

Two causes, both live in this repo:

1. **One workflow, several triggers.** `Run Python Tests` reported twice on one
   SHA, one row SKIPPED and one SUCCESS. Reducing to a `{name: conclusion}`
   dict kept the SKIPPED one. That produced a report of a failing required
   check on a PR whose `mergeStateStatus` was already `CLEAN`.
2. **Different workflows publishing the same check name.** Measured on
   `d7b9c8837`, 2026-08-04: `Aggregate Results` appears twice, from
   `AI PR Quality Gate` (run `30929337949`, failure) and from
   `Session Protocol Validation` (run `30929338237`, success). Nothing in the
   check name distinguishes them.

Case 2 is the worse one, because the two rows are not two attempts at the same
question. They are unrelated checks that happen to share a label, so "did
Aggregate Results pass" has no single answer.

Disambiguate with fields that are actually unique, not with the name:

```bash
# every row, with the workflow that owns it
gh api --paginate "repos/rjmurillo/ai-agents/commits/<sha>/check-runs?per_page=100" \
  --jq '.check_runs[] | "\(.conclusion)\t\(.started_at)\t\(.name)"'
# then resolve a specific row's owning workflow
gh api "repos/rjmurillo/ai-agents/actions/runs/<run_id>" --jq '.name'
```

`started_at` is the cheap tell. When rows sharing a name are minutes apart,
they are different workflows or different attempts, and you have to decide
which one your question is about before you read the conclusion.
## Pagination is the least important of the three things a reader gets wrong

Measured 2026-08-03. Across one session I wrote three bespoke check readers.
Each one fixed the previous defect and introduced a new one.

| Attempt | What it fixed | What it broke |
|---|---|---|
| `gh pr view --json statusCheckRollup` reduced to a `{name: conclusion}` dict | nothing | two rows share one name, so the dict kept SKIPPED and dropped SUCCESS; reported a green required check as skipped |
| `gh api --paginate --jq` | truncation | `--jq` runs once per page, so the reduction saw a partial list |
| `--paginate --slurp` plus my own reducer | truncation and per-page reduction | counted `cancelled` as a hard failure; reported two clean PRs as FAILURE |

`get_pr_checks.py` already handled pagination, severity mapping, and required
status. Its remaining gap was the same-name rule: any sibling success could
supersede a later failure from another trigger event. PR #4721 showed that this
can flip a required check from failing to passing.

The helper remains the first reader because it is better than an ad hoc rollup.
It is not the final reader when a required-check blocker contradicts its
verdict. Resolve that contradiction with latest-run-per-context evidence and
the current required-context list.

The order of danger is the reverse of the order of visibility. Truncation is
the defect you notice, because the row count looks wrong. Severity mapping and
re-run supersession are the ones that hand you a confident, complete-looking
answer with the sign flipped.

A cancelled row can be superseded by a later success only after both rows are
proved to represent the same logical context. A shared display name is not that
proof. Different workflows and trigger events reuse names in this repository.
A cancelled-only context still surfaces as a failure so it remains visible.

## Related

- `pr-review/mergestatestatus-blocked-can-be-stale.md`. The BLOCKED field is
  advisory; the merge endpoint is authoritative and safe to call. That memory
  carries the 24-of-28 result and the per-check reduction that should have been
  used here.
