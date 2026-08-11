# Retrospective: skills-docs-p2

## Session Info

- **Date**: 2026-08-06
- **Agents**: GitHub Copilot CLI, GPT-5.6 Sol reviewer
- **Task Type**: Bug fix and contract completion
- **Outcome**: Success

## Phase 0: Data Gathering

### Evidence

| Source | Evidence |
|---|---|
| Session log | `.agents/sessions/2026-08-05-session-10002-revalidate-ship-skills-docs-fixes.json` |
| Pull request | PR #4673 |
| Issues | #4364, #4378, #4381, #4498, #4511 |
| Final code before latest main | `22a5fe95a` |
| Latest main merge | `75d8ee3ec` |
| Final test run | 23,734 passed, 33 skipped |
| Final review | GPT-5.6 Sol returned ZERO FINDINGS |

### 4-Step Debrief

- **Observe**: Prior fixes passed focused tests but repeated adversarial review found untested boundary classes.
- **Respond**: Fixed each merited finding, added a discriminating test, ran a killing mutation, regenerated mirrors, and re-reviewed the new HEAD.
- **Analyze**: The implementation was correct on reported examples but incomplete across equivalent boundary inputs such as equals-form options, repeated cursors, non-finite numbers, and symlink escapes.
- **Apply**: Build boundary matrices before implementation and rerun review after every artifact change or main merge.

### Execution Trace

1. Re-read issue and PR discourse, including linked work.
2. Merged current main and reproduced the open issue state.
3. Verified legacy fields, actor IDs, pagination, build arguments, and rename behavior.
4. Ran focused and full tests, Ruff, mypy, drift, live GraphQL, and mutations.
5. Iterated Sol review findings until the reviewer returned zero findings.
6. Split #4381 documentation to remain under the 50-file PR limit.
7. Created PR #4673, applied the commit-limit labels, and merged newer main.
8. Re-ran 23,734 tests, pre_pr 46 of 46, and final Sol review.

### Outcome Classification

- **Glad**: All requested contracts now have positive, negative, edge, and mutation evidence.
- **Sad**: Review started too late to expose the full boundary matrix before implementation.
- **Mad**: The portability baseline writer still leaves one unignored lock, so #4511 was reopened.

## Phase 1: Insights Generated

### Five Whys

1. Why did review require several remediation passes? Each pass found another boundary input with the same failure shape.
2. Why were those inputs absent? Tests followed the reported examples rather than enumerating the whole input grammar and failure state machine.
3. Why was the grammar not enumerated? The task combined CLI parsing, Git history, pagination, identity, path security, and generated mirrors.
4. Why did the combination matter? Each subsystem had a different fail-closed contract, but the first test plan treated them as one happy-path feature.
5. Why did this survive earlier validation? Deterministic gates prove implemented assertions, not missing assertions.

**Root cause**: No explicit boundary matrix existed before implementation. Review became the discovery mechanism for missing requirements.

### Fishbone Analysis

| Area | Contributor |
|---|---|
| Inputs | Separated, equals-form, abbreviated, repeated, malformed, non-finite, and symlink inputs differed in behavior. |
| External APIs | REST warnings and GraphQL partial shapes could look successful. |
| Git | Renames, unrelated histories, deletion-only diffs, and operational failures need separate outcomes. |
| Compatibility | Legacy author fields and additive identity fields served different consumers. |
| Process | Main moved during the run, and each merge changed the artifact under review. |

### Patterns and Shifts

- Shift from example tests to boundary-class tests.
- Shift from one review at the end to review after every final artifact mutation.
- Shift from pagination count checks to completeness-state checks.

## Phase 2: Diagnosis

### Successes

| Strategy | Evidence | Impact | Atomicity |
|---|---|---:|---:|
| Mutation per finding | 21 mutants died and five controls survived | 9/10 | 90% |
| Final review on exact HEAD | Sol returned ZERO FINDINGS after latest main | 9/10 | 90% |
| Canonical generation | `build_all --check` and mirror tests passed | 8/10 | 85% |

### Failures

| Strategy | Error Type | Root Cause | Prevention | Atomicity |
|---|---|---|---|---:|
| Example-led test plan | Missing boundary cases | No input matrix | List every accepted syntax and failure state first | 90% |
| Early completion claims | Artifact changed afterward | Review evidence bound to an older HEAD | Record and review the exact final SHA | 95% |

### Near Misses

| What Almost Failed | Recovery | Learning |
|---|---|---|
| Partial pages emitted success | Warning promotion and connection validation | Completeness is data, not an assumption. |
| Path prefix check allowed escape | `Path.resolve().relative_to()` | Lexical prefixes are not containment. |
| First final push failed | Retrospective gate exposed missing evidence | Run push-policy prerequisites before the first final push. |
| Shallow CI lacked a historical test SHA | Replaced the duplicate history-dependent test with synthetic rename coverage | Regression tests must create their own Git history. |

## Phase 3: Decisions

### Action Classification

| Class | Action |
|---|---|
| Keep | Independent review plus deterministic mutation evidence. |
| Drop | Treating one passing example as proof of the input class. |
| Add | Boundary matrix for CLI syntax, API pagination, Git states, and paths. |
| Modify | Bind validation and review evidence to the final merged HEAD. |

### SMART Validation

| Action | Specific | Measurable | Achievable | Relevant | Time-bound |
|---|---|---|---|---|---|
| Add boundary matrix | Name each input and failure class | One test and mutant per class | Uses existing pytest harness | Prevents silent pass paths | Before implementation commit |
| Review exact HEAD | Pass final SHA to reviewer | ZERO FINDINGS on that SHA | Existing task tool | Prevents stale review evidence | After last merge or edit |

### Action Sequence

1. Enumerate boundary classes.
2. Implement one class at a time with tests.
3. Run targeted mutations.
4. Regenerate mirrors.
5. Merge current main.
6. Run full gates.
7. Review exact HEAD.
8. Push and verify CI.

## Phase 4: Extracted Learnings

### Learning 1

- **Statement**: When `gh_api_paginated` warns that a page is partial, an inventory CLI must exit 3 before emitting success.
- **Atomicity Score**: 95%
- **Evidence**: `get_pr_reviewers.py` and `get_pr_comments_by_reviewer.py`; mutations M2 and M7.
- **Skill Operation**: TAG
- **Target Skill ID**: github pagination completeness

### Learning 2

- **Statement**: Use `Path.resolve().relative_to(workspace)` for CLI workspace containment; string prefixes do not prove containment.
- **Atomicity Score**: 95%
- **Evidence**: `assess.py`; sibling-prefix and symlink tests; mutation M16.
- **Skill Operation**: TAG
- **Target Skill ID**: security path containment

### Learning 3

- **Statement**: After the artifact changes or main merges, rerun deterministic gates and independent review against the new HEAD.
- **Atomicity Score**: 90%
- **Evidence**: Main merges `bbd321624` and `75d8ee3ec`; final review on latest HEAD returned zero findings.
- **Skill Operation**: TAG
- **Target Skill ID**: final artifact review

## Skillbook Updates

No new memory file was added. Each learning already has a binding source in code, tests, or repository rules. Adding a second memory copy would duplicate knowledge and create drift.

## Deduplication Check

| Learning | Existing owner | Decision |
|---|---|---|
| Pagination completeness | GitHub scripts and tests | TAG existing contract |
| Path containment | Python boundary code and security rules | TAG existing contract |
| Review exact HEAD | Adversarial review policy and session evidence | TAG existing contract |

## Phase 5: Persist and Close

- **Persistence**: Code, tests, issue #4511, PR #4673, and this artifact hold the evidence.
- **Plus**: Mutation evidence made every fix falsifiable.
- **Delta**: Boundary discovery should happen before implementation, not in repeated final reviews.
- **ROTI**: 4/5. The final result is clean, but late boundary discovery added several full-suite cycles.
- **Helped**: Exact tool output, full discourse, live GraphQL, generated mirrors, and independent review.
- **Hindered**: Moving main, REST secondary limits, first-push commit relief, and retrospective gating at push time.
- **Hypothesis**: A boundary matrix at task start cuts review remediation passes by at least half on the next cross-contract change.
