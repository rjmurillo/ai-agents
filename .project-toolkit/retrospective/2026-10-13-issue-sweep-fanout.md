# Retrospective: 187-issue sweep and the fan-out that filled the disk

## Session Info
- **Date**: 2026-10-13
- **Agents**: orchestrator (main session), 187 triage agents (Sonnet), close-verify skeptic, spec/plan/build/test/review/ship chain agents (Sonnet), background commit security reviewer
- **Task Type**: Process (large-scale delegated issue sweep)
- **Outcome**: Partial. Open issues went 187 to 107 (including issues filed during the run). About 60 fix PRs merged. Remaining work is paused because root disk free space is 9G.

Evidence base: session facts supplied by the orchestrator plus the scratchpad files `triage.json`, `closeverify.json`, `run1.json`, `retry.json`, `defects.md`, `learnings_plan.json`. No session log exists, because session log creation is discontinued (`.claude/rules/universal.md`, MUST NOT item 10). Each claim is marked OBSERVED (tool output or file in the session), INFERRED (reading of the evidence), or UNKNOWN. Per `.claude/rules/retros.md`, this critiques processes and artifacts, not people.

Trigger: the user corrected the work explicitly (drive-by changes and filing major issues were permitted only after the first wave stalled), and `main` went red (time-bomb fixture, #6379).

## Phase 0: Data Gathering

### Evidence Links

- Red main: [#6379](https://github.com/rjmurillo/ai-agents/issues/6379), fixed by [#6387](https://github.com/rjmurillo/ai-agents/pull/6387)
- Security true positives: [#6297](https://github.com/rjmurillo/ai-agents/issues/6297) (merge_pr stacked merge TOCTOU), [#6415](https://github.com/rjmurillo/ai-agents/issues/6415) (dispatch-closure merge-base fail-open), [#5414](https://github.com/rjmurillo/ai-agents/issues/5414) (api_examples SSRF), [#6424](https://github.com/rjmurillo/ai-agents/issues/6424) (prepare_pr_body symlink)
- Scratch leak: [#6292](https://github.com/rjmurillo/ai-agents/issues/6292) (ratchet scratch trees leak into /tmp)
- Mirror drift commit: `7dfb67e51` (committed without `build_all.py`)
- Flaky test: `tests/validation/test_pre_push_testmon_concurrent_db.py::test_concurrent_partitions_record_into_one_database`, PR #6387 run 38340318288, job 115113458662
- Raw data: scratchpad `triage.json`, `closeverify.json`, `run1.json`, `retry.json`, `defects.md`, `learnings_plan.json`

### Failure Mode Classification

Against `.agents/governance/FAILURE-MODES.md`:

| Failure | Class | Why |
|---------|-------|-----|
| Mistake 1: ~82 chains, ~16 concurrent pre-push gates, disk and inode exhaustion | No match. Proposed new class 13, "Unbudgeted fan-out resource exhaustion" | None of the 12 classes covers shared-resource exhaustion by parallel delegation. Nearest is 7 (Self-Contained Agent Delegation Failure), but the delegated agents had full context; the delegator gave them no resource budget. Class 13 is a proposal only. Adopting it needs an ADR, which this retro does not write; see Findings for the owner |
| Mistake 2: workflows launched with `__FILL__` and `PLACEHOLDER_SEE_NEXT` args | 7. Self-Contained Agent Delegation Failure (delegator side) | The launch carried no real context. The failure was harmless (0 agents ran) |
| Mistake 3: prompts said "report defects, do not file", stranding 131 reports | 3. Ambiguous Instruction Inversion | Prompt wording blocked the output that mattered; the owner had to reverse it |
| 58% of proposed closes refuted by the skeptic (22 of 38) | 9. Confident-Incorrectness Recurrence | Single-pass triage asserted "already fixed" without a primary-source read. The skeptic pass caught it before closure |
| `7dfb67e51` committed without `build_all.py` | 4. False Completion Markers | A wait for disk budget was treated as permission to skip the generation step; the commit looked done |
| Disk-budget wait that skipped a step instead of blocking | 10. Silent Defaults and Guard-Clause Suppression | Absence of budget produced a silent skip, not an error |
| Subagent processes surviving TaskStop | Not a repo failure. Claude Code product defect (feedback drafted) | Subagent processes outlived TaskStop |
| Red main from a time-bomb fixture (`tests/metrics/metric_artifact_helpers.py:24`) | 11-adjacent (test fixture depends on wall clock) | A fixed date aged out; fixed in #6387 |

### 4-Step Debrief

**Step 1: Observe (facts only)**
- OBSERVED: 187 triage agents ran single-pass on Sonnet.
- OBSERVED: the close-verify skeptic refuted 22 of 38 proposed closes (58%). 16 were closed with evidence at the first pass.
- OBSERVED: owner decision D1 delegated all owner-decision items (take the recommended option, run adr-review debate).
- OBSERVED: ~82 chains started with ~16 concurrent full pre-push gates in separate worktrees. Root was 98% full; `/tmp` was an 8.4M-inode tmpfs. Both filled (ENOSPC). Bash stopped working. All work halted twice.
- OBSERVED: TaskStop left subagent processes running. The first `pkill` matched its own monitor and exited 144. Processes were then killed by hand.
- OBSERVED: mid-run fix: a semaphore of 4 heavy stages, 12 chains, and `df` checks.
- OBSERVED: root drained to 9G free again with three workflows plus the owner's other sessions. Work stopped a second time.
- OBSERVED: two launches with placeholder args failed with 0 agents.
- OBSERVED: prompts said "report defects, do not file". 131 defect reports sat unfiled until the owner permitted drive-by changes and filing of major issues (`defects.md`).
- OBSERVED: the weekly usage limit failed 88 agent calls. Resume-from-cache recovered them.
- OBSERVED: parallel pollers exhausted the GraphQL 5000/hr quota. The REST check-runs fallback worked.
- OBSERVED: the background commit security review caught 4 true positives before push (#6297, #6415, #5414, #6424). The repo pre-push security hook blocked one.
- OBSERVED: `7dfb67e51` was committed without `build_all.py` after a disk-budget wait.
- OBSERVED: `main` went red on a time-bomb fixture, `tests/metrics/metric_artifact_helpers.py:24`. Fixed in #6387 (#6379).
- OBSERVED: ~60 fix PRs merged. Open issues 187 to 107.

**Step 2: Respond**
- Pivots: fan-out width cut after the first ENOSPC; prompt policy changed from report-only to drive-by plus file.
- Retries: failed agent calls resumed from cache (88 calls); REST fallback for GraphQL.
- Escalations: D1 (owner decision policy), the drive-by and filing permission, and a leftover remote branch `fix/metric-age-test-clock` that a deny rule blocked deleting.
- Blocks: ENOSPC twice; usage limit once; GraphQL quota once.

**Step 3: Analyze**
- INFERRED: the largest loss came from sizing the fan-out by the number of tasks (187) instead of by the scarcest shared resource (disk and inodes). Each chain was correct alone; the sum was not.
- INFERRED: the skeptic pass is the highest-value control in the run. It converted a 58% false-close rate into zero false closes.
- INFERRED: the security review worked because it reads the diff, not the author's summary. That is the property that made it independent.
- Bias guard (identity check): the run's stated identity was "delegate everything, one idea per PR". Delegation did not fail; the unbudgeted width did. The conclusion is about an approach (unbounded parallelism), not about delegation as a method. Owner's other sessions are a candidate cause of the second stop only. UNKNOWN: whether other sessions were active during the first ENOSPC; the supplied facts do not say.

**Step 4: Apply**
- Add a fan-out resource budget, a block-not-skip rule for waits, launch arg validation, process-tree kill, and REST-first polling (see Phase 3).

### Execution Trace

Timestamps below are relative where the supplied facts give no clock time. Clock times are UNKNOWN except file mtimes in the scratchpad (2026-10-11 22:47 triage close-verify; 2026-10-12 19:51 first run; 2026-10-12 20:05 learnings plan; 2026-10-13 01:22 defects).

| Time | Agent | Action | Outcome | Energy |
|------|-------|--------|---------|--------|
| T+0 | orchestrator | 187 single-pass triage agents | Triage complete | High |
| T+1 | skeptic | Close-verify 38 proposed closes | 22 refuted, 16 closed | High |
| T+2 | orchestrator | D1: delegate owner decisions | Accepted | High |
| T+3 | orchestrator | Launch with `__FILL__` | 0 agents, harmless | Stalled |
| T+3 | orchestrator | Launch with `PLACEHOLDER_SEE_NEXT` | 0 agents, harmless | Stalled |
| T+4 | orchestrator | ~82 chains, ~16 concurrent gates | ENOSPC on root and tmpfs; Bash dead | Blocked |
| T+5 | orchestrator | TaskStop, then `pkill` | Processes survived; `pkill` hit its own monitor (exit 144); killed by hand | Blocked |
| T+6 | orchestrator | Semaphore 4 heavy stages, 12 chains, `df` checks | Resumed | Medium |
| T+7 | system | Weekly usage limit | 88 calls failed; resume-from-cache recovered | Medium |
| T+8 | pollers | GraphQL quota exhausted | REST check-runs fallback worked | Medium |
| T+9 | security reviewer | Background commit review | 4 true positives caught pre-push | High |
| T+10 | agent | Disk-budget wait, then commit `7dfb67e51` | Mirror drift (no `build_all.py`) | Sad |
| T+11 | CI | `main` red on `metric_artifact_helpers.py:24` | Fixed in #6387 | Medium |
| T+12 | owner | Drive-by and filing permission | 131 stranded reports released | High |
| T+13 | system | Root at 9G with three workflows plus other sessions | Second halt | Blocked |

### Timeline Patterns
- Every stall traced to a shared, finite resource (disk, inodes, usage limit, API quota), never to task difficulty.
- High-energy spans followed a new control being added (skeptic, semaphore, security review).

### Outcome Classification

**Mad (Blocked)**
- Disk and inode exhaustion, twice. Bash stopped working; all work halted.
- TaskStop left processes running.
- 131 defect reports stranded by prompt wording.

**Sad (Suboptimal)**
- Two placeholder-arg launches (0 agents, no damage).
- 88 calls lost to the usage limit (recovered).
- GraphQL quota exhausted by parallel pollers (recovered via REST).
- `7dfb67e51` committed with mirror drift.
- Single-pass triage produced 22 wrong close proposals.

**Glad (Success)**
- Skeptic pass blocked 22 false closes.
- Background security review caught 4 true positives before push.
- Resume-from-cache recovered 88 failed calls.
- ~60 PRs merged; open issues 187 to 107.

**Distribution**: Mad 3, Sad 5, Glad 4. Success rate by event count: 4 of 12 (33%). By outcome, the sweep moved 80 issues (43% of 187) and left 107 open.

## Phase 1: Insights Generated

### Five Whys: Mistake 1, disk and inode exhaustion halted all work twice

**Problem:** Bash stopped working and all work halted twice because root and `/tmp` hit ENOSPC.

**Q1:** Why did Bash stop working?
**A1:** OBSERVED: root was full and `/tmp` (8.4M-inode tmpfs) was out of inodes, so the shell and tools could not create temp files.

**Q2:** Why were root and `/tmp` full?
**A2:** OBSERVED: ~16 full pre-push gates ran at once in separate worktrees on a disk already 98% full. Each gate writes scratch trees and pytest basetemp into `/tmp` (leak tracked as #6292; `pyproject.toml:78` basetemp retention unset). INFERRED: per-gate footprint times 16 exceeded free space and inode count.

**Q3:** Why did ~16 heavy gates run concurrently?
**A3:** OBSERVED: ~82 chains started at once with no limit on heavy stages. INFERRED: concurrency was set by task count, not by a resource model.

**Q4:** Why was concurrency set by task count?
**A4:** INFERRED: the workflow design treated each chain as an independent unit and the orchestrator checked no precondition (`df`, inode count) before launch. No per-gate disk cost was known. UNKNOWN: the per-gate disk and inode footprint was never measured before the run.

**Q5:** Why was no budget or precondition in the design?
**A5:** INFERRED: no runbook or skill states a fan-out resource budget, and the "delegate everything" goal rewarded width. The repo has gates for correctness but none for the host's capacity to run them in parallel.

**Root Cause:** Fan-out width was chosen from task count with no capacity model for the shared resources the heaviest stage consumes.
**Actionable Fix:** Compute a resource budget before launch: measure per-gate footprint once, divide free disk and inodes by it with a safety factor, cap heavy-stage concurrency with a semaphore, and re-check `df` before each heavy stage.

**Recurrence evidence (second halt):** OBSERVED: after the semaphore, root drained to 9G with three workflows plus the owner's other sessions. INFERRED: the semaphore bounded this session's gates but not the host total. A static cap is not a budget when other consumers share the disk.

### Fishbone Analysis

**Problem:** Delegated sweep halted twice and stranded work.

| Category | Contributing factors |
|----------|----------------------|
| Prompt | "Report defects, do not file" stranded 131 reports; no instruction to check disk before heavy stages |
| Tools | `pkill` matched its own monitor (exit 144); TaskStop does not kill subagent process trees; GraphQL pollers share one quota |
| Context | Per-gate disk footprint unknown; other sessions' usage invisible to the orchestrator |
| Dependencies | 98%-full root; 8.4M-inode tmpfs; weekly usage limit; GraphQL 5000/hr |
| Sequence | Launch width set before any measurement; skeptic ran after, not before, triage closes |
| State | Scratch trees leaked from killed pushes (#6292); stale worktrees held disk |

**Cross-category patterns**: shared finite resources appear under Tools, Dependencies, Context, and State. That is the root-cause cluster.

**Controllable vs uncontrollable**

| Factor | Controllable? | Action |
|--------|---------------|--------|
| Fan-out width | Yes | Budget from measured footprint |
| Heavy-stage concurrency | Yes | Semaphore plus pre-stage `df` and inode check |
| Placeholder args | Yes | Validate before launch |
| Prompt wording on filing | Yes | State the file-or-report policy explicitly |
| Process tree after TaskStop | Partly | Kill the tree by process group; report product defect |
| Weekly usage limit | No | Resume-from-cache; checkpoint results |
| Other sessions' disk use | No | Leave headroom; stop on a low-water mark |

### Force Field Analysis

**Desired state**: large sweeps run to completion without exhausting host resources.
**Current state**: sweeps halt when the host fills.

| Driving force | Strength | Restraining force | Strength |
|---------------|----------|-------------------|----------|
| Semaphore and `df` checks already proven mid-run | 4 | "Delegate everything" goal rewards width | 4 |
| Resume-from-cache makes restarts cheap | 3 | Owner's other sessions are invisible to the plan | 3 |
| Pre-push security review gives confidence to push in parallel | 3 | Scratch-leak defect #6292 unfixed | 3 |
| Owner reads the findings table | 2 | No launch-time validation of args or budget | 3 |

Net: 12 driving, 13 restraining. Strengthen the semaphore by making it a budget. Reduce the goal pressure by naming a width ceiling in the launch prompt.

### Patterns and Shifts

| Pattern | Frequency | Impact | Category |
|---------|-----------|--------|----------|
| Shared finite resource exhausted | 4 (disk/inodes, usage limit, GraphQL quota, root again) | High | Failure |
| Independent skeptic or reviewer catches an author error | 2 (close-verify 22 of 38; security review 4) | High | Success |
| Wait or skip treated as done | 1 (`7dfb67e51`) | Medium | Failure |
| Placeholder args reach launch | 2 | Low | Failure |

| Shift | When | Before | After | Cause |
|-------|------|--------|-------|-------|
| Filing policy | After 131 stranded reports | Report only | Drive-by plus file major issues | Owner directive 2026-10-12 |
| Concurrency | After first ENOSPC | ~16 heavy gates | 4 heavy stages, 12 chains | Orchestrator fix |

### Learning Matrix

**Continue**: skeptic pass on proposed closes; background security review before push; resume-from-cache; REST fallback.
**Change**: fan-out sized by task count; polling by GraphQL; prompt wording that forbids filing; skipping a step during a wait.
**Idea**: a `fanout-budget` preflight that prints per-stage footprint and the allowed width; launch-arg validator in the workflow script.
**Invest**: fix #6292 (scratch leak) so each killed push stops leaking inodes; a host-capacity probe the orchestrator can call.

## Phase 2: Diagnosis

### Successes (Tag: helpful)

| Strategy | Evidence | Impact | Atomicity |
|----------|----------|--------|-----------|
| Run a skeptic over proposed closes before closing | 22 of 38 refuted (58%); 16 closed with evidence | 9 | 90% |
| Review the commit diff for security before push | 4 true positives (#6297, #6415, #5414, #6424) | 9 | 88% |
| Resume from cache after a usage-limit failure | 88 failed calls recovered | 7 | 85% |
| REST check-runs fallback when GraphQL is exhausted | Polling continued | 6 | 85% |

### Failures (Tag: harmful)

| Strategy | Error Type | Root Cause | Prevention | Atomicity |
|----------|------------|------------|------------|-----------|
| ~82 chains, ~16 concurrent full gates | Resource exhaustion | No capacity model | Resource budget plus semaphore | 88% |
| Wait on disk budget, then skip a step | False completion | Wait treated as optional | Block, never skip | 90% |
| Launch with placeholder args | Context loss | No arg validation | Reject placeholder tokens at launch | 90% |
| "Report defects, do not file" | Instruction inversion | Prompt blocked the useful output | State file-or-report policy per run | 80% |
| `pkill` by pattern after TaskStop | Tool misuse | Pattern matched own monitor | Kill by process group or PID | 85% |

### Near Misses

| What Almost Failed | Recovery | Learning |
|--------------------|----------|----------|
| 22 wrong closes | Skeptic refuted them | Single-pass triage is not enough evidence to close |
| 4 security defects headed for push | Background review and the pre-push hook | Review the diff, not the summary |
| Mirror drift in `7dfb67e51` | Detected after the fact (detection path UNKNOWN) | A skipped generator step shows up only at the gate |
| Time-bomb fixture on `main` | #6387 | Fixtures that read a fixed date age out |

### Traceability Health
NOT RUN. The session produced no spec-layer artifacts for this retrospective.

### Impact

| Area | Severity | Effect |
|------|----------|--------|
| Root disk and inodes | High | Bash stopped working twice; all sweep work halted |
| Defect reports | High | 131 reports stranded by prompt wording until policy changed |
| Close proposals | Medium | 22 wrong close proposals, caught by the skeptic pass |
| CI and polling | Medium | GraphQL quota exhausted by parallel pollers; recovered via REST |
| Generated mirrors | Medium | `7dfb67e51` committed with mirror drift |
| Launch hygiene | Low | Two placeholder-arg launches ran 0 agents, no damage |

## Phase 3: Decisions

### Action Classification

| Class | Finding | Action |
|-------|---------|--------|
| Keep | Skeptic pass; diff-based security review; resume-from-cache; REST fallback | Retain; make skeptic mandatory for bulk closes |
| Drop | Width by task count; "do not file" wording; `pkill` by pattern | Replace |
| Add | Fan-out resource budget; launch-arg validator; process-tree kill | New process rules |
| Modify | Pollers: REST first, GraphQL only for fields REST lacks | Update guidance |

### SMART Validation (selected)

| Statement | S | M | A | R | T |
|-----------|---|---|---|---|---|
| Cap heavy-stage concurrency at floor(free_disk / (3 x measured_stage_footprint)) | Y | Y | Y | Y | Y (before launch) |
| A wait on a resource budget blocks; it never skips a step | Y | Y | Y | Y | Y (at each wait) |
| Reject launch args containing `__FILL__` or `PLACEHOLDER` | Y | Y | Y | Y | Y (at launch) |
| Kill a TaskStop'd subagent by process group, never by name pattern | Y | Y | Y | Y | Y (after TaskStop) |
| Poll check status via REST check-runs by default | Y | Y | Y | Y | Y (all polling) |

### Action Sequence

| Order | Action | Owner | Depends On | Blocks |
|-------|--------|-------|------------|--------|
| 1 | Measure per-stage disk and inode footprint once | Repo owner | None | 2 |
| 2 | Add the budget formula and low-water-mark stop to the launch prompt | Repo owner | 1 | 4 |
| 3 | Add placeholder-arg validation to the workflow script | Repo owner | None | 4 |
| 4 | Relaunch the paused sweep when root has headroom | Repo owner | 2, 3 | None |
| 5 | Fix #6292 so killed pushes stop leaking scratch | Issue #6292 | None | None |

## Phase 4: Extracted Learnings

### Learning 1
- **Statement**: Size heavy-stage concurrency from measured disk and inode footprint, not task count.
- **Atomicity Score**: 90%
- **Evidence**: ~16 concurrent gates filled root (98% full) and an 8.4M-inode tmpfs; all work halted twice.
- **Skill Operation**: ADD
- **Target Skill ID**: fanout-resource-budget

### Learning 2
- **Statement**: A wait on a resource budget must block; never skip the step it guards.
- **Atomicity Score**: 90%
- **Evidence**: `7dfb67e51` committed without `build_all.py` after a disk-budget wait.
- **Skill Operation**: ADD
- **Target Skill ID**: wait-blocks-never-skips

### Learning 3
- **Statement**: Reject workflow launch args that contain placeholder tokens before any agent starts.
- **Atomicity Score**: 90%
- **Evidence**: Two launches with `__FILL__` and `PLACEHOLDER_SEE_NEXT` ran 0 agents.
- **Skill Operation**: ADD
- **Target Skill ID**: workflow-launch-arg-validation

### Learning 4
- **Statement**: After TaskStop, kill the subagent process group; do not use name-pattern `pkill`.
- **Atomicity Score**: 85%
- **Evidence**: Subagents survived TaskStop; first `pkill` matched its own monitor (exit 144).
- **Skill Operation**: ADD
- **Target Skill ID**: taskstop-kill-process-tree

### Learning 5
- **Statement**: Poll check status through REST check-runs; reserve GraphQL for fields REST lacks.
- **Atomicity Score**: 85%
- **Evidence**: Parallel pollers exhausted the GraphQL 5000/hr quota; REST fallback worked.
- **Skill Operation**: ADD
- **Target Skill ID**: poll-rest-first

### Learning 6
- **Statement**: Require a skeptic pass before closing issues from single-pass triage.
- **Atomicity Score**: 90%
- **Evidence**: Skeptic refuted 22 of 38 proposed closes (58%).
- **Skill Operation**: ADD
- **Target Skill ID**: bulk-close-skeptic-pass

### Learning 7
- **Statement**: State the file-or-report policy for defects in every delegated agent prompt.
- **Atomicity Score**: 80%
- **Evidence**: "Report defects, do not file" stranded 131 reports until the owner changed the policy.
- **Skill Operation**: ADD
- **Target Skill ID**: delegation-defect-policy

## Skillbook Updates

### ADD
```json
[
  {"skill_id": "fanout-resource-budget", "statement": "Size heavy-stage concurrency from measured disk and inode footprint, not task count.", "context": "Before launching any workflow that runs full pre-push gates in parallel worktrees", "evidence": "2026-10-13 issue sweep: ~16 gates filled root and /tmp twice", "atomicity": 90},
  {"skill_id": "wait-blocks-never-skips", "statement": "A wait on a resource budget must block; never skip the step it guards.", "context": "Any agent waiting on disk, quota, or lock", "evidence": "Commit 7dfb67e51 skipped build_all.py after a disk-budget wait", "atomicity": 90},
  {"skill_id": "workflow-launch-arg-validation", "statement": "Reject workflow launch args that contain placeholder tokens before any agent starts.", "context": "Workflow tool launch", "evidence": "Two launches with __FILL__ and PLACEHOLDER_SEE_NEXT ran 0 agents", "atomicity": 90},
  {"skill_id": "taskstop-kill-process-tree", "statement": "After TaskStop, kill the subagent process group; do not use name-pattern pkill.", "context": "Stopping a workflow that spawned subagents", "evidence": "Subagents survived TaskStop; pkill matched its own monitor, exit 144", "atomicity": 85},
  {"skill_id": "poll-rest-first", "statement": "Poll check status through REST check-runs; reserve GraphQL for fields REST lacks.", "context": "Parallel PR status pollers", "evidence": "GraphQL 5000/hr exhausted; REST fallback worked", "atomicity": 85},
  {"skill_id": "bulk-close-skeptic-pass", "statement": "Require a skeptic pass before closing issues from single-pass triage.", "context": "Bulk issue closure", "evidence": "22 of 38 proposed closes refuted (58%)", "atomicity": 90},
  {"skill_id": "delegation-defect-policy", "statement": "State the file-or-report policy for defects in every delegated agent prompt.", "context": "Writing agent prompts for sweeps", "evidence": "131 defect reports stranded until owner changed policy", "atomicity": 80}
]
```

### UPDATE, TAG, REMOVE
None. These candidates have not been checked against the skillbook; see Deduplication Check.

## Deduplication Check

NOT RUN. The skillbook and `search_memory.py` were not queried in this pass because the task was scoped to writing the artifact, and the Serena checkout is not this worktree (`.claude/rules/universal.md` MUST NOT 11). The skillbook agent owns deduplication before any of the seven candidates persist.

## Phase 5: Persist and Close

### Memory Persistence
NOT PERFORMED. No Serena write was made from this linked worktree. The seven candidates are returned to the parent session for routing to skillbook. No commit or push was made (root disk at 9G; pushes paused).

### +/Delta

**+ Keep**
- Independent verifiers (skeptic, diff-based security review) caught every high-stakes error before it landed.
- Evidence files in the scratchpad made OBSERVED claims checkable.

**Delta Change**
- Name the scarce shared resource before choosing width.
- Mark a defect-handling policy in the first prompt, not after 131 reports pile up.
- The `FAILURE-MODES.md` classes do not cover resource exhaustion; this retro had to propose a class.

### Delta Triage

| Delta Item | Category |
|------------|----------|
| New failure class 13 for unbudgeted fan-out | Missing Documentation |
| Launch-arg placeholder validation | Process Improvements |
| Fan-out budget preflight | Feature Requests |
| Scratch leak #6292 | Process Improvements (already tracked) |

### Findings for the owner

| Item | Evidence (path:line) | Proposed action | Class |
|------|----------------------|-----------------|-------|
| `FAILURE-MODES.md` has no class for fan-out resource exhaustion | `.agents/governance/FAILURE-MODES.md:15-30` (index lists 12 classes, none on shared-resource exhaustion) | Add class 13 with a linked ADR; `.claude/rules/retros.md` MUST 2 requires the ADR | Requested improvement |
| Ratchet scratch trees leak into `/tmp` on a killed push; pytest basetemp retention unset | `pyproject.toml:78` (basetemp retention); issue #6292 | Cap retention and clean scratch on exit; already tracked in #6292 | Requested improvement |
| TaskStop leaves subagent processes running | Observed in this session; product feedback drafted | Report to the Claude Code product team; not a repo issue | Side quest |
| Remote branch `fix/metric-age-test-clock` left behind after PR #6387 merged via REST; deny rule blocked delete | PR #6387 | Owner deletes the branch | Optional enhancement |
| Flaky `test_concurrent_partitions_record_into_one_database` failed `assert 30 == (2 * 30)` once; rerun passed at the same head | PR #6387 run 38340318288, job 115113458662 | File an issue and fix | Requested improvement |
| Mirror drift from `7dfb67e51` | Commit `7dfb67e51` | Run `build_all.py` and commit the regenerated mirrors on the owning branch | Requested improvement (INFERRED: `.claude/AGENTS.md` says a hand edit or missed render reds pre-PR `Generated Artifact Staleness`; not run here) |

### ROTI Assessment

**Score**: 3

**Benefits Received**:
- A named root cause (no capacity model) with five concrete process changes.
- A classified gap in the failure taxonomy.
- Seven atomic skill candidates, all at 80% or higher.

**Time Invested**: one pass over the supplied facts and scratchpad files; the raw `run1.json` (281 KB) and `triage.json` (247 KB) were not re-read in full, so counts such as 82 chains and 131 reports are the orchestrator's figures, not recomputed here.

**Verdict**: Continue.

### Helped, Hindered, Hypothesis

**Helped**
- Scratchpad evidence files and the 2026-10-11 retro as a format reference.

**Hindered**
- Clock times for most events were not recorded; the trace uses relative order.
- Per-gate disk footprint was never measured, so the Five Whys stops at UNKNOWN on A4.

**Hypothesis**
- Measuring one gate's footprint and printing the allowed width at launch will prevent the next ENOSPC halt. Test it on the next paused-sweep relaunch.

## Retrospective Handoff

### Skill Candidates

| Skill ID | Statement | Atomicity | Operation | Target |
|----------|-----------|-----------|-----------|--------|
| fanout-resource-budget | Size heavy-stage concurrency from measured disk and inode footprint, not task count. | 90% | ADD | - |
| wait-blocks-never-skips | A wait on a resource budget must block; never skip the step it guards. | 90% | ADD | - |
| workflow-launch-arg-validation | Reject workflow launch args that contain placeholder tokens before any agent starts. | 90% | ADD | - |
| taskstop-kill-process-tree | After TaskStop, kill the subagent process group; do not use name-pattern pkill. | 85% | ADD | - |
| poll-rest-first | Poll check status through REST check-runs; reserve GraphQL for fields REST lacks. | 85% | ADD | - |
| bulk-close-skeptic-pass | Require a skeptic pass before closing issues from single-pass triage. | 90% | ADD | - |
| delegation-defect-policy | State the file-or-report policy for defects in every delegated agent prompt. | 80% | ADD | - |

### Memory Updates

None written. Routed to the parent session (linked worktree; see Phase 5).

### Git Operations

| Operation | Path | Reason |
|-----------|------|--------|
| git add | `.project-toolkit/retrospective/2026-10-13-issue-sweep-fanout.md` | Retrospective artifact (not committed; pushes paused) |

### Handoff Summary

- **Skills to persist**: 7 candidates (atomicity >= 80%)
- **Memory files touched**: none
- **Blockers for the owner**: 0
- **Recommended next**: skillbook (dedup then persist), then commit this file when disk allows
