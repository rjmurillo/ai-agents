# Retrospective: worktree-freeze

## Session Info
- **Date**: 2026-09-01
- **Agents**: Copilot CLI, Claude Sonnet 5, GPT-5.6 Sol
- **Task Type**: Bug
- **Outcome**: Partial

## Phase 0: Data Gathering
The session started with ten open pull requests. Most were blocked by the same red checks on `main`. Parallel workers repeated that diagnosis, increased machine load, and made local hook timeouts worse. A GPT-5.6 worker fixed the shared repo-health and recovery-manifest failures through #5448. The user then stopped all implementation and requested durable branch checkpoints.

The response first closed valid pull requests when local hooks exceeded their timeout. The user rejected that action. The affected pull requests were reopened, and the closure comments were retracted. The session then stopped PR work, synced worktrees with repaired `main`, committed local artifacts, and moved pushes to a native WSL clone.

Outcome classification: main repair succeeded. Pull request closures were harmful and reversed. Worktree checkpointing remains in progress because pre-push ratchets exceed their wall-clock budget under machine load.

## Phase 1: Insights Generated
Why did valid work get closed? The workflow treated a local timeout as a terminal product verdict. Why? A terminal-state instruction overrode the distinction between invalid work and delayed work. Why? The coordinator optimized for ending tasks instead of preserving value. Why? Main remained red while ten agents repeated the same blocked analysis. Why? The session did not identify and fix the shared dependency first.

Contributing factors included parallel agent load, Windows filesystem latency, stale mutation markers, public PyPI restrictions, and branch-local environments missing hook dependencies. The largest control failure was sequencing. Fixing `main` first would have removed the shared blocker and reduced repeated work.

Pattern: environment failures must change scheduling or execution location. They must not change the validity verdict for a pull request.

## Phase 2: Diagnosis

### Successes (Tag: helpful)
| Strategy | Evidence | Impact | Atomicity |
|----------|----------|--------|-----------|
| Fix shared red main first | #5448 restored repo-health and recovery tests | 10 | 90% |
| Use native WSL storage for hooks | Checkpoint branch push completed from ext4 | 8 | 85% |
| Preserve before mutation | Recovery branches and stashes exist for every sync | 9 | 90% |

### Failures (Tag: harmful)
| Strategy | Error Type | Root Cause | Prevention | Atomicity |
|----------|------------|------------|------------|-----------|
| Close blocked valid PRs | Decision error | Local timeout treated as product verdict | Preserve, wait, or escalate | 95% |
| Run ten PR workers against red main | Coordination error | Shared dependency not prioritized | Repair main before fan-out | 95% |
| Use API commit transports | Policy violation | Hook friction treated as transport problem | Use normal Git only | 95% |

### Near Misses
| What Almost Failed | Recovery | Learning |
|--------------------|----------|----------|
| Local work lost during mass sync | Backup branches and autostashes retained every state | Create recovery refs before worktree updates |
| Stale mutation markers blocked every push | Marker processes were verified dead and artifacts archived | Clear dead harness state before checkpoint pushes |

## Phase 3: Decisions

### Action Classification
| Action | Classification | Reason |
|--------|----------------|--------|
| Fix red main before PR fan-out | Add | Removes the shared merge blocker once |
| Close valid PRs on timeout | Drop | Destroys continuity without judging merit |
| Use API commit transport | Drop | Bypasses required repository hooks |
| Serialize checkpoint pushes | Keep | Reduces load and preserves branch ownership |

### SMART Validation
Future multi-PR runs will check required jobs on `main` before launching workers. If `main` is red, one worker owns repair. PR fan-out resumes only after the shared checks pass.

### Action Sequence
1. Check `main`.
2. Repair shared failures.
3. Sync each worktree.
4. Launch PR-specific workers.
5. Preserve and push WIP before stopping.

## Phase 4: Extracted Learnings

### Learning 1
- **Statement**: Fix red main before parallel pull request work.
- **Atomicity Score**: 95%
- **Evidence**: #5448 removed failures blocking every open pull request.
- **Skill Operation**: UPDATE
- **Target Skill ID**: pr-autofix

## Skillbook Updates

### ADD
```json
{
  "skill_id": "pr-autofix-main-first",
  "statement": "Fix red main before parallel pull request work.",
  "context": "Apply when multiple pull requests share a failing required check.",
  "evidence": "Session 2026-09-01, PR #5448",
  "atomicity": 95
}
```

### UPDATE

| Skill ID | Current | Proposed | Why |
|----------|---------|----------|-----|
| pr-autofix | Triage each PR independently | Stop fan-out when a required check is red on main | Prevent repeated blocked work |

### TAG

| Skill ID | Tag | Evidence | Impact |
|----------|-----|----------|--------|
| pr-autofix-main-first | coordination | #5448 | Removes shared blockers once |

### REMOVE

| Skill ID | Reason | Evidence |
|----------|--------|----------|
| close-on-local-timeout | Invalid product verdict | Reopened #5358, #5359, and #5364 |

## Deduplication Check

| New Skill | Most Similar | Similarity | Decision |
|-----------|--------------|------------|----------|
| pr-autofix-main-first | reproduce-on-main | 70% | Update PR workflow sequencing |

## Phase 5: Persist and Close

### Memory Persistence

| Learning | Atomicity | Existing Match | Result |
|----------|-----------|----------------|--------|
| Fix red main before parallel pull request work | 95% | PR workflow preference | Deduplicated |

### +/Delta

#### + Keep
- Recovery branches before mass worktree updates.
- One native WSL clone for hook-bound pushes.

#### Delta Change
- Stop all PR fan-out immediately when required checks are red on `main`.

### Delta Triage

#### Actionable Items Identified

| Delta Item | Category | Priority | Destination | Reference |
|------------|----------|----------|-------------|-----------|
| Main-first gate for pr-autofix | Process | P1 | Existing pr-autofix work | #5448 |

#### Issues Created

| Issue | Title | Priority | Labels |
|-------|-------|----------|--------|
| (none) | Existing workflow owns the change | (none) | (none) |

#### Backlog Items Stored

| Item | Priority | Memory File |
|------|----------|-------------|
| (none) | (none) | (none) |

#### Skipped Items

| Item | Reason |
|------|--------|
| New timeout issue | Current request is checkpoint and stop, not gate redesign |

### ROTI Assessment

**Score**: 1

**Benefits Received**:
- Shared main failure was repaired.
- Local work survived the correction and mass sync.

**Time Invested**: More than four hours

**Verdict**: Modify

### Helped, Hindered, Hypothesis

#### Helped
- Branch leases, recovery branches, and external worktrees preserved state.

#### Hindered
- Parallel workers amplified disk contention and repeated the same diagnosis.

#### Hypothesis
- A main-first gate will reduce PR-autofix wall time and token use by more than half.
