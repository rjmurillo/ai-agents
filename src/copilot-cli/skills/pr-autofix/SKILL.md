---
name: pr-autofix
description: Autonomous PR monitor and fixer per docs/autonomous-pr-monitor.md. Triages open PRs by tier, addresses thread feedback, fixes CI failures, and enables auto-merge when the 4-condition Ready-to-Merge gate passes.
allowed-tools: Bash, Read, Edit, Write, Skill
user-invocable: true
---

# /pr-autofix

Autonomous PR monitor and fixer. Implements the protocol from
`docs/autonomous-pr-monitor.md`.

## Triggers

| Trigger phrase | Operation |
|----------------|-----------|
| `pr-autofix` | Triage all open PRs by tier and act |
| `autofix this pr` | Single-PR mode on the current branch's open PR |
| `monitor open prs` | Periodic triage without merging |
| `auto-merge ready prs` | Tier 1 only: enable auto-merge on land-ready PRs |
| `address pr feedback` | Tier 3/4 only: walk thread lifecycle |

## Process

Three phases. Tier-based dispatch decides which actions apply per PR.

### Phase 1: Triage

Run `test_pr_merge_ready.py` for every open PR. Classify each into a tier (T1-T5) using the table below. Sort the queue by tier ascending.

### Phase 2: Act per tier

Walk the queue. For each PR, apply the tier's action set. T1 first (land-ready), then T2 (CI fix), then T3/T4 (threads), then T5 (bot).

**Per-PR live-state gate (BLOCKING, issue #2455).** Before any action runs on a PR (any tier: arming auto-merge, pushing a CI fix, posting a thread reply), call `check_pr_live_state.py` and branch on the JSON envelope `Data.action` field. The session-start triage snapshot is stale by the time the walk reaches each row in a repo with heavy merge automation, and the consequences of acting on a stale row are concrete: armed auto-merge on a redundant PR, conflict merges into a closed branch, duplicate logic landed twice.

```bash
# One outer fetch covers all per-PR calls; --skip-fetch keeps the loop cheap.
git fetch --quiet origin main

# Per PR, immediately before any per-tier action:
LIVE=$(python3 .claude/skills/github/scripts/pr/check_pr_live_state.py \
    --pull-request "$PR" --skip-fetch --output-format json)
ACTION=$(echo "$LIVE" | jq -r '.Data.action')
if [ "$ACTION" = "SKIP" ]; then
    REASON=$(echo "$LIVE" | jq -r '.Data.reason')
    echo "Skipping #$PR: $REASON"
    # If Data.superseded_by_base.fully_superseded == true, recommend close
    # via the queue's close-handling path; do NOT push or merge.
    continue
fi
# ACTION == "ACT": proceed with the tier's planned action set.
```

SKIP verdicts are binding: do NOT push commits, do NOT arm auto-merge, do NOT run `merge_pr.py` on a PR this gate classifies as SKIP. The verdict's `reason` field names the cause (merged, closed, draft, fully superseded by base) for the autofix log. An ACT verdict only proves the PR is still actionable; the four-condition Ready-to-Merge gate still applies before any merge.

### Phase 3: Verify and gate

After all queued actions, re-check the 4-condition Ready-to-Merge gate. Enable auto-merge only when all four conditions hold.

## Workflow

1. Triage all open PRs into tiers T1-T5 using `test_pr_merge_ready.py`.
2. Process T1 (land-ready) first, then T2 (CI fix), T3/T4 (threads), T5 (bot).
3. **Before acting on any PR, call `check_pr_live_state.py`** and skip the row when it returns `Data.action=SKIP` (issue #2455). The triage snapshot from step 1 goes stale fast in a repo with heavy merge automation; the gate catches PRs merged/closed mid-walk and PRs whose diff is already on `main` via a sibling consolidated PR.
4. For each PR that the live-state gate cleared: address review threads, fix CI failures using known patterns, then choose the merge path from the four-condition gate.

## Ready-to-Merge Definition (4 conditions, ALL required)

1. Branch up to date with `main` (`mergeStateStatus` not `BEHIND`).
2. All required checks pass.
3. All conversations addressed: READ, TRIAGED, SOLVED (if Blocking), REPLIED with course of action, RESOLVED.
4. `mergeStateStatus == CLEAN` (or `UNSTABLE` with documented non-required failures).

`CanMerge=True` from `test_pr_merge_ready.py` alone is insufficient. Cross-check all four conditions.

## Tier Definitions

| Tier | Criteria | Action |
|------|----------|--------|
| T1 | Branch up to date, no CI failures, no threads, `CLEAN` | Use the CLEAN merge path after the four-condition gate |
| T2 | CI failures only, branch up to date | Fix CI, verify required checks pass |
| T3 | Threads only (CI passing) | Walk full thread lifecycle, then merge |
| T4 | Both CI failures + threads | Fix CI first, then lifecycle threads |
| T5 | Bot PR with validation failures | Handle individually |

If `BEHIND`, update branch against main BEFORE other actions (see doc Branch Update section).

## Fix Patterns

- **PR description mismatch**: Remove file references not in the diff (use GitHub API to PATCH body).
- **Branch behind main**: Worktree + `git merge origin/main --no-edit` + push (no force needed).
- **Stale merge-state cache**: `test_pr_merge_ready.py` sets `StaleDirtySuspected=true` when GitHub reports `mergeable == "CONFLICTING"` or `mergeStateStatus == "DIRTY"`. This is advisory, not authoritative. Verify against local git FIRST: in a worktree, `git fetch origin "$BASE"`, then `git merge-base --is-ancestor "origin/$BASE" HEAD` (exit 0 = ancestor) AND a `git merge --no-commit --no-ff "origin/$BASE"` trial merge that stays clean. Both clean means the conflict is stale: run a safe base-ref refresh (`git merge origin/"$BASE" --no-edit` + push, no force) after the Force-Push Safety SHA audit, then re-run the completion gate. A failing trial merge means the conflict is real: resolve via merge-resolver. Evidence required: the ancestry exit code and trial-merge result. See doc Stale merge-state cache section (issue #2368).
- **Stale CI check**: Push fresh commit to re-trigger; avoid `--no-verify` if possible.
- **Bot review threads**: Read, triage per Thread Severity, reply with disposition, resolve via `add_pr_review_thread_reply.py --resolve`.
- **Session validation failure**: Use session-log-fixer skill.

## Force-Push Safety

Before any push: verify `git rev-parse "refs/heads/$BRANCH"` matches the PR's expected `head.sha` from `get_pr_context.py`. (Prefer `rev-parse` over plain-file reads of `.git/refs/heads/<branch>`: rev-parse resolves loose refs AND refs that have been compacted into `.git/packed-refs`; a plain-file read returns "missing ref" when the branch lives only in `packed-refs`.) If the local ref points to a bootstrap/sandbox commit, STOP. Investigate corruption before pushing. Force-push only with explicit user authorization, using SHA-pinned source with quoted refspec:

```bash
SHA="<known-good-sha>"
BRANCH="<branch-name>"
git push origin "${SHA}:refs/heads/${BRANCH}" --force-with-lease --no-verify
```

Quote every variable expansion. The shell does not treat `:` specially in a refspec; the real reason to quote is that branch names can contain characters the shell DOES treat specially (`*`, `?`, `[`, whitespace), and unquoted `$BRANCH` will word-split or glob on those.

## Scripts

```bash
# Check merge readiness
python3 .claude/skills/github/scripts/pr/test_pr_merge_ready.py --pull-request {pr}

# Per-PR live-state gate (BLOCKING per Phase 2; issue #2455). Returns
# exit 0 + Data.action=ACT when safe to proceed, exit 1 + Data.action=SKIP when
# the PR is merged/closed/draft or fully superseded by base.
python3 .claude/skills/github/scripts/pr/check_pr_live_state.py --pull-request {pr} --skip-fetch --output-format json

# Get CI check logs
python3 .claude/skills/github/scripts/pr/get_pr_checks.py --pull-request {pr} | \
  python3 .claude/skills/github/scripts/pr/get_pr_check_logs.py --pull-request {pr} --checks-input -

# CLEAN path: try auto-merge only when there is pending branch-protection work to wait on.
# If GitHub rejects an already-CLEAN PR with "clean status", use the printed direct-merge fallback.
python3 .claude/skills/github/scripts/pr/set_pr_auto_merge.py --pull-request {pr} --enable --merge-method SQUASH

# Direct merge: already-CLEAN fallback or UNSTABLE state with documented non-required failures.
python3 .claude/skills/github/scripts/pr/merge_pr.py --pull-request {pr} --strategy squash
```

### Merge path by `mergeStateStatus`

GitHub refuses auto-merge for `UNSTABLE` PRs (issue #2439) and may also reject an already-`CLEAN` PR because there is nothing left to wait on (issue #2450). Pick the path that matches the state:

| `mergeStateStatus` | Path | Script |
|---|---|---|
| `CLEAN` | Auto-merge when waiting is useful; direct merge if GitHub returns the already-clean rejection | `set_pr_auto_merge.py --enable`, then `merge_pr.py --strategy squash` fallback |
| `UNSTABLE` with documented non-required failures | Direct merge (immediate) | `merge_pr.py --strategy squash` |
| `BEHIND` | Update branch first, then re-classify | `git merge origin/main --no-edit` + push |
| `DIRTY`/`CONFLICTING` | See Stale merge-state cache pattern below | merge-resolver if real conflict |

`set_pr_auto_merge.py` detects the `UNSTABLE` and already-`CLEAN` rejections from GitHub's GraphQL API and emits the direct-merge fallback command in its error output (exit 3) so the operator never has to translate the generic "GraphQL request failed" message themselves.

### Merge-check exit codes: `test_pr_merged.py`

As of issue #2308, `test_pr_merged.py` exits **0** on any successful query
and reports merge state in the JSON `merged` field. This makes the script
behave like every other shell-friendly probe: exit 0 means "I answered your
question". Branch on the JSON, not the exit code.

Earlier history: the script used to exit **100** when the PR was merged
(Skill-PR-Review-007). Treating 100 as a failure caused wasted polling loops
on PRs #2240, #2269 (#2277), and made successful merge verification look
failed on PR #2289 (#2308).

When invoking from autofix code:

```bash
PR_NUMBER="123"
python3 .claude/skills/github/scripts/pr/test_pr_merged.py --pull-request "$PR_NUMBER" | jq -e '.merged == true'
```

To restore the legacy skip-review sentinel (only for callers that already
encoded "100 = merged"):

```bash
PR_NUMBER="123"
python3 .claude/skills/github/scripts/pr/test_pr_merged.py --pull-request "$PR_NUMBER" --exit-100-on-merged
```

The legacy `--exit-zero-on-merged` flag (from #2277) still parses as a no-op
for backward compatibility.

## Completion Gate

Run after all threads resolved and CI passes:

```bash
python3 .claude/skills/github/scripts/pr/run_completion_gate.py \
  --config .claude/commands/pr-review-config.yaml \
  --pull-request {pr} --json
```

## Verification

Per PR processed:

- [ ] Tier classification recorded (T1-T5).
- [ ] Per-PR live-state gate ran immediately before the tier's action (issue #2455): `check_pr_live_state.py --pull-request $PR --skip-fetch --output-format json`. Verdict `Data.action=ACT` recorded; `Data.action=SKIP` aborted the action and recorded the reason (merged, closed, draft, or fully superseded by base).
- [ ] All required CI checks pass (T2/T4 only).
- [ ] Every review thread is READ, TRIAGED, SOLVED (if Blocking), REPLIED with course of action, and RESOLVED (T3/T4 only).
- [ ] `mergeStateStatus` is `CLEAN` (or `UNSTABLE` with documented non-required failures).
- [ ] Branch is up to date with `main` (`mergeStateStatus` not `BEHIND`).
- [ ] Force-push safety check ran before any push: `git rev-parse "refs/heads/$BRANCH"` matched the PR's expected `head.sha`.
- [ ] Correct merge path chosen by state: `set_pr_auto_merge.py --enable` for `CLEAN`, `merge_pr.py --strategy squash` for `UNSTABLE` with documented non-required failures (see "Merge path by `mergeStateStatus`" table; issue #2439).
- [ ] All four Ready-to-Merge conditions hold before the merge command runs (CanMerge=True is insufficient alone).
