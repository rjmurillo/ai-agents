# Retrospective: pr5343-round-cap-handoff

## Session Info

- **Date**: 2026-09-01
- **Agents**: Claude Code (Claude Sonnet 5)
- **Task Type**: Bug

Task: take over PR #5343 (`claude/fix-4632-build-all-check-fails-open`) after
`pr-autofix`'s round-cap breaker tripped (6 rounds recorded, cap 5; 9.3h wall
clock, cap 4.0h) and explicitly asked for human or session review.

## Failure Mode Classification

`.agents/governance/FAILURE-MODES.md` class 4, **False Completion Markers**
(High). Both findings below are the shape that class names: "PR description
asserts behavior the test suite does not exercise", and success reported
without verification against an artifact.

- The signature mismatch shipped in a commit whose message claimed the fix,
  pushed without running the suite it broke.
- The two boundary-mocking tests advertised coverage of the `except OSError`
  translation in `_strict_owned_stat` and `_strict_owned_children` while
  never reaching either handler, so the PR's stated regression evidence did
  not hold.

No new class is proposed. Class 4's detection bullets already cover both, so
the gap is enforcement, not taxonomy.

## Phase 0: Data Gathering

The round-cap breaker comment named no specific failure, only that automated
work had stopped. `Run Python Tests` was red on the PR's head commit
(`a8784605e`), and five Copilot review comments had landed against that same
commit within the prior few minutes.

**Outcome classification**: partial success. The task (unblock the PR) was
completed, and both defects were caught before merge rather than after.

## Phase 1: Insights Generated

### Finding: a production signature change landed without updating its own test's mock

`a8784605e` added a keyword-only `missing_root_ok` parameter to
`_strict_owned_stat` in `build/scripts/build_all.py`, but
`test_run_check_aborts_before_generation_when_owned_file_stat_fails` still
monkeypatched it with a two-positional-argument stub
(`flaky_strict_owned_stat(path: Path)`). The mismatch is a `TypeError` at
call time, not a logic disagreement, so it failed loudly in CI
(`pytest (bulk-nested)`, `Run Python Tests`) rather than passing for the
wrong reason: `FAILED
test_run_check_aborts_before_generation_when_owned_file_stat_fails -
TypeError: ... got an unexpected keyword argument 'missing_root_ok'`.

`.claude/rules/testing.md` SHOULD-4 names exactly this obligation: "grep for
tests asserting old contracts... and flip them in the same diff".

### Finding: two tests mocked above the boundary they meant to prove

Both `test_run_check_aborts_before_generation_when_owned_file_stat_fails`
and its directory-scan sibling replaced `_strict_owned_stat` and
`_strict_owned_children` outright with a stub that raised the already
wrapped `SnapshotIncompleteError`, rather than raising a raw `OSError` at
the real I/O boundary (`Path.stat`, `os.scandir`) and letting production
code perform the wrapping. Copilot's review caught this precisely: deleting
the `except OSError` translation in either real function would leave both
tests green, because neither test's code path ever reaches it.

Caught by review before merge, not after. Rewriting both tests to fail at
the true I/O boundary closes the gap `.claude/rules/testing.md` SHOULD-6
describes: "prove the wiring, not only the guard".

### Five whys: why did a red commit reach the remote

1. Why was the branch red? A test stub did not match the production
   signature the same commit introduced.
2. Why did the author not see it? The suite was not run before the push.
3. Why was it not run? The session pushed under time pressure near the
   round-cap wall clock.
4. Why did the push succeed anyway? Not established. A pre-push
   `python-tests` job does exist and is not diff-scoped by a `glob`
   (`lefthook.yml`, `name: python-tests`, running
   `git_hook_policy.py pytest`), and `git show a8784605e:lefthook.yml`
   confirms it was already wired at that commit, so "pre-push does not run
   the suite" is false. What the available artifacts do not show is why it
   did not block. Two candidates: `run_pytest` narrows through
   `_resolve_pytest_commands(repo_root, changed_files)`, which is the local
   selector disagreement issue #5318 tracks, or the hook did not run in that
   session's environment. This session had neither the push transcript nor
   the hook log, so the mechanism is named as open rather than guessed.
5. Why did a second session not catch it first? Neither session held the
   `pr-autofix` lease at push time, so both were editing the same branch
   without knowing.

Why 4 is deliberately left unresolved. An earlier draft of this retro
asserted that pre-push runs only lint and ratchets. That was wrong, and a
prevention aimed at a mechanism that does not exist would have been worse
than an open question.

## Phase 2: Diagnosis

### Successes (Tag: helpful)

| Strategy | Evidence | Impact | Atomicity |
|----------|----------|--------|-----------|
| Read CI red before reading review comments | Located the `TypeError` in one step instead of triaging five comments first | 8 | 90% |
| Use a negative control per rewritten test | Reverting `_queue_strict_owned_path` to a no-op made the rewritten stat test fail as expected, proving the test reaches the handler | 9 | 95% |
| Fix the mypy finding at the assert rather than by widening the type | One line, and it states the invariant `missing_root_ok=False` guarantees | 6 | 85% |

### Failures (Tag: harmful)

| Strategy | Error Type | Root Cause | Prevention | Atomicity |
|----------|------------|------------|------------|-----------|
| Push without running the suite the change touched | False completion | Time pressure near the round-cap wall clock. The pre-push `python-tests` job exists and should have caught it, so why it did not is an open question, not a known absence | Run the touched suite yourself before every push, and treat a green pre-push as corroboration rather than proof | 85% |
| Replace the function under test with a stub that raises the wrapped error | Test proves nothing | Mocking above the I/O boundary, so production's translation never runs | Raise the raw error at the real boundary and let production wrap it | 95% |
| Change a signature without grepping for stand-ins of the same function | Contract drift | Callers were checked, test doubles were not | Treat a test double as a caller when a signature changes | 90% |

### Near Misses

| What Almost Failed | Recovery | Learning |
|--------------------|----------|----------|
| Two tests would have passed against a version with the error translation deleted | Copilot review named the exact handler and the exact mutation | A green suite is not evidence that the guard under it is load bearing |
| A second concurrent session was editing the same branch | The round-cap breaker stopped automated work before the two diverged further | The lease is only useful if it is held at push time |

## Phase 3: Decisions

### Action Classification

| Action | Classification | Detail |
|--------|----------------|--------|
| Negative control per guard-bearing test | Keep | Already proved its worth twice in this session |
| Mock at the real I/O boundary | Modify | Was "mock the helper"; now "raise the raw error where production catches it" |
| Run the touched suite before pushing | Add | The pre-push `python-tests` job did not block this commit, and until that is explained an author-run suite is the only check under the author's control |
| Re-acquire the `pr-autofix` lease immediately before pushing | Add | Neither session held it, and `renew` does not extend `expires_at` |
| Derive the fix from the review comment alone | Drop | The comment named a symptom; the handler and its caller had to be read |

### SMART Validation

- "Run the touched suite before pushing" is specific (the suite covering the
  changed module), measurable (exit code), achievable (2 to 5 seconds for
  `test_build_all.py`), relevant (this failure), time-bound (before each push).
  It does not replace the pre-push `python-tests` job; it is the check the
  author controls while that job's miss is unexplained.
- "Re-acquire the lease immediately before pushing" is specific (an `acquire`
  call, not `renew`), measurable (the returned action field), achievable (one
  call), relevant (the concurrent-session finding), time-bound (per push).

### Action Sequence

1. Rewrite both tests to fail at the real I/O boundary (no dependencies).
2. Add the `assert metadata is not None` for the mypy finding (no dependencies).
3. Correct the diagnostics skill's exit-code table and regenerate the mirror
   (depends on 1 and 2 landing so the branch is green first).
4. File the lease-at-push-time gap as a tracked issue (independent).

## Phase 4: Extracted Learnings

### Learning 1

- **Statement**: A test that stubs the function under test cannot kill mutants inside it.
- **Atomicity Score**: 95%
- **Evidence**: Deleting the `except OSError` bodies in `_strict_owned_stat` and `_strict_owned_children` left both advertised regressions green.
- **Skill Operation**: TAG
- **Target Skill ID**: `.claude/rules/testing.md` SHOULD-6

### Learning 2

- **Statement**: A signature change must flip every test double of that function.
- **Atomicity Score**: 90%
- **Evidence**: `a8784605e` added `missing_root_ok` and left a two-positional stub, producing a `TypeError` in CI.
- **Skill Operation**: TAG
- **Target Skill ID**: `.claude/rules/testing.md` SHOULD-4

### Learning 3

- **Statement**: A lease held at first mutation is not held at push time.
- **Atomicity Score**: 90%
- **Evidence**: Two concurrent sessions pushed to this branch in one window; the 15 minute TTL lapses during local work and `renew` does not extend `expires_at`.
- **Skill Operation**: ADD
- **Target Skill ID**: n/a

## Skillbook Updates

### ADD

```json
{
  "skill_id": "pr-autofix-lease-at-push-time",
  "statement": "Re-acquire the pr-autofix lease immediately before pushing, not only before the first mutation.",
  "context": "Any pr-autofix session whose local work can outlast the 15 minute lease TTL.",
  "evidence": "PR #5343: two concurrent sessions pushed in one window, one of them red. Issue #5486.",
  "atomicity": 90
}
```

### UPDATE

| Skill ID | Current | Proposed | Why |
|----------|---------|----------|-----|
| none | | | Both testing learnings restate rules that already exist verbatim, so rewording them would be churn |

### TAG

| Skill ID | Tag | Evidence | Impact |
|----------|-----|----------|--------|
| `.claude/rules/testing.md` SHOULD-6 | helpful | Review caught two tests that mocked above the boundary, which the rule already forbids | The rule is correct and was not followed, so enforcement is the gap |
| `.claude/rules/testing.md` SHOULD-4 | helpful | The `missing_root_ok` stub drift is the exact case the rule names | Same shape: correct rule, missed application |

### REMOVE

| Skill ID | Reason | Evidence |
|----------|--------|----------|
| none | No strategy in this session was harmful enough to remove | Both failures were omissions of existing rules, not bad rules |

## Deduplication Check

| New Skill | Most Similar | Similarity | Decision |
|-----------|--------------|------------|----------|
| Mock at the real I/O boundary | `.claude/rules/testing.md` SHOULD-6 | High | Deduplicated. Tag the existing rule rather than add |
| Flip test doubles on a signature change | `.claude/rules/testing.md` SHOULD-4 | High | Deduplicated. Tag the existing rule rather than add |
| Hold the lease at push time | `.claude/commands/pr-autofix.md` lease steps | Low | Added. The command documents acquiring, not re-acquiring before the push |

## Phase 5: Persist and Close

### Memory Persistence

| Learning | Atomicity | Existing Match | Result |
|----------|-----------|----------------|--------|
| A test that stubs the function under test cannot kill mutants inside it | 95% | `.claude/rules/testing.md` SHOULD-6 | Deduplicated |
| A signature change must flip every test double of that function | 90% | `.claude/rules/testing.md` SHOULD-4 | Deduplicated |
| A lease held at first mutation is not held at push time | 90% | none | Added, as issue #5486 rather than a memory |

`.claude/rules/knowledge-persistence.md` decides the surface. The first two are
already expressed in a rule file, so a memory would create drift. The third must
bind every session running `pr-autofix`, which is a rule or issue obligation,
not a retrieval aid.

### +/Delta

#### + Keep

- Reading CI red before the review comments located the defect in one step.
- Every rewritten test got a negative control in the same session.

#### Delta Change

- Run the suite covering the touched module before pushing, not after.
- Re-acquire the `pr-autofix` lease immediately before the push.

### Delta Triage

#### Actionable Items Identified

| Delta Item | Category | Priority | Destination | Reference |
|------------|----------|----------|-------------|-----------|
| Lease not held at push time, two sessions pushed to one branch | Process | P1 | Issue #5486 | <https://github.com/rjmurillo/ai-agents/issues/5486> |
| Unpushed commits from an escalated round-cap session reused unverified | Process | P1 | Issue #5447 | <https://github.com/rjmurillo/ai-agents/issues/5447> |
| Pre-push `python-tests` did not block a red commit, mechanism unestablished | Process | P1 | Issue #5318 | <https://github.com/rjmurillo/ai-agents/issues/5318> |

#### Issues Created

| Issue | Title | Priority | Labels |
|-------|-------|----------|--------|
| #5486 | pr-autofix: hold the lease at push time, not only at first mutation | P1 | enhancement |

#### Backlog Items Stored

| Item | Priority | Memory File |
|------|----------|-------------|
| none | | Both P1 items became issues, and the P2 item was skipped as already covered |

#### Skipped Items

| Item | Reason |
|------|--------|
| none | The earlier draft skipped the pre-push question on the grounds that `pre_pr.py` covered it. It does not: its own success path prints that it "has no visibility into sibling jobs (python-tests, ratchets)" when it runs as a lefthook job. The row is now open against issue #5318 |

### ROTI Assessment

**Score**: 3

**Benefits Received**:

- Two tests that proved nothing now fail against the mutation they exist to catch.
- A concurrency gap that had already produced one red push is tracked as issue #5486 rather than living as a session observation.

**Time Invested**: about 1 hour

**Verdict**: Continue

### Helped, Hindered, Hypothesis

#### Helped

- Copilot's review named the exact handler and the exact mutation, which made the negative control obvious to construct.
- CI red pointed at one commit, so the timeline was short.

#### Hindered

- A concurrent session editing the same branch made the git history hard to attribute while the work was in flight.
- The round-cap comment named no specific failure, so Phase 0 started from scratch.

#### Hypothesis

- If a session re-acquires the lease immediately before pushing, the two-sessions-one-branch pattern that produced the red commit cannot recur. Issue #5486 is the experiment.

## Process Observation

This is the second time in one session that a fix landed on this same PR
mid-flight from a different concurrent `pr-autofix` session, without either
session holding a lease at push time. The round-cap breaker is a useful
backstop, since it stopped automated work rather than looping past the cap,
but nothing prevented the commit that tripped it from shipping a real CI
regression in the first place.

Issue #5447 does not cover this. Its scope is commits an escalated session
left **unpushed**. The commits here **were** pushed, by a session whose lease
had lapsed.
