# Retrospective: Trunk and CI Cancellation Incident

## Session Info
- **Date**: 2026-08-09
- **Agents**: Copilot CLI, specialized review agents
- **Task Type**: Bug
- **Outcome**: Failure

## Phase 0: Data Gathering

### 4-Step Debrief

**Observe:** A Trunk Merge Queue trial created 18 draft PRs, 695 workflow runs
in one measured window, and zero merges. After abandoning Trunk, 41 behind PR
branches were updated in parallel and auto-merge was enabled on all of them.
That triggered 820 queued or in-progress workflow runs. In a panic response,
818 runs were cancelled.

**Respond:** Auto-merge was disabled on 41 PRs, strict policy flipped several
times, and PRs were closed/reopened or given empty commits to regenerate
required contexts. Those recovery actions created more CI churn and left
several PRs showing missing, cancelled, or pending required checks.

**Analyze:** The cancellation treated workflow runs as disposable jobs. For a
required check, the run is also the only producer of the status context. A
cancelled run cannot be replaced by waiting. Some workflows omit `reopened`,
so close/reopen was not a complete recovery event. Updating every branch before
the first merge also guaranteed that most of the resulting CI work would be
invalidated.

**Apply:** Keep strict freshness enabled for safety. Update and test one front
PR at a time. Never bulk-cancel required runs without a per-PR regeneration
plan. Read asynchronous push completion output before reporting remote state.

### Execution Trace

1. Enabled Trunk and disabled strict freshness.
2. Observed zero merges and high draft/CI volume.
3. Removed Trunk and restored strict.
4. Updated 41 PR branches in parallel and enabled auto-merge.
5. Realized the first merge would invalidate the other 40 matrices.
6. Cancelled 818 runs without first mapping each required context to a recovery
   event.
7. PRs showed cancelled and permanently missing checks.
8. Close/reopen failed to regenerate workflows whose explicit type list omitted
   `reopened`.
9. Empty synchronize commits were needed to regenerate complete check sets.
10. Restored strict and adopted one-front serial landing.

### Outcome Classification

| Mad | Sad | Glad |
|-----|-----|------|
| 818 runs cancelled without recovery mapping | Four hours lost and repository progress stalled | Strict policy, no-Trunk decision, and one-front workflow are now explicit |
| Repeated remote loops for failures encoded locally | User had to discover stuck PRs and incorrect claims | Review agents caught duplicate ratchets and stale policy claims |
| Reported pushes as in-flight after they had failed | CI and AI review cost increased | Exact incident counts and recovery constraints are preserved |

### Failure Mode Classification

- **Primary**: FM-9, Confident-Incorrectness Recurrence. Bulk state changes
  were made from an unverified cost model, and push/run state was reported
  before terminal outputs were read.
- **Secondary**: FM-4, False Completion Markers. Auto-merge enabled and push
  started were treated as progress terminal states while PRs remained blocked.
- **Related**: FM-3, Ambiguous Instruction Inversion. "Stop the bleeding" was
  interpreted as cancel all work rather than preserve required-check recovery.

### Impact

| Area | Severity | Evidence |
|------|----------|----------|
| GitHub Actions cost | High | 820 runs triggered; 818 cancellation requests |
| PR recoverability | High | Required contexts missing after cancellation |
| Developer time | High | Four-hour incident and repeated 15-minute remote loops |
| Repository progress | High | PR backlog stalled while checks were regenerated |
| Data integrity | Medium | Episode metric recorded 44 paths instead of 10 |

### Evidence Links

- [Issue #4815](https://github.com/rjmurillo/ai-agents/issues/4815):
  Trunk trial root cause and zero-merge result.
- [PR #4814](https://github.com/rjmurillo/ai-agents/pull/4814):
  abandoned queue compatibility changes.
- [Issue #4827](https://github.com/rjmurillo/ai-agents/issues/4827):
  active workflows omit `reopened`.
- [Issue #4835](https://github.com/rjmurillo/ai-agents/issues/4835):
  required-context cancellation guard.
- [PR #4792](https://github.com/rjmurillo/ai-agents/pull/4792):
  stale strict/Trunk guidance and session metric defects.

## Phase 1: Insights Generated

### Five Whys

1. **Why were PRs waiting on checks that would never run?** Required workflow
   runs were cancelled.
2. **Why were they cancelled?** The response to a CI-cost spike was to stop all
   non-front runs immediately.
3. **Why was there a CI-cost spike?** Forty-one branches were updated before
   selecting a single front PR.
4. **Why were all branches updated?** Auto-merge enablement was treated as a
   bulk operation without modeling strict freshness invalidation.
5. **Why did the mistake persist?** No pre-action artifact stated the cost
   model, recovery event, or terminal condition, and asynchronous push results
   were not read before status claims.

Root cause: state-changing GitHub operations were executed in bulk before a
cost model and recovery contract existed.

### Fishbone Analysis

| Category | Contributing factor |
|----------|---------------------|
| Decision | Panic response optimized visible queue length instead of total CI work |
| Tooling | Bulk API calls made destructive state changes cheap |
| Workflow | Required status contexts depend on events; cancellation removes the producer |
| Verification | No dry-run list of affected runs, PRs, or recovery events |
| Concurrency | Parallel branch updates created hundreds of duplicate matrices |
| Communication | Progress claims preceded reading push completion and CI outputs |
| Policy | Strict and merge workflow changed repeatedly before documentation converged |

### Patterns and Shifts

- Repeated pattern: act on a familiar symptom before verifying the live cause.
- Repeated pattern: remote CI used as first execution of known local prompts.
- Shift required: state-changing bulk actions need a written blast-radius and
  rollback table before execution.
- Shift required: task completion means merged or explicitly handed off, not
  auto-merge enabled or push started.

### Learning Matrix

| Keep | Drop | Add | Modify |
|------|------|-----|--------|
| Independent review and negative controls | Bulk branch refresh | One-front invariant | Auto-merge protocol |
| Live GitHub API verification | Panic cancellation | Required-context recovery map | Push status reporting |
| Strict freshness | Unread async results | Post-merge main health gate | Local prompt execution |

## Phase 2: Diagnosis

### Successes (Tag: helpful)
| Strategy | Evidence | Impact | Atomicity |
|----------|----------|--------|-----------|
| Independent adversarial review | Found duplicate ratchets and invalid queue checks before merge | 8 | 88% |
| Negative controls | New tests turned red when guards were removed | 8 | 92% |
| Live ruleset and PR queries | Corrected false attribution and stale policy claims | 9 | 95% |

### Failures (Tag: harmful)
| Strategy | Error Type | Root Cause | Prevention | Atomicity |
|----------|------------|------------|-----------|-----------|
| Update 41 branches in parallel | Cost amplification | No merge invalidation model | Update only the front PR | 96% |
| Cancel 818 workflow runs | Recoverability destruction | No context-to-event recovery map | Never cancel required runs without regeneration plan | 98% |
| Close/reopen as generic recovery | Incomplete trigger model | Explicit workflow type lists omit `reopened` | Verify trigger coverage or use synchronize | 94% |
| Report push before reading completion | False progress claim | Async state treated as success | Read terminal output and remote SHA first | 97% |
| Change merge architecture mid-drain | Scope thrash | No bounded experiment contract | Define cost, success, timeout, rollback first | 93% |

### Near Misses
| What Almost Failed | Recovery | Learning |
|--------------------|----------|----------|
| Stale Trunk guidance could have merged | PR #4814/#4792 closed and branches deleted | Close invalid policy PRs before they auto-merge |
| Strict-off stale merge race | Strict restored to true | Safety policy changes require explicit end-state verification |
| PR #4587 duplicate ratchets | Architect artifact exposed both duplicates | Run canonical review prompts locally after merging main |

## Phase 3: Decisions

### Action Classification

| Class | Action |
|-------|--------|
| Keep | Strict freshness, independent review, negative controls |
| Drop | Trunk.io, parallel backlog refresh, bulk required-run cancellation |
| Add | One-front landing protocol, cancellation recovery memory, local prompt gate |
| Modify | Push reporting, session completion, workflow `reopened` coverage |

### SMART Validation

| Action | Specific | Measurable | Achievable | Relevant | Time-bound |
|--------|----------|------------|------------|----------|------------|
| One-front landing | Only one auto-merge request and one refreshed branch | Armed PR count <= 1 | GitHub CLI supports it | Prevents CI explosion | Every merge |
| Cancellation guard | Require recovery event per required context | Recovery table exists before cancellation | Workflow metadata is queryable | Prevents stuck PRs | Before any bulk cancel |
| Push claim guard | Read terminal output and compare local/remote SHA | SHA equality recorded | Existing git commands | Prevents false status | Before every progress claim |
| Local prompts | Run matching canonical prompt files | Axis verdicts in QA report | Copilot CLI available | Avoids 15-minute remote loops | Before final push |

### Action Sequence

1. Restore strict freshness and remove Trunk.
2. Disable all auto-merge requests except one eligible front.
3. Repair stuck PRs only after mapping missing checks to trigger events.
4. Land the merge workflow protocol and issue #4827 trigger fix.
5. Persist cancellation and push-result learnings to Serena.

### Remediation Ownership

| Action | Owner | Tracking |
|--------|-------|----------|
| Add required-context cancellation guard and recovery manifest | Repository maintainers | Issue #4835 |
| Add `reopened` to active PR workflow triggers | Repository maintainers | Issue #4827 |
| Land strict one-front protocol and stacked PR guidance | Repository maintainers | Issue #4820 / PR #4821 |
| Keep Trunk removed and strict enabled | Repository admins | Ruleset 11104075 |

## Phase 4: Extracted Learnings

### Learning 1
- **Statement**: Never bulk-cancel required CI without a recovery event.
- **Atomicity Score**: 75%
- **Evidence**: Cancelling 818 runs left PRs with missing required contexts.
- **Skill Operation**: ADD
- **Target Skill ID**: ci-required-run-cancellation-recovery

### Learning 2
- **Statement**: Under strict freshness, refresh only the front PR.
- **Atomicity Score**: 75%
- **Evidence**: Updating 41 branches triggered 820 runs, most immediately stale.
- **Skill Operation**: ADD
- **Target Skill ID**: ci-strict-one-front-drain

### Learning 3
- **Statement**: Read terminal push output before reporting remote state.
- **Atomicity Score**: 75%
- **Evidence**: Failed pushes were reported as in-flight, delaying repair.
- **Skill Operation**: UPDATE
- **Target Skill ID**: agent-error-recovery-obligations

### Learning 4
- **Statement**: Run canonical CI review prompts before the final push.
- **Atomicity Score**: 75%
- **Evidence**: Remote Architect review found duplicate ratchets known locally.
- **Skill Operation**: ADD
- **Target Skill ID**: ci-local-ai-review-before-push

## Skillbook Updates

### ADD
```json
{
  "skill_id": "ci-required-run-cancellation-recovery",
  "statement": "Never bulk-cancel required CI without a recovery event.",
  "context": "Before cancelling queued or running GitHub Actions on PR branches.",
  "evidence": "2026-08-09 incident: 818 cancellations left missing required contexts.",
  "atomicity": 75
}
```

```json
{
  "skill_id": "ci-strict-one-front-drain",
  "statement": "Under strict freshness, refresh only the front PR.",
  "context": "When draining multiple PRs under require-branches-up-to-date.",
  "evidence": "Updating 41 branches triggered 820 workflow runs.",
  "atomicity": 75
}
```

```json
{
  "skill_id": "ci-local-ai-review-before-push",
  "statement": "Run canonical CI review prompts before the final push.",
  "context": "When changed paths trigger AI PR Quality Gate workflows.",
  "evidence": "PR #4587 duplicate ratchets were first found by remote Architect review.",
  "atomicity": 75
}
```

### UPDATE

| Skill ID | Current | Proposed | Why |
|----------|---------|----------|-----|
| agent-error-recovery-obligations | Fix push errors immediately | Read terminal push output and verify remote SHA before any progress claim | Async push failure was misreported as progress |

### TAG

| Skill ID | Tag | Evidence | Impact |
|----------|-----|----------|--------|
| ci-concurrency-group-evicts-pending-runs-on-main | harmful-cancellation | 818 cancelled runs and missing contexts | High |

### REMOVE

| Skill ID | Reason | Evidence |
|----------|--------|----------|
| None | No existing valid skill is obsolete | Search found no duplicate cancellation recovery skill |

## Deduplication Check

| New Skill | Most Similar | Similarity | Decision |
|-----------|--------------|------------|----------|
| ci-required-run-cancellation-recovery | ci-concurrency-group-evicts-pending-runs-on-main | 35% | ADD, different mechanism and action |
| ci-strict-one-front-drain | ci-count-ratchets-require-branch-freshness | 45% | ADD, cost-control procedure |
| ci-local-ai-review-before-push | github-actions-local-testing-integration | 40% | ADD, AI prompt gate rather than workflow emulation |
