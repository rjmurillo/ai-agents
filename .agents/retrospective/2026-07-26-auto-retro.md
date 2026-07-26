# Retrospective: PR autofix queue, 2026-07-26

## Session Info
- **Date**: 2026-07-26
- **Agents**: Copilot CLI, pr-comment-responder, merge-resolver, retrospective
- **Task Type**: Bug
- **Outcome**: Complete. Eleven queued PRs merged. Issue #3357 tracks the
  atomic-write defect found in the merged causal-graph driver.

## Phase 0: Data Gathering

### 4-Step Debrief

- **Observe**: The queue merged PRs #3326, #3327, #3334, #3336, #3337,
  #3338, #3339, #3340, #3344, #3347, and #3348. PR #3348 required five
  review rounds, a documented commit-limit bypass, and concurrent-commit
  reconciliation through `f8b5f9a35f`.
- **Respond**: The session resolved every review thread, reran the failed PR
  validation job after adding `commit-limit-bypass`, and merged #3348 after
  required CI passed. It then deleted an accidentally recreated remote branch
  and opened issue #3357 for the unmerged atomic-write correction.
- **Analyze**: Live-state gates, completion gates, and remote-head checks
  preserved concurrent commits. A failed fetch followed by a push recreated a
  branch GitHub had deleted after merge. Content-only atomic-write tests also
  missed a mode change from `0644` to `0600`.
- **Apply**: Treat failed fetches and missing expected refs as push blockers.
  Audit delegated files and outcomes. Test atomic replacement for content,
  cleanup, close failures, and destination metadata.

### Execution Trace

1. Triaged the open queue and processed land-ready PRs before thread work.
2. Merged ten PRs after fresh live-state and four-condition completion gates.
3. Isolated PR #3347 in a worktree after the shared checkout changed.
4. Found that a #3348 responder changed retrospective and Serena artifacts
   instead of resolving the assigned final thread.
5. Removed the unrelated artifacts and preserved `.serena/project.yml`.
6. Corrected the inaccurate causal-graph key comment and resolved all 16
   review threads.
7. Merged current `main` into #3348 after PR #3347 landed.
8. Incorporated four later review fixes for ancestor recovery, counter
   semantics, edge identity, malformed records, and exit-code behavior.
9. Used `commit-limit-bypass` after review churn pushed #3348 past 20 commits,
   then reran the failed PR validation job.
10. Merged #3348 at `f8b5f9a35f` after required CI and thread gates passed.
11. Probed an atomic-write follow-up, found and corrected mode loss, and reached
    68 focused tests with clean Ruff and mypy results.
12. Deleted the accidentally recreated #3348 branch and opened issue #3357 for
    the focused follow-up.

### Outcome Classification

- **Glad**: Eleven PRs merged without overwriting concurrent branch work.
- **Sad**: A stale push recreated a deleted branch, and the atomic-write fix
  missed #3348's merge by one race.
- **Mad**: None. The defect was preserved as tested code and issue #3357.

## Phase 1: Insights Generated

### Five Whys: Delegated work left the assigned PR path

1. Why did the responder fail to finish #3348? It created unrelated
   retrospective and Serena artifacts.
2. Why did that output survive until review? Its return value was inspected
   after execution, not constrained by a changed-file scope check.
3. Why was a return value insufficient? A plausible narrative does not prove
   that the assigned thread changed state.
4. Why was thread state the better verifier? The task's acceptance condition
   was a zero unresolved-thread count, not artifact creation.
5. Why did recovery succeed? The branch diff exposed the unrelated files
   before they were pushed.

**Root cause**: Delegated PR work lacked an artifact-level scope and outcome
audit. This maps to FM-7, Self-Contained Agent Delegation Failure.

### Five Whys: The merge-resolver helper failed to create its worktree

1. Why did the helper fail? The PR branch was already checked out.
2. Why was the branch already checked out? The primary checkout owned #3348.
3. Why did the helper need another worktree? Its default workflow isolates
   conflict resolution by checking out the same branch elsewhere.
4. Why was isolation unnecessary here? A trial merge completed cleanly with
   no unmerged files.
5. Why was recovery safe? The existing `.serena/project.yml` edit stayed
   unstaged, and validation covered the merged result.

**Root cause**: The helper's isolated-worktree path did not fit a branch
already owned by the current checkout. This was an efficiency failure, not a
correctness failure.

### Five Whys: A deleted remote branch was recreated

1. Why did the #3348 branch reappear after merge? A later push recreated it.
2. Why did the push run after GitHub deleted the branch? The local workflow
   continued from a stale branch snapshot.
3. Why was the snapshot stale? A fetch failed before the push.
4. Why did work continue after the failed fetch? The command chain did not
   make fetch success a blocking precondition.
5. Why was deletion recovery needed? Push safety checked commit identity but
   not the existence and freshness of the remote ref.

**Root cause**: Push authorization depended on stale local state after a failed
fetch. This maps to FM-5, Premature Merge and Deploy, as a destructive
shared-branch near miss.

### Five Whys: The first atomic-write fix changed file mode

1. Why did mode change from `0644` to `0600`? `mkstemp()` created the temporary
   file with owner-only permissions.
2. Why did replacement keep that mode? `os.replace()` moves the temporary
   inode and its metadata.
3. Why did tests miss the change? They asserted merged content and failure
   cleanup only.
4. Why was content treated as the full contract? The design considered
   atomicity but not destination metadata.
5. Why was the issue found before commit? An empirical probe inspected mode
   bits after replacement.

**Root cause**: The atomic-write contract omitted destination metadata.
Content-only verification was incomplete.

### Patterns and Shifts

- Remote-head checks repeatedly caught or guarded concurrent branch movement.
- New review rounds arrived after earlier threads were resolved. Thread count
  had to be re-read after every push.
- Comment accuracy mattered. `_COLLECTIONS` used node `id`, pattern `name`,
  and the edge triple, not a single hash rule.
- Generated causal-graph conflicts became clean merges once the registered
  content merge driver was active.
- A failed prerequisite must stop the mutation chain. Continuing after a
  failed fetch converted a cleanup action into branch recreation.
- Atomic replacement changes inode metadata unless the implementation copies
  the required destination properties.

### Learning Matrix

| Category | Learning |
|----------|----------|
| Continue | Run live-state and completion gates immediately before actions. |
| Change | Audit delegate file changes and the real PR outcome before acceptance. |
| Stop | Pushing after any failed fetch or missing expected remote ref. |
| Start | Probe atomic replacement for metadata, partial writes, and close errors. |

### What Went Well

- PR #3347 merged only after 18 threads resolved and its completion gate
  passed.
- PR #3348 merged after all later review rounds, required CI, and a documented
  commit-limit bypass.
- Remote SHA comparisons preserved concurrent commits `a20e67fa3c`,
  `bf60eab071`, `434721b64d`, and `f8b5f9a35f`.
- The atomic-write follow-up now covers replace failure, partial writes, close
  failure, cleanup failure, descriptor ownership, and mode preservation across
  68 focused tests.

### What Could Improve

- The delegated #3348 responder should have been checked against its assigned
  files and unresolved-thread count before its output was accepted.
- The push that recreated the deleted branch should have stopped when its
  preceding fetch failed.
- The first atomic-write test should have asserted file mode, not content
  alone. The missing assertion allowed a `0644` to `0600` regression.
- The assistant sent a stopping response while a required CI watcher still
  ran. Autofix was not complete at that point.

## Phase 2: Diagnosis

### Successes (Tag: helpful)
| Strategy | Evidence | Impact | Atomicity |
|----------|----------|--------|-----------|
| Fresh live-state gate before PR action | #3348 returned `Data.action=ACT` before the thread reply | 10 | 98% |
| Remote-head comparison before push | #3348 remote `403adeb3f5` matched merge commit parent | 10 | 98% |
| Four-condition completion gate | Eleven PRs merged only after branch, CI, threads, and merge state passed | 10 | 96% |
| Empirical metadata probe | Detected mode change from `0644` to `0600` before commit | 9 | 97% |

### Failures (Tag: harmful)
| Strategy | Error Type | Root Cause | Prevention | Atomicity |
|----------|------------|------------|------------|-----------|
| Accept delegated output before scope audit | FM-7 delegation failure | Narrative output did not prove thread completion | Compare changed files and unresolved-thread count | 96% |
| Stop while CI watcher remained active | Process control near miss | Long-running check was treated as a stopping point | Finalize only after completion gate or blocker | 95% |
| Invoke isolated resolver on checked-out branch | Tool-fit error | Helper needed a second checkout of an owned branch | Use a clean in-place trial merge first | 90% |
| Push after failed fetch | FM-5 shared-branch near miss | Stale local state authorized a remote mutation | Require successful fetch and expected ref existence | 98% |
| Test atomic content without metadata | Contract omission | Replacement inode metadata was not part of assertions | Assert required metadata after replacement | 97% |

### Near Misses
| What Almost Failed | Recovery | Learning |
|--------------------|----------|----------|
| Merge before required CI completed, FM-5 | Completion gate blocked merge | Never merge from `CanMerge` or thread count alone. |
| Concurrent agents overwrote branch work | Remote SHA matched before each push | A push needs a live branch ownership check. |
| Unrelated `.serena/project.yml` was staged | Explicit path staging left it unstaged | Stage only task files in shared checkouts. |
| Delegate artifacts entered PR #3348 | Scope audit removed them before push | Agent output is evidence to inspect, not authority. |
| Deleted #3348 branch was left recreated | Live remote inspection exposed it and deletion restored state | Failed fetches block later pushes. |
| Atomic replacement weakened permissions | Mode probe exposed `0644` to `0600` before commit | Metadata belongs in the write contract. |

## Phase 3: Decisions

### Action Classification

| Action | Decision | Evidence |
|--------|----------|----------|
| Keep | Live-state gate and completion gate | Ten safe merges and no premature merge |
| Keep | Remote-head SHA checks | Concurrent work survived on #3340, #3347, and #3348 |
| Drop | Accepting delegated work from narrative alone | #3348 responder missed the assigned thread |
| Add | Changed-file and outcome audit after delegation | The audit isolated unrelated artifacts |
| Add | Failed-fetch stop before any push | A stale push recreated the deleted #3348 branch |
| Add | Metadata checks for atomic replacement | First probe found mode loss |
| Modify | Try a clean in-place base merge before a second worktree | #3348 merged `main` without conflicts |

### SMART Validation

- **Delegation scope audit**: After each delegated PR task, inspect changed
  files and re-query the assigned acceptance condition before using its
  output. The check is specific, takes one command pair, and runs immediately.
- **Push ownership check**: Before each push, compare live `headRefOid` with
  the expected local parent. A failed fetch, missing ref, or mismatch blocks
  the push.
- **Autofix stop rule**: Do not send a final response while a required CI
  watcher is active. Resume after notification and run the completion gate.
- **Atomic-write contract**: Verify unchanged destination content on write,
  close, and replace failures. Verify cleanup and destination mode on success.

### Action Sequence

1. Query the PR's live state.
2. Assign or perform one bounded action.
3. Audit changed files and the action's acceptance condition.
4. Validate the smallest relevant test set and system-boundary metadata.
5. Fetch successfully and compare the remote head with the expected commit.
6. Push, re-read threads and CI, then run the completion gate.
7. Merge only after all four conditions pass.

## Phase 4: Extracted Learnings

### Learning 1
- **Statement**: Audit delegated file changes against the assigned PR outcome.
- **Atomicity Score**: 96%
- **Evidence**: PR #3348 responder created unrelated artifacts and left its thread open.
- **Skill Operation**: ADD
- **Target Skill ID**: pr-review-delegated-work-scope-audit

### Learning 2
- **Statement**: Compare the live remote head before every PR push.
- **Atomicity Score**: 98%
- **Evidence**: Concurrent updates occurred on PRs #3340, #3347, and #3348.
- **Skill Operation**: UPDATE
- **Target Skill ID**: pr-comment-005-branch-state-verification

### Learning 3
- **Statement**: End autofix only after its completion gate returns.
- **Atomicity Score**: 95%
- **Evidence**: A final response was sent while #3348 CI still ran.
- **Skill Operation**: TAG
- **Target Skill ID**: pr-autofix

### Learning 4
- **Statement**: Stop a push chain when fetch fails or the expected ref is missing.
- **Atomicity Score**: 98%
- **Evidence**: A stale push recreated #3348's branch after GitHub deleted it.
- **Skill Operation**: UPDATE
- **Target Skill ID**: pr-comment-005-branch-state-verification

### Learning 5
- **Statement**: Preserve destination metadata during atomic file replacement.
- **Atomicity Score**: 97%
- **Evidence**: The first #3357 probe changed mode from `0644` to `0600`.
- **Skill Operation**: ADD
- **Target Skill ID**: atomic-replace-preserve-metadata

## Skillbook Updates

### ADD
```json
{
  "skill_id": "pr-review-delegated-work-scope-audit",
  "statement": "Audit delegated file changes against the assigned PR outcome.",
  "context": "After delegated PR review, CI fix, or thread response work.",
  "evidence": "PR #3348 scope diversion on 2026-07-26.",
  "atomicity": 96
}
```

```json
{
  "skill_id": "atomic-replace-preserve-metadata",
  "statement": "Preserve destination metadata during atomic file replacement.",
  "context": "When changing an in-place write to temporary-file plus os.replace.",
  "evidence": "Issue #3357 mode regression probe on 2026-07-26.",
  "atomicity": 97
}
```

### UPDATE

| Skill ID | Current | Proposed | Why |
|----------|---------|----------|-----|
| pr-comment-005-branch-state-verification | Compare live remote head before pushes | Also stop on failed fetch or missing expected ref | A stale push recreated the deleted #3348 branch |

### TAG

| Skill ID | Tag | Evidence | Impact |
|----------|-----|----------|--------|
| pr-autofix | completion-gate-before-final | #3348 CI watcher remained active | Prevents premature stopping and merge |

### REMOVE

| Skill ID | Reason | Evidence |
|----------|--------|----------|
| None | No stored skill was disproven | Session evidence supported current gates |

## Deduplication Check

| New Skill | Most Similar | Similarity | Decision |
|-----------|--------------|------------|----------|
| pr-review-delegated-work-scope-audit | FM-7 Self-Contained Agent Delegation Failure | 65% | Add PR-specific outcome audit |
| remote-head-before-push | pr-comment-005-branch-state-verification | 85% | Update existing memory |
| completion-gate-before-final | pr-autofix completion gate | 100% | Tag existing skill, no duplicate |
| atomic-replace-preserve-metadata | atomic write implementation guidance | 55% | Add tested metadata rule |

## Failure Patterns

- **FM-5 Premature Merge and Deploy, near miss**: A push continued after a
  failed fetch and recreated the deleted #3348 branch. Live inspection and
  explicit deletion restored the merged state.
- **FM-7 Self-Contained Agent Delegation Failure, occurred**: Delegated agents
  created retrospective and Serena artifacts outside their assigned code
  review scope. Changed-file audits quarantined those artifacts.
- **FM-4 False Completion Markers, avoided after correction**: An earlier
  response treated an active CI waiter as a stopping point. The workflow
  resumed, ran the completion gate, and merged #3348.
- **FM-9 Confident-Incorrectness Recurrence, near miss**: The first atomic
  replacement looked correct under content-only tests but changed destination
  mode. A direct metadata probe disproved the assumption before commit.

## Phase 5: Persist and Close

### Memory Persistence

- Updated `pr-comment-005-branch-state-verification` with failed-fetch and
  missing-ref stop conditions.
- Added `delegated-pr-work-scope-audit` for post-delegation file and outcome
  checks.
- Added `atomic-replace-preserve-metadata` with the `0644` to `0600` evidence.

### + / Delta

- **+** Live-state gates and remote SHA checks preserved concurrent commits
  across eleven merged PRs.
- **Delta** Prerequisite failure handling must be mechanical. A failed fetch
  cannot be followed by a push.

### ROTI

- **8/10**. The queue reached zero open PRs and exposed two reusable safety
  rules. Branch recreation and delegated scope drift added recovery work.

### Helped, Hindered, Hypothesis

- **Helped**: Fresh PR state, remote SHA comparison, targeted tests, and direct
  filesystem probes.
- **Hindered**: Asynchronous reviewer rounds, delegated scope drift, and stale
  local state after a failed fetch.
- **Hypothesis**: Making fetch success, expected-ref existence, and metadata
  assertions blocking gates will remove both recovery classes in future runs.
