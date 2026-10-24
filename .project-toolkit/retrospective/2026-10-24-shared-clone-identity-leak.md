# Retrospective: shared-clone-identity-leak

## Session Info
- **Date**: 2026-10-24
- **Agents**: orchestrator, workflow agents for #6889, #6892, #6881, #6896, and the Codex sandbox eval harness
- **Task Type**: Bug
- **Outcome**: Partial

## Phase 0: Data Gathering

### 4-Step Debrief

**Observe.** All lines below were checked against git and GitHub on 2026-10-24 unless marked INFERRED.
- OBSERVED: commits `88e5131ec8` (branch `fix/6892-split-pool-collect-once`, 2026-10-23 21:51 -0700) and `692d424cd0` (branch `fix/implementer-authorized-guards`, 21:53 -0700) carry the author `T <t@example.com>`.
- OBSERVED: PR #6898 squash-merged as `31218cf53c`. The author is the real owner. The body ends with `Co-authored-by: T <t@example.com>` (`git log -1 --format=%B 31218cf53c`, lines 140 to 141 of the message).
- OBSERVED: PR #6900 is CLOSED unmerged. Replacement PR #6901 is MERGED as `4f83487d89` with the owner as author.
- OBSERVED: `scripts/github_core/placeholder_identity.py:24-28` leaves `*@example.com` off the denylist on purpose, so `filter_coauthor_trailers` does not strip this trailer.
- OBSERVED: PR #6902 is MERGED. It fixes a stray `/tmp/.git` that the Codex `workspace-write` sandbox created.
- INFERRED from the task brief, not re-measured: the `[user]` block sat in the shared `.git/config` from about 21:55 to 22:11 PDT. The config was clean when checked on 2026-10-24 (`git config --local --get-regexp '^user\.'` returned nothing).
- INFERRED: the first theory blamed `GIT_DIR` set by a pytest run for #6889. PR #6902 refuted it. The writer of the `[user]` block was never confirmed.

**Respond.** The polluting agent reported after the fact. The orchestrator planned a fresh branch with no force-push, which AGENTS.md forbids. That plan came after #6898 had merged. The orchestrator disabled auto-merge on #6900.

**Analyze.** Three layers each had a gap: the shared config was writable, commit authors were unchecked, and the trailer filter skipped `example.com`.

**Apply.** Two checks and one rule, listed in the learnings below.

### Execution Trace

| Time (PDT, 2026-10-23 unless noted) | Event | Evidence |
|------|-------|----------|
| 21:51 | Commit `88e5131ec8` authored as T | git log |
| 21:53 | Commit `692d424cd0` authored as T | git log |
| 21:55 to 22:11 | Identity block present in shared config | task brief (INFERRED) |
| 2026-10-24 05:06 UTC | #6898 merges as `31218cf53c` with the T trailer | git log |
| after | #6900 auto-merge disabled, #6900 closed | PR state |
| 2026-10-24 05:39 UTC | #6901 merges clean as `4f83487d89` | git log |

### Outcome Classification
- **Mad**: the T trailer is on main and cannot be removed without rewriting main.
- **Sad**: the report came after the merge. The owner decision on a gate has not been made.
- **Glad**: #6900 was caught before merge. #6901 merged clean. #6902 found the real writer.

## Phase 1: Insights Generated

### Five Whys

1. Why is a T trailer on main? #6898 auto-merged with commits authored as T.
2. Why did it auto-merge? No gate checks commit author email before merge.
3. Why did commits carry T? The shared `.git/config` held a `[user]` block and all worktrees read it.
4. Why was the block there? A test run wrote it. The exact writer is unconfirmed (INFERRED).
5. Why did nothing stop the write? Agents share one `.git/config`, and the placeholder denylist skips `example.com` to protect test fixtures.

Root cause: identity is trusted from local config, and no check compares author email to an allowlist at push or merge time.

### Fishbone
- **Tooling**: no author gate. The trailer filter exempts `example.com`.
- **Process**: the report came after the merge. The orchestrator relayed the plan too late.
- **Environment**: one `.git/config` shared across all linked worktrees.
- **Diagnosis**: the first theory (GIT_DIR) was wrong and cost attention.

### Patterns and Shifts
- Pattern: a mitigation existed but did not fire. `--commit-body` can omit a trailer, and the filter exists, yet neither ran on this path.
- Pattern: an agent labeled a PR blocked with the wrong cause (#6896).
- Pattern: an unprobed decision option was offered (#6884 D9). PR #6895 already records this, so it is not a new learning.

### Learning Matrix

| | Worked | Did not work |
|---|--------|--------------|
| Process | Orchestrator disabled auto-merge on #6900 | Report after merge |
| Tooling | `--commit-body` exists | No author gate, `example.com` exempt |

## Phase 2: Diagnosis

### Successes (Tag: helpful)
| Strategy | Evidence | Impact | Atomicity |
|----------|----------|--------|-----------|
| Disable auto-merge on a PR with a bad head, then replace the PR | #6900 CLOSED, #6901 MERGED `4f83487d89` | 8 | 75% |

### Failures (Tag: harmful)
| Strategy | Error Type | Root Cause | Prevention | Atomicity |
|----------|------------|------------|------------|-----------|
| Merge agent PRs without checking author emails | Process gap | No author check in the merge path | `git log --format='%an <%ae>' origin/main..HEAD` before merge | 75% |
| Run git or tests with GIT_DIR at the shared clone | Environment | One config shared by all worktrees | Never export GIT_DIR at the shared clone | 75% |
| Re-arm auto-merge only once | Tool behavior | A new push drops auto-merge armed with an expected head | Re-check `auto_merge` after each push | 75% |
| Label #6896 blocked:human on an advisory check | Misdiagnosis | One unresolved review thread was the real block | Count unresolved threads first | 75% |

### Near Misses
| What Almost Failed | Recovery | Learning |
|--------------------|----------|----------|
| #6900 had auto-merge armed on the bad head | Orchestrator disabled it, #6901 replaced it | Check authors before arming auto-merge |
| #6899 lost auto-merge after a push to `260042f462` (armed with `7b25903d3f`) | Re-armed, merged as `08cdb54477` | Re-arm after every push |

## Phase 3: Decisions

### Action Classification

| Action | Class |
|--------|-------|
| Keep: disable auto-merge on a bad head | Keep |
| Add: author-email check before merge (manual, memory) | Add |
| Add: never GIT_DIR at the shared clone (memory) | Add |
| Add: re-arm auto-merge after a push (memory) | Add |
| Modify: blocked-PR diagnosis adds a thread count step | Modify |

### SMART Validation
Each learning names one command or one field, one trigger, and one observed case. All four pass.

### Action Sequence
1. Write the memories (this PR).
2. Owner decides on the gate in the findings table below.

## Phase 4: Extracted Learnings

### Learning 1
- **Statement**: Agents never run git or tests with GIT_DIR pointed at the shared clone.
- **Atomicity Score**: 75%
- **Evidence**: Commits `88e5131ec8` and `692d424cd0` authored as T; `31218cf53c` body.
- **Skill Operation**: ADD
- **Target Skill ID**: git-a-stray-identity-in-the-shared-clone-config-reaches-main

### Learning 2
- **Statement**: Check git log author emails on origin/main..HEAD before merging an agent PR.
- **Atomicity Score**: 75%
- **Evidence**: `31218cf53c` merged with the T trailer; `placeholder_identity.py:24-28` exempts example.com.
- **Skill Operation**: ADD
- **Target Skill ID**: git-a-stray-identity-in-the-shared-clone-config-reaches-main

### Learning 3
- **Statement**: Re-arm auto-merge with merge_pr.py --auto --expected-head-sha after any push to the PR.
- **Atomicity Score**: 75%
- **Evidence**: PR #6899, push to `260042f462` after arming `7b25903d3f`.
- **Skill Operation**: ADD
- **Target Skill ID**: github-a-new-push-turns-off-auto-merge-armed-with-an-expected-head

### Learning 4
- **Statement**: Count unresolved review threads before labeling a PR blocked:human.
- **Atomicity Score**: 75%
- **Evidence**: #6896 was labeled on an advisory check; one unresolved thread was the block.
- **Skill Operation**: UPDATE
- **Target Skill ID**: diagnosing-a-blocked-pr

## Skillbook Updates

### ADD
```json
{
  "skill_id": "git-a-stray-identity-in-the-shared-clone-config-reaches-main",
  "statement": "Never export GIT_DIR at the shared clone, and check author emails before merging an agent PR.",
  "context": "Before merging any agent PR; before any agent test run in a worktree.",
  "evidence": "31218cf53c, 88e5131ec8, 692d424cd0",
  "atomicity": 75
}
```

```json
{
  "skill_id": "github-a-new-push-turns-off-auto-merge-armed-with-an-expected-head",
  "statement": "Re-arm auto-merge with the new head SHA after any push to an armed PR.",
  "context": "After each push to a PR armed with merge_pr.py --auto --expected-head-sha.",
  "evidence": "PR #6899, 260042f462",
  "atomicity": 75
}
```

### UPDATE

| Skill ID | Current | Proposed | Why |
|----------|---------|----------|-----|
| diagnosing-a-blocked-pr | Reads the ruleset, not mergeStateStatus | Adds an unresolved-thread count step before blocked:human | #6896 mislabel |

### TAG

| Skill ID | Tag | Evidence | Impact |
|----------|-----|----------|--------|
| none | | | |

### REMOVE

| Skill ID | Reason | Evidence |
|----------|--------|----------|
| none | | |

## Deduplication Check

| New Skill | Most Similar | Similarity | Decision |
|-----------|--------------|------------|----------|
| git-a-stray-identity-in-the-shared-clone-config-reaches-main | ci/git-dir-from-a-linked-worktree-push-outranks-git-c | Low (that file covers push hooks, not config pollution) | Add |
| github-a-new-push-turns-off-auto-merge-armed-with-an-expected-head | github-dismissed-reviews-block-automerge | Low (different cause) | Add |
| unprobed decision option (#6884 D9) | orchestrator-observations (PR #6895) | High | Skipped |

## Phase 5: Persist and Close

### Memory Persistence

| Learning | Atomicity | Existing Match | Result |
|----------|-----------|----------------|--------|
| Never GIT_DIR at the shared clone | 75% | none | Added |
| Check author emails before merging an agent PR | 75% | none | Added (same file) |
| Re-arm auto-merge after a push | 75% | none | Added |
| Count unresolved threads before blocked:human | 75% | diagnosing-a-blocked-pr | Updated |
| Probe lefthook before offering a decision option | n/a | orchestrator-observations | Deduplicated |

### +/Delta

#### + Keep
- Disabling auto-merge on the bad head saved #6900.
- Checking each claim against git before writing.

#### Delta Change
- Check author emails before arming auto-merge.
- Report a config pollution at once, not after the merge.

### Delta Triage

#### Actionable Items Identified

| Delta Item | Category |
|------------|----------|
| No author-email check at push or merge | Tool Gap |
| `example.com` is exempt from the placeholder denylist | Tool Gap |
| Agents share one writable `.git/config` | Process |

#### Findings for the owner

| Item | Evidence (path:line) | Proposed action | Class |
|------|----------------------|-----------------|-------|
| Commits with an unexpected author email reach main | `31218cf53c` body lines 140-141 | Candidate gate: refuse a push or merge whose commits carry an author email outside an allowlist | Optional enhancement |
| Trailer filter skips `example.com` | `scripts/github_core/placeholder_identity.py:24-28` | Decide whether the allowlist gate replaces the denylist exemption | Optional enhancement |
| Writer of the `[user]` block never confirmed | PR #6902 body | Owner decides whether to trace the writer | Side quest |

### ROTI Assessment

**Score**: 3

**Benefits Received**:
- Verified the leak chain against git.
- Found the denylist exemption that let the trailer pass.

**Time Invested**: one session

**Verdict**: Continue

### Helped, Hindered, Hypothesis

#### Helped
- `git log` and the PR context script gave exact SHAs and states.

#### Hindered
- Issues #6889, #6892, #6896, and #6884 are issues, not PRs, so the timeline of the 21:55 to 22:11 window rests on the task brief.

#### Hypothesis
- A pre-merge author check in the merge script would have stopped #6898.
