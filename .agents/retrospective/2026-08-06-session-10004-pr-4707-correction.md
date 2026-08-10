# Retrospective: 2026-08-06-session-10004-pr-4707-correction

## Session Info
- **Date**: 2026-08-06
- **Agents**: Copilot CLI, GPT-5.6 Sol reviewer
- **Task Type**: Bug
- **Outcome**: Partial

## Phase 0: Data Gathering
**4-Step Debrief**

- Observe: Exact PR head `13f411b69a933bc17a59ca04ee9cc29d2a214d68`
  reproduced all three High findings. Commit
  `1a81fc3b6f447b0034022044d737eb59af865628` fixed them.
- Respond: Preserved both push logs, ran the same 15 failures on exact head,
  used the external-root pytest runner, and used no hook bypass.
- Analyze: The correction was sound. Repository-local pytest roots and
  incomplete session evidence independently blocked delivery.
- Apply: Reproduce on the exact reviewed SHA, keep pytest roots outside every
  repository, and finish session evidence before the final push.

**Execution Trace**

1. `13f411b69a933bc17a59ca04ee9cc29d2a214d68` failed five focused probes.
2. `1a81fc3b6f447b0034022044d737eb59af865628` passed 135 targeted tests and
   the memory corpus checks.
3. The first push failed 15 tests after pytest used a repository-local root.
4. Exact `13f411b69a933bc17a59ca04ee9cc29d2a214d68` failed the same 15 tests.
5. Both SHAs passed all 15 through `scripts/ci/run_pytest_non_tmp.py`.
6. Stale ignored fixtures exposed a second scanner defect. Evidence was added
   to [Issue #4657](https://github.com/rjmurillo/ai-agents/issues/4657#issuecomment-5212254853).
7. The next push reached `retrospective-policy`, which found session 10004
   incomplete.

**Outcome Classification**

- Glad: Exact-head controls separated code defects from environment failures.
- Sad: Two full hook cycles ran before session evidence was complete.
- Mad: A test claiming to scan `tests/` resolved its root to the repository.

## Phase 1: Insights Generated
**Five Whys: repository-local pytest failures**

1. Why did 15 tests fail? Their temporary paths were inside a Git repository.
2. Why were those paths inside the repository? The push used `.pytest_tmp`.
3. Why did location matter? The tests assert behavior outside every repository.
4. Why did targeted validation miss this? Memory-index tests do not exercise
   repository-location contracts.
5. Why did a later scanner fail too? Ignored binary fixtures remained under
   the repository and the scanner walked the repository root.

Root cause: the full suite requires an external pytest root, while broad
scanners must not consume ignored test artifacts.

**Five Whys: retrospective gate**

1. Why did the retry stop? `retrospective-policy` found no completed evidence.
2. Why was evidence absent? Session 10004 recorded retrospective as incomplete.
3. Why was it still incomplete? The correction resumed without closing the
   original session workflow.
4. Why did this surface late? The policy runs at pre-push.
5. Why did the push start first? Session evidence was treated as cleanup
   instead of a delivery prerequisite.

Root cause: session completion was sequenced after the final delivery gate.

**Fishbone**

- Environment: pytest root was inside the checkout.
- Process: retrospective evidence was deferred.
- Tooling: one scanner walked ignored repository artifacts.
- State: stale fixtures survived the failed push.

**Patterns and Shifts**

- Exact PR snapshots and live branch heads answer different questions.
- Negative controls distinguish branch regressions from inherited failures.
- Parallel hooks can reveal several independent blockers in one push.

**Learning Matrix**

| Keep | Drop | Add | Modify |
|------|------|-----|--------|
| Exact-SHA probes | Repo-local full-suite temp roots | Session close before push | Issue #4657 scanner scope |

## Phase 2: Diagnosis

Failure mode classification: FM-4, False Completion Markers, near miss. Remote
SHA verification prevented a local validation message from being reported as
a successful push.

### Successes (Tag: helpful)
| Strategy | Evidence | Impact | Atomicity |
|----------|----------|--------|-----------|
| Exact-head reproduction | Five probes failed on `13f411b69` | 10 | 90% |
| Negative control | The same 15 tests failed on exact head | 10 | 90% |
| External-root control | Both SHAs passed 15 of 15 tests | 9 | 88% |
| Separate review | GPT-5.6 Sol reported no Critical or High findings | 8 | 82% |

### Failures (Tag: harmful)
| Strategy | Error Type | Root Cause | Prevention | Atomicity |
|----------|------------|------------|------------|-----------|
| Repository-local pytest root | Environment mismatch | Temp paths violated test premises | Use `PYTEST_NON_TMP_ROOT` outside the checkout | 88% |
| Deferred session close | Workflow sequencing | Evidence followed the push attempt | Run retrospective and session-end before push | 90% |

### Near Misses
| What Almost Failed | Recovery | Learning |
|--------------------|----------|----------|
| Baseline failures attributed to correction | Exact-head negative control | Compare the same test set on both SHAs |
| Ignored binary fixture blocked every push | Moved fixture tree outside checkout and linked #4657 | Ignored files still affect filesystem scanners |
| Local success mistaken for delivery | Compared `ls-remote` with local HEAD | Remote SHA is the delivery proof |

## Phase 3: Decisions

### Action Classification
| Class | Decision | Evidence |
|-------|----------|----------|
| Keep | Exact-head reproduction and negative controls | Five probes and 15-test control |
| Drop | Repository-local roots for the full suite | Fifteen location-sensitive failures |
| Add | Retrospective before the final push | `retrospective-policy` failure |
| Modify | Expand Issue #4657 with the second scanner | Linked issue comment |

### SMART Validation
| Learning | Specific | Measurable | Achievable | Relevant | Time-bound |
|----------|----------|------------|------------|----------|------------|
| Exact-head control | Names both SHAs and test set | Same failures on both | Existing worktrees suffice | Prevents wrong attribution | Before code changes |
| External pytest root | Names required runner and root location | 15 of 15 pass | Existing script suffices | Prevents false suite reds | Before full suite |
| Session evidence first | Names retrospective and session-end | Both artifacts validate | Existing skills suffice | Prevents late push block | Before final push |

### Action Sequence
1. Generate this retrospective with the repository workflow.
2. Record completion through the session owner tool.
3. Validate the session log and generated episode.
4. Commit the retrospective and session artifacts with the correction branch.

## Phase 4: Extracted Learnings

### Learning 1
- **Statement**: Run exact-head negative controls before attributing review findings to a correction.
- **Atomicity Score**: 75% (Good)
- **Evidence**: The same 15 failures reproduced on exact `13f411b69`.
- **Skill Operation**: TAG
- **Target Skill ID**: ai-agents-debugging-playbook

### Learning 2
- **Statement**: Use external pytest roots when tests assert behavior outside every repository.
- **Atomicity Score**: 75% (Good)
- **Evidence**: Both SHAs passed 15 of 15 through `run_pytest_non_tmp.py`.
- **Skill Operation**: TAG
- **Target Skill ID**: testing

### Learning 3
- **Statement**: Complete session evidence before starting the final pre-push hook.
- **Atomicity Score**: 75% (Good)
- **Evidence**: `retrospective-policy` blocked after code validation had passed.
- **Skill Operation**: TAG
- **Target Skill ID**: session-end

## Skillbook Updates

### ADD
```json
[]
```

### UPDATE

| Skill ID | Current | Proposed | Why |
|----------|---------|----------|-----|
| None | Existing rules cover all learnings | No text change | Avoid duplicate guidance |

### TAG

| Skill ID | Tag | Evidence | Impact |
|----------|-----|----------|--------|
| ai-agents-debugging-playbook | exact-head-control | 15-test negative control | Prevents wrong attribution |
| testing | external-pytest-root | 15 of 15 passed externally | Prevents location false failures |
| session-end | evidence-before-push | Retrospective gate block | Prevents late delivery blocks |

### REMOVE

| Skill ID | Reason | Evidence |
|----------|--------|----------|
| None | No obsolete skill found | Deduplication review |

## Deduplication Check

| New Skill | Most Similar | Similarity | Decision |
|-----------|--------------|------------|----------|
| Exact-head negative control | ai-agents-debugging-playbook | High | Do not duplicate |
| External pytest root | `.claude/rules/testing.md` | High | Do not duplicate |
| Session evidence first | session-end | High | Do not duplicate |

## Review Correction: 2026-08-07

PR #4735 tracks the four Action Sequence items above. Copilot CLI owns each
item until the replacement branch is pushed and all review threads resolve.
