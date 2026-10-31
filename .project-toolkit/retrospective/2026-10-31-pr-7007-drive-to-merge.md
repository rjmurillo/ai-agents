# Retrospective: pr-7007-drive-to-merge

## Session Info
- **Date**: 2026-10-31
- **Agents**: orchestrating session only (autoplan, github-url-intercept, pr-review skills); no subagents
- **Task Type**: Bug
- **Outcome**: Success

## Phase 0: Data Gathering

### 4-Step Debrief

**Observe.** Every line below was checked against git or GitHub during the session.
- OBSERVED: PR #7007 started CONFLICTING, with `Validate PR` and `Devin Review` red and 3 unresolved owner threads.
- OBSERVED: `Validate PR` failed with `File mentioned but not in diff File: build_all.py`. The body named `build_all.py` and `generate_agents.py` under `## Changes`.
- OBSERVED: the only merge conflict was the generated `.agents/governance/agent-source-divergence.json`.
- OBSERVED: all 3 threads reported damage from the reference scrub. Two were stray punctuation (`sync.SKILL.md.tmpl:31` began with `,`; `pr-autofix.SKILL.md.tmpl:942` began with `#.`). One was a verify command that no longer hit its cited line.
- OBSERVED: a pytest call over 58 files collected 0 items. The file list sat in an unquoted zsh variable.
- OBSERVED: the merged PR's report said the remote branch "still exists". `git ls-remote` then returned nothing. The repo has `delete_branch_on_merge: true`.
- OBSERVED: six `Smoke` jobs and two other non-required jobs were WAITING at merge. The user denied a `pending_deployments` lookup.

**Respond.** Merged `origin/main` instead of rebasing, so no force-push. Took main's pin file and re-recorded pins. Fixed the 3 threads in one commit. Validated the new PR body locally, with the old body as a negative control. Merged pinned to the head SHA.

**Analyze.** Two defects came from the earlier session that wrote the PR: scrub damage and a body that named unchanged files. Two errors came from this session: the zsh split and the false remote-branch claim. Memory already held the fix for all three process errors.

**Apply.** One new learning on scrub damage. Three recurrences tagged on existing memories.

### Execution Trace

| Time (UTC, 2026-10-31) | Event | Evidence |
|------|-------|----------|
| 07:30 | `Validate PR` fails on `e0e9ee28ca` | check run 41180761696 |
| 15:17 | PR context read; route set to `pr-review` | `get_pr_context.py` output |
| 15:18 | Config trust exit 0; transport `gh`; 3 threads, 0 clusters | `run_completion_gate.py --verify-config-only`, `cluster_threads.py` |
| ~15:19 | Merge commit `dc86b21d76` with 109 re-recorded pins | git log |
| ~15:20 | pytest collects 0 items; rerun with xargs passes 2640, skips 1 | pytest output |
| ~15:20 | Fix commit `738d5dbbae` | git log |
| 15:20 | PR body edited after local validator check | `edit_pr_body.py` result |
| ~15:22 | Push lands `e0e9ee28ca..738d5dbbae` | push log |
| 15:23 | 3 threads replied to and resolved | `add_pr_review_thread_reply.py` |
| ~15:30 | Settle check exit 0; gate exit 1 on branch protection only | gate JSON |
| 15:34 | Squash merge `78e8145660` | `merge_pr.py` result |
| after | Claimed the remote branch still existed; `ls-remote` was empty | `git ls-remote` |

### Outcome Classification
- **Mad**: the final report stated a remote-branch state that was never checked.
- **Sad**: the PR merged with the real-CLI smoke jobs unrun. A 3-second pytest no-op nearly passed as a test run.
- **Glad**: no force-push, a pinned-SHA merge, and an identity audit before merge. The body fix was proven with a negative control.

### Impact

| Area | Severity | What happened |
|---|---|---|
| Shipped skill prose | Medium | Two skills shipped broken punctuation until review caught it |
| Report accuracy | Low | One false state claim, corrected the next turn |
| Test evidence | Low | One 0-test run, caught before any claim |
| Runtime verification | Medium | Merged with the real-CLI smoke jobs unrun |

### Failure Mode Classification (`.agents/governance/FAILURE-MODES.md`)

| Failure | Class |
|---|---|
| False remote-branch claim | 9, Confident-incorrectness recurrence: the fact was in memory and was not consulted |
| pytest collected 0 items | 4, False completion markers (near miss): a passing-looking run with no tests |
| Scrub left orphan punctuation | 4, False completion markers: the PR said the scrub was done, and the prose was broken |
| Smoke jobs unrun at merge | 11, Customer-facing artifact shipped without runtime verification (risk, no observed defect) |

## Phase 1: Insights Generated

### Five Whys: false remote-branch claim
1. Why was the claim false? GitHub deleted the branch at merge.
2. Why was that missed? The claim came from the missing `--delete-branch` flag, not the remote.
3. Why trust the flag? The report was written from the commands sent, not from state.
4. Why no state check? Cleanup felt finished after the local worktree removal.
5. Why no memory hit? Memory recall ran on prompts, not before the report's claims.

Root cause: a state claim built from the actions taken, with no read of the state.

### Five Whys: pytest collected 0 items
1. Why 0 items? pytest got one argument holding 58 space-joined paths.
2. Why one argument? zsh does not word-split an unquoted `$files`.
3. Why unquoted? The command was written in bash habit.
4. Why not caught first? `bash-integration-observations.md:33` records this, but it was not recalled.
5. Why was the error caught at all? The output said `no tests ran`, and that was read.

Root cause: a bash habit in a zsh shell. Reading the output caught it.

### Five Whys: scrub damage (inherited from the PR's authoring session)
1. Why stray punctuation? Deleting `(issue #N)` left the comma or period that followed it.
2. Why at a line start? The reference ended its line, so the punctuation wrapped onto the next one.
3. Why not caught by the gate? `check_template_repo_refs.py` checks for references, not leftovers.
4. Why not caught by tests? No test reads prose punctuation.
5. Why caught at all? The owner read the diff.

Root cause: a mechanical deletion with no check for what it left behind.

### Patterns and Shifts
- Pattern: the memory held each process fix, and each mistake recurred anyway. Recall did not fire at the action.
- Shift: check-then-claim kept working where it was used: the body validator, the identity audit, the ls-remote check before deleting.

### Learning Matrix

| :) Continue | :( Change |
|---|---|
| Merge instead of rebase on a pushed branch | Read state before reporting it |
| Negative control on the body validator | Use xargs or arrays for file lists in zsh |
| Merge pinned to the head SHA | Check scrubs for orphan punctuation |

| Idea | Invest |
|---|---|
| Lint for lines that start with `,` or `#.` in templates | Owner decision; see Findings |

## Phase 2: Diagnosis

### Successes (Tag: helpful)
| Strategy | Evidence | Impact | Atomicity |
|----------|----------|--------|-----------|
| Merge origin/main, not rebase, on a pushed PR branch | `dc86b21d76`, no force-push | 8 | 75% |
| Validate a new PR body with the old body as a negative control | old exit 1, new exit 0 | 7 | 75% |
| Pin the merge to the head SHA | `--expected-head-sha 738d5dbbae` | 6 | 70% |

### Failures (Tag: harmful)
| Strategy | Error Type | Root Cause | Prevention | Atomicity |
|----------|------------|------------|------------|-----------|
| Report remote branch state from flags sent | False claim | No state read | `git ls-remote` before the claim | 75% |
| Pass a file list as an unquoted zsh variable | Silent no-op | Bash habit | `xargs` or zsh array | 75% |
| Delete `(issue #N)` without checking for leftovers | Broken prose | No post-deletion check | Grep for line-leading `,` and `#.` | 75% |

### Near Misses
| What Almost Failed | Recovery | Learning |
|--------------------|----------|----------|
| pytest ran 0 tests in 0.01s | Read `no tests ran`, reran with xargs | A fast green run needs a test count |
| Merge with the real-CLI smoke jobs unrun | Reported as NOT RUN; user chose to merge | Required checks do not cover runtime smoke |

## Phase 3: Decisions

### Action Classification

| Type | Item |
|------|------|
| Keep | Merge, not rebase, on pushed branches |
| Keep | Negative control on body validation |
| Add | Post-scrub orphan-punctuation grep |
| Modify | Read remote state before reporting cleanup |
| Drop | None |

### SMART Validation

| Learning | Specific | Measurable | Attainable | Relevant | Timely | Result |
|---|---|---|---|---|---|---|
| Post-scrub orphan-punctuation grep | Yes, two patterns | Yes, grep hit count | Yes, one command | Yes, 2 of 3 threads | Yes, after any bulk delete | Pass |

### Action Sequence
1. Persist the scrub learning (no dependency).
2. Tag recurrences on the three existing memories (no dependency).
3. Owner decides on a lint (depends on 1).

## Phase 4: Extracted Learnings

### Learning 1
- **Statement**: After deleting parenthetical refs, grep templates for lines starting with comma or '#.'.
- **Atomicity Score**: 75%
- **Evidence**: Threads on `templates/skills/sync.SKILL.md.tmpl:31` and `templates/skills/pr-autofix.SKILL.md.tmpl:942`, fixed in `738d5dbbae`
- **Skill Operation**: ADD
- **Target Skill ID**: N/A

### Learning 2
- **Statement**: In zsh, unquoted $var does not word-split; pipe file lists through xargs.
- **Atomicity Score**: 75%
- **Evidence**: pytest collected 0 items over 58 files; xargs rerun passed 2640
- **Skill Operation**: TAG
- **Target Skill ID**: bash-integration-observations

### Learning 3
- **Statement**: Check git ls-remote before claiming a merged PR head branch still exists.
- **Atomicity Score**: 75%
- **Evidence**: `git ls-remote origin refs/heads/fix/templates-no-repo-refs` returned nothing after the claim
- **Skill Operation**: TAG
- **Target Skill ID**: decision-squash-only-breaks-ancestry-merge-detection

### Learning 4
- **Statement**: Run pr_description.py --body-file before editing a PR body; paths under Changes must exist in diff.
- **Atomicity Score**: 75%
- **Evidence**: `Validate PR` failed on `build_all.py`; local rerun matched the CI failure
- **Skill Operation**: TAG
- **Target Skill ID**: pr-validator-needs-prepare-body-file-and-diff-backed-paths

## Skillbook Updates

### ADD
```json
{
  "skill_id": "scrub-orphan-punctuation-check",
  "statement": "After deleting parenthetical refs, grep templates for lines starting with comma or '#.'.",
  "context": "Any bulk deletion of inline references from prose or comments",
  "evidence": "PR #7007 threads on sync.SKILL.md.tmpl:31 and pr-autofix.SKILL.md.tmpl:942",
  "atomicity": 75
}
```

### UPDATE

| Skill ID | Current | Proposed | Why |
|----------|---------|----------|-----|

### TAG

| Skill ID | Tag | Evidence | Impact |
|----------|-----|----------|--------|
| bash-integration-observations | harmful-recurrence | pytest 0 items, 2026-10-31 | 6 |
| decision-squash-only-breaks-ancestry-merge-detection | harmful-recurrence | false branch claim, 2026-10-31 | 5 |
| pr-validator-needs-prepare-body-file-and-diff-backed-paths | helpful | body fixed on first try, 2026-10-31 | 6 |

### REMOVE

| Skill ID | Reason | Evidence |
|----------|--------|----------|

## Deduplication Check

| New Skill | Most Similar | Similarity | Decision |
|-----------|--------------|------------|----------|
| scrub-orphan-punctuation-check | none found (`grep -rliE "stray (comma\|punctuation)\|scrub" .serena/memories`) | Low | Add |
| zsh word-split | bash-integration-observations.md:33 | High | Tag only |
| ls-remote before branch claim | decision-squash-only-breaks-ancestry-merge-detection.md:56 | High | Tag only |
| PR body diff-backed paths | pr-validator-needs-prepare-body-file-and-diff-backed-paths.md | High | Tag only |

## Phase 5: Persist and Close

### Memory Persistence

| Learning | Atomicity | Existing Match | Result |
|----------|-----------|----------------|--------|
| Post-scrub orphan-punctuation grep | 75% | none | Added as `process/process-check-for-orphan-punctuation-after-a-reference-scrub` (0 hits on `78e8145660`, 1 hit in each pre-fix file) |
| zsh word-split | 75% | bash-integration-observations | Updated (recurrence row in History) |
| ls-remote before branch claim | 75% | decision-squash-only-breaks-ancestry-merge-detection | Updated (recurrence note under Decision item 1) |
| PR body diff-backed paths | 75% | pr-validator-needs-prepare-body-file-and-diff-backed-paths | Deduplicated |

### +/Delta

#### + Keep
- Every claim in Phase 0 was traced to a command output or commit.
- The duplicate search ran before any memory was written.

#### Delta Change
- Three of four learnings already existed. Recall at action time is the gap, not the memory itself.

### Delta Triage

#### Actionable Items Identified

| Delta Item | Category |
|------------|----------|
| No gate catches orphan punctuation after a scrub | Tool Gap |
| Real-CLI smoke jobs are not required checks | Process |
| Known zsh and branch facts are not recalled at action time | Tool Gap |

#### Findings for the owner

| Item | Evidence (path:line) | Proposed action | Class |
|------|----------------------|-----------------|-------|
| Orphan punctuation after a scrub | `templates/skills/sync.SKILL.md.tmpl:31` | Add a pattern for lines starting with `,` or `#.` to the template refs gate | Optional enhancement |
| Smoke jobs unrun at merge | PR #7007 rollup at `738d5dbbae`: 6 Smoke jobs WAITING | Approve the waiting smoke runs on main, or make one smoke required | Optional enhancement |
| Known facts not recalled at action time | `.serena/memories/bash/bash-integration-observations.md:33` | Recall memory on Bash commands that build arg lists from variables | Side quest |

### ROTI Assessment

**Score**: 3

**Benefits Received**:
- Found that 3 of 4 mistakes were already in memory, so recall is the gap.
- One new reusable check for scrub work.

**Time Invested**: About 15 minutes

**Verdict**: Continue

### Helped, Hindered, Hypothesis

#### Helped
- Short session with every step backed by tool output.

#### Hindered
- No session log; the evidence came from this conversation and git.

#### Hypothesis
- Running the duplicate search first will cut retro write time for single-PR sessions.
