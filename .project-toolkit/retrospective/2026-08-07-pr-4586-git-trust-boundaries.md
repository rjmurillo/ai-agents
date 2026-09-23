# Retrospective: pr-4586-git-trust-boundaries

## Session Info

- **Date**: 2026-08-07
- **Agents**: GitHub Copilot CLI, GPT-5.6 Sol reviewer
- **Task Type**: Bug
- **Outcome**: Success

## Phase 0: Data Gathering

### 4-Step Debrief

- **Observe**: Exact head
  [`14cce29`](https://github.com/rjmurillo/ai-agents/commit/14cce29c07ad6d2890088d44776877245300600c)
  executed `core.fsmonitor` from repository, global, and system config.
  `HEAD^{tree}` and `HEAD:README.md` returned exit 3.
- **Respond**: Isolated every scanner Git invocation. Split raw object
  resolution, object verification, and commit peeling.
- **Analyze**: Both defects came from modeling Git behavior instead of probing
  its config and object contracts.
- **Apply**: Added exact-expression, sentinel, mixed-case environment,
  missing-object, and command-boundary tests.

### Execution Trace

1. Acquired the PR lease. Confirmed PR
   [#4586](https://github.com/rjmurillo/ai-agents/pull/4586) remained open.
2. Reproduced both defects in a detached worktree at exact remote head.
3. Fixed canonical source. Regenerated the Copilot mirror.
4. Added 33 focused tests and five behavior mutation controls.
5. GPT-5.6 Sol found one High missing-object classification defect.
6. Fixed the defect. Added a real missing-object Git regression.
7. Sol rereview returned `CLEAN`.
8. Committed the code as
   [`3ab2df4`](https://github.com/rjmurillo/ai-agents/commit/3ab2df4c4b577dd9e86d03c6cf258aa1a1b4b757).

### Outcome Classification

- **Glad**: Exact-head reproduction prevented a stale fix.
- **Glad**: Independent review found the missing-object edge before push.
- **Mad**: Scanner config isolation was mistakenly applied to the first push,
  which removed the configured credential helper.
- **Sad**: Full pytest cannot satisfy both repository-local temp policy and
  tests that require an external temp root.

### Impact

| Area | Severity | Evidence |
|------|----------|----------|
| Scanner command execution | High | Three Git config scopes executed sentinels |
| Exit-code contract | High | Two valid non-commit expressions returned exit 3 |
| Missing-object classification | High | First Sol review found the latent branch |
| Push workflow | Low | First push stopped before remote mutation |

## Phase 1: Insights Generated

### Five Whys: Config Execution

1. Why did scanner Git commands execute a sentinel? Git consulted
   `core.fsmonitor`.
2. Why could inherited config set it? The subprocess environment did not
   isolate system, global, and repository config.
3. Why was the boundary incomplete? The implementation treated read-only Git
   commands as inert.
4. Why did tests miss it? They did not install executable config in all three
   scopes.
5. Why did review accept it? The tests asserted output, not config side
   effects.

Root cause: failure mode 9, Confident-Incorrectness Recurrence. The scanner
claimed a Git trust boundary without probing Git's actual config behavior.

### Five Whys: Revision Classification

1. Why did tree and blob expressions return exit 3? Direct commit peeling
   failed.
2. Why did peeling failure mean external failure? One command represented
   both ref validity and commit type.
3. Why were those states combined? The raw object was never resolved and
   verified first.
4. Why did tests miss the distinction? They did not pass exact tree and blob
   expressions.
5. Why did the contract drift? The implementation modeled refs as commitish or
   invalid, omitting valid non-commit objects.

Root cause: failure mode 9, Confident-Incorrectness Recurrence. Exit semantics
were inferred instead of tested against Git object types.

### Fishbone

| Factor | Contribution |
|--------|--------------|
| Code | One commit-peel command collapsed three object states |
| Environment | Git config can execute `core.fsmonitor` from three scopes |
| Tests | No executable config sentinels or exact non-commit expressions |
| Review | Missing-object behavior needed a separate reviewer to surface |
| Workflow | Scanner-only isolation was copied to an operator push |

### Patterns and Shifts

- Git trust boundaries include environment, config, object replacement, and
  object type.
- Exit-code tests need exact user inputs, not derived object IDs.
- A control for untrusted subprocesses can break trusted operator commands.

### Learning Matrix

| Keep | Drop | Add | Modify |
|------|------|-----|--------|
| Exact-head reproduction | Read-only means inert | Executable config sentinels | Resolve, verify, then peel |
| Independent rereview | Scanner config on pushes | Real missing-object fixture | Close retrospective before push |

## Phase 2: Diagnosis

### Successes (Tag: helpful)

| Strategy | Evidence | Impact | Atomicity |
|----------|----------|--------|-----------|
| Detached exact-head reproduction | Both reported defects reproduced at `14cce29` | 10 | 100% |
| Independent Sol review | Found missing-object misclassification | 10 | 100% |
| Mutation controls | Five behavior mutants caught | 9 | 100% |

### Failures (Tag: harmful)

| Strategy | Error Type | Root Cause | Prevention | Atomicity |
|----------|------------|------------|------------|-----------|
| Treat read-only Git as inert | FM-9 | Config behavior inferred | Sentinel every config scope | 100% |
| Peel directly to commit | FM-9 | Object states collapsed | Resolve and verify raw object first | 100% |
| Isolate config during push | Boundary misuse | Scanner control copied to operator command | Preserve operator Git config | 100% |

### Near Misses

| What Almost Failed | Recovery | Learning |
|--------------------|----------|----------|
| Missing object returned exit 2 | Sol review plus real Git fixture | Verify object access before commit peel |
| Lease expired during long checks | Self-renewed before remote mutation | Renew while pre-push checks run |
| Credential helper removed | Retry with normal operator config | Keep scanner isolation local to scanner commands |

## Phase 3: Decisions

### Action Classification

| Class | Action | Owner | State |
|-------|--------|-------|-------|
| Keep | Exact-head gate and independent rereview | PR owner | Complete |
| Drop | Isolated config for operator push commands | PR owner | Complete |
| Add | Config-scope and exact-expression regressions | Doc-accuracy maintainers | Complete in `3ab2df4` |
| Modify | Revision checks to resolve, verify, then peel | Doc-accuracy maintainers | Complete in `3ab2df4` |
| Modify | Mark retrospective complete before final push | Session owner | Complete in this follow-up |

### SMART Validation

| Action | Specific | Measurable | Verified |
|--------|----------|------------|----------|
| Isolate scanner Git | Every scanner call uses one command builder | Command-boundary assertions cover every call | 83 tests passed |
| Classify revisions | Preserve exit 2 for non-commit refs and exit 3 for missing objects | Two exact expressions plus one missing-object fixture | 83 tests passed |
| Regenerate mirror | Canonical and Copilot scripts stay identical | `build_all.py --check` | Passed |

### Action Sequence

1. Reproduce at exact remote head. Complete.
2. Fix canonical source and regenerate the owned mirror. Complete.
3. Add focused tests and mutation controls. Complete.
4. Run independent review and repair High findings. Complete.
5. Record this retrospective and update session evidence. Complete.
6. Push normally after lease and exact-SHA gates. Pending.

## Phase 4: Extracted Learnings

### Learning 1

- **Statement**: Route every doc-accuracy Git subprocess through PR #4586's isolated command builder.
- **Atomicity Score**: 100%
- **Evidence**: Repository, global, and system sentinels executed at exact head.
- **Skill Operation**: TAG
- **Target Skill ID**: doc-accuracy

### Learning 2

- **Statement**: Classify non-commit revisions only after raw object resolution succeeds, as tested in PR #4586.
- **Atomicity Score**: 100%
- **Evidence**: `HEAD^{tree}`, `HEAD:README.md`, and a missing-object ref now diverge correctly.
- **Skill Operation**: TAG
- **Target Skill ID**: doc-accuracy

### Learning 3

- **Statement**: Use normal operator Git config for pushes; PR #4586 exposed credential loss.
- **Atomicity Score**: 100%
- **Evidence**: The isolated push could not read GitHub credentials and made no remote mutation.
- **Skill Operation**: TAG
- **Target Skill ID**: git-workflow-and-versioning

## Skillbook Updates

### ADD

None. Focused tests already encode the scanner contracts.

### UPDATE

| Skill ID | Current | Proposed | Why |
|----------|---------|----------|-----|
| None | None | None | No skill text change needed |

### TAG

| Skill ID | Tag | Evidence | Impact |
|----------|-----|----------|--------|
| doc-accuracy | git-config-isolation | PR #4586 config sentinels | Prevent executable inherited config |
| doc-accuracy | git-object-classification | PR #4586 exact expressions | Preserve exit-code contract |
| git-workflow-and-versioning | operator-config | PR #4586 failed authenticated push | Preserve credential helpers |

### REMOVE

| Skill ID | Reason | Evidence |
|----------|--------|----------|
| None | No obsolete skill found | PR #4586 |

## Deduplication Check

| New Skill | Most Similar | Similarity | Decision |
|-----------|--------------|------------|----------|
| Git config isolation | Focused doc-accuracy tests | Exact test coverage | Do not duplicate in memory |
| Revision classification | Focused doc-accuracy tests | Exact test coverage | Do not duplicate in memory |
| Operator push config | Existing Git credential configuration | Direct runtime evidence | Do not add a repository rule |

No Serena memory was added. Each repository behavior is re-derivable from the
focused tests in under one minute. The operator push behavior is not a
repository-wide convention.
