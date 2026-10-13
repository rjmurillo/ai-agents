# Retrospective: PR #6367 reflect-nudge HIGH/MED patterns

## Session Info
- **Date**: 2026-10-12
- **Agents**: main session (Opus), general-purpose review agent (Sonnet, 4 rounds)
- **Task Type**: Feature
- **Outcome**: Success

Revised 2026-10-13 before landing: the `Validate PR` root cause was corrected from a skipped skill step to a tool gap.

Evidence base: this session's transcript, PR #6367, merge commit `db36beee8`, and CI runs
38262091187, 38339479868, and 38340749330. No session log exists under
`.project-toolkit/sessions/`; session log creation is discontinued. Each claim is marked
OBSERVED (tool output in the session), INFERRED (my reading), or UNKNOWN.

## Phase 0: Data Gathering

### Evidence Links

- PR: [#6367](https://github.com/rjmurillo/ai-agents/pull/6367), merge commit [db36beee8](https://github.com/rjmurillo/ai-agents/commit/db36beee80462dda2a7b85995085dc72ba42db2a)
- `Validate PR` failure: [run 38262091187, job 114854910113](https://github.com/rjmurillo/ai-agents/actions/runs/38262091187/job/114854910113)
- Dispatch closure base drift: [run 38339479868, job 115107014372](https://github.com/rjmurillo/ai-agents/actions/runs/38339479868/job/115107014372); cause [#6366](https://github.com/rjmurillo/ai-agents/pull/6366)
- Flaky testmon test: [run 38340749330, job 115110944568](https://github.com/rjmurillo/ai-agents/actions/runs/38340749330/job/115110944568)
- `rather than` removal: commit `b2caf0c40`; review fixes `02a13f902`, `1841ac925`
- claude-mem source: thedotmack/claude-mem at `356b7c08f64c`, `plugin/skills/agent-cost-report/scripts/acr/`

### Failure Mode Classification

Against `.agents/governance/FAILURE-MODES.md`:

| Failure | Class | Why |
|---------|-------|-----|
| Skipped ship's `/validate-pr-description` step | 1. Context reading failure | The ship skill names the step and it was not run. It was not the cause of the `Validate PR` failure; see the Five Whys |
| Kept `rather than` over the reviewer's objection on one example | 9. Confident-incorrectness recurrence | The claim rested on a corpus with no pasted prose |

### Impact

| Area | Severity | Effect |
|------|----------|--------|
| CI time | Medium | One extra `Validate PR` cycle, about 60 minutes to green |
| Pattern precision | Low | Caught before merge; no shipped false positive |
| Merge latency | Low | Rate limits and one flaky test added waits, not defects |

### 4-Step Debrief

**Observe (facts only)**
- OBSERVED: claude-mem's `agent-cost-report` skill (`acr/patterns.py`, `acr/behavior.py`) held user-side correction regexes and no praise regexes.
- OBSERVED: the 30-day Claude Code corpus had 326 distinct human turns. The old patterns flagged 4 HIGH and 0 MED.
- OBSERVED: none of the claude-mem phrases matched that corpus. Precision was judged by hand on the transcript-derived phrases only.
- OBSERVED: a `cp` into the worktree's `.claude/` was refused by a deny rule. The denial named the main checkout's path, not the worktree's.
- OBSERVED: review round 1 found 4 over-matches on neutral questions. Round 2 left 2 LOW notes. I kept `rather than` over the reviewer's objection.
- OBSERVED: on user request, Codex (141 turns) and Droid (97 turns) history showed `rather than` matching pasted prose in 4 of 5 hits. I dropped it. Copilot history (182 turns) held only automated prompts.
- OBSERVED: two `get_pr_checks.py --wait` runs died on a GraphQL secondary rate limit (exit 3). A 4-minute slow poll worked.
- OBSERVED: required `Validate PR` failed on "File mentioned but not in diff" for `build_all.py`. Ship step 3 said to run `/validate-pr-description` before `/push-pr`. I skipped it, but that skill checks the title, keywords, and template only, so it would not have caught this.
- OBSERVED: the operator left 5 docstring review threads. All were fixed in `1841ac925` and resolved.
- OBSERVED: non-required `Verify dispatch closure against base` failed because #6366 changed `get_pr_checks.py` on `main`. A server-side branch update cleared it.
- OBSERVED: `pytest (split-4)` failed once in `test_pre_push_testmon_concurrent_db.py` (`assert 30 == (2 * 30)`). It passed 3 of 3 locally. A later `Run Python Tests` passed and auto-merge fired.
- OBSERVED: Hindsight recall at session start described the hook as a stuck-loop detector. The code proved that false, and I ingested a correction.

**Respond**
- Pivots: claude-mem had no praise data, so MED came from transcripts. The user's cross-harness request reversed the `rather than` decision.
- Retries: 3 CI waits, 1 failed-job rerun, 2 PR body edits.

**Analyze**
- INFERRED: the `rather than` reversal shows that one operator's typed corpus under-samples pasted prose. The Claude corpus filter drops turns that start with `<`, so long pastes rarely survive. Codex and Droid keep them.
- OBSERVED: no check could have caught the `Validate PR` failure before the PR opened. `pr_description.py` requires `--pr-number`.

**Apply**
- Run `pr_description.py --pr-number <N> --ci` right after opening any PR.
- Test unanchored phrases on a pasted-prose corpus before defending them against a reviewer.

### Execution Trace

| Time (UTC) | Action | Outcome |
|---|---|---|
| 10-12 ~13:30 | Clone claude-mem, grep heuristics | Found correction regexes, no praise |
| ~13:40 | Measure candidates on 326 Claude turns | Picked 13 HIGH, 5 MED |
| ~13:55 | Edit template, build, tests, negative control | 189 pass; first case set: 0 of 22 new cases match on main |
| ~14:00 | Review round 1 | WARN: 4 over-matches; fixed |
| ~14:05 | Review round 2 | WARN LOW x2; acknowledged; marker |
| 14:09 | Push and open PR #6367 | Description not checked against the diff |
| ~14:25 | User: check Copilot, Codex, Droid | `rather than` dropped; round 3 PASS |
| 14:25-14:27 | CI waits | GraphQL secondary rate limit, exit 3 |
| 14:35 | `Validate PR` FAILURE | Description named `build_all.py` |
| ~15:30 | Body fixed, validator clean locally | `Validate PR` passed on rerun |
| ~02:30 (10-13) | 5 operator threads fixed | Round 4 PASS, threads resolved |
| ~03:13 | Dispatch closure fails on base drift | Server-side branch update |
| ~03:33 | split-4 testmon test fails | Rerun queued; auto-merge enabled |
| 04:18 | Merged `db36beee8` | Worktree removed later |

### Outcome Classification

- **Mad**: a required check failed on a body mistake that no local tool could catch before the PR opened.
- **Sad**: two CI waits burned on a rate limit with fast retries; a flaky unrelated test cost a rerun cycle.
- **Glad**: the negative control, corpus measurement, and cross-harness check caught real defects before merge.

## Phase 1: Insights Generated

### Five Whys: `Validate PR` failed

1. Why did it fail? The body named `build_all.py` in backticks under `## Changes`, and that file was not in the diff.
2. Why was it there? I described the render step by naming its script.
3. Why was that not caught before CI? No check compares a description to the diff before the PR exists.
4. Why not? `pr_description.py` requires `--pr-number` and reads the body and diff from GitHub. The `/validate-pr-description` skill, which I also skipped, checks the title, keywords, and template only.
5. Why did the existing memory not prevent it? It advised rerunning the validator before opening the PR, which the validator cannot do.

Root cause: a tool gap. The only description-vs-diff check needs an open PR, so the first signal is a red required check. Filed as [#6405](https://github.com/rjmurillo/ai-agents/issues/6405).

### Five Whys: `rather than` survived review round 2

1. Why did it survive? I overruled the reviewer with one example sentence.
2. Why was one example enough for me? The Claude corpus showed 1 of 1 true hits.
3. Why did that corpus mislead? Typed turns rarely contain pasted prose.
4. Why? `human_text` drops turns that start with `<`, and the operator's pastes arrive wrapped.
5. Why not test other corpora first? I did not think of them. The user's request found the evidence.

Root cause: precision was measured on a corpus with no pasted prose.

### Learning Matrix

| :) Continue | :( Change |
|---|---|
| Negative control against the main-branch hook | Run the description validator right after opening a PR |
| Hand-reading every new match | Test unanchored phrases on pasted-prose corpora |
| Slow poll after a rate-limit failure | Use slow polling from the start when the account is busy |

| Idea | Invest |
|---|---|
| A local `--body-file` mode for `pr_description.py`, run by `/push-pr` | Filed as #6405 |
| REST fallback in `get_pr_checks.py` for secondary limits | Tracked in #6391 |

## Phase 2: Diagnosis

### Successes (Tag: helpful)
| Strategy | Evidence | Impact | Atomicity |
|----------|----------|--------|-----------|
| Negative control: load the main-branch hook and run the new cases | Final case set: 0 of 25 matched on main, 25 of 25 on branch. The positive set went from 22 to 26 when round 1 added 2 correction and 2 preference cases, then to 25 when the `rather than` case was removed | 8 | 90% |
| Cross-harness corpus check for regex precision | `rather than` 4 of 5 false positives in Codex and Droid | 9 | 88% |
| Server-side branch update for base-drift closure failures | Closure check went SUCCESS after `update_pr_branch.py` | 6 | 85% |

### Failures (Tag: harmful)
| Strategy | Error Type | Root Cause | Prevention | Atomicity |
|----------|------------|------------|------------|-----------|
| Opened the PR without a description-vs-diff check | Tool gap | The only check needs an open PR | Run `pr_description.py` right after `new_pr.py` | 92% |
| Overruled reviewer on `rather than` | Premature conclusion | Corpus had no pasted prose | Test on a second corpus first | 85% |
| `get_pr_checks.py --wait` under secondary limit | External | Fast retries hit the same limit | Poll every 4 minutes | 80% |

### Near Misses
| What Almost Failed | Recovery | Learning |
|--------------------|----------|----------|
| `cp` into `.claude/` resolved to the main checkout | Deny rule blocked it | Use absolute worktree paths in writes |
| Acted on Hindsight recall of the hook's patterns | Read the file first | Verify recalled facts against code |

## Phase 3: Decisions

### Action Classification

| Action | Class | Item |
|---|---|---|
| Negative control for pattern changes | Keep | Load main-branch module from scratchpad |
| Run `pr_description.py` right after `new_pr.py` | Add | Session practice |
| Defend reviewer-contested patterns with one example | Drop | Need a second corpus |
| `--wait` polling on a busy account | Modify | Slow poll |

### SMART Validation

- Run `pr_description.py --pr-number N --ci` right after `new_pr.py`, and fix every CRITICAL before CI runs. Specific, measurable (exit and CRITICAL count), achievable, relevant to #6367, time-bound to PR open. Pass.
- Before overruling a reviewer on a regex, measure it on at least two corpora. Specific and measurable (two hit counts). Pass.

### Action Sequence

1. Correct the existing PR-validator memory and record this recurrence (no dependency). Opened as PR #6409.
2. Ingest the cross-harness precision learning to Hindsight (no dependency).
3. File the tool-gap findings below. Done: #6405, #6406, and evidence on #6391.

## Phase 4: Extracted Learnings

### Learning 1
- **Statement**: Run pr_description.py on the PR before CI; backticked non-diff paths fail Validate PR.
- **Atomicity Score**: 90%
- **Evidence**: PR #6367 `Validate PR` FAILURE on `build_all.py`, run 38262091187
- **Skill Operation**: TAG
- **Target Skill ID**: pr-review/pr-validator-needs-prepare-body-file-and-diff-backed-paths

### Learning 2
- **Statement**: Check unanchored transcript regexes on Codex and Droid history; pasted prose inflates false positives.
- **Atomicity Score**: 85%
- **Evidence**: `rather than` matched pasted prose in 4 of 5 Codex and Droid hits, commit `b2caf0c40`
- **Skill Operation**: ADD
- **Target Skill ID**: n/a

### Learning 3
- **Statement**: Dispatch-closure failures from base drift clear with a server-side branch update.
- **Atomicity Score**: 82%
- **Evidence**: run 38339479868 flagged `get_pr_checks.py` changed by #6366; passed after update to `294f35181`
- **Skill Operation**: ADD
- **Target Skill ID**: n/a

### Learning 4
- **Statement**: After a GraphQL secondary rate limit, poll checks every 4 minutes, not with --wait.
- **Atomicity Score**: 78%
- **Evidence**: two `--wait` runs exited 3; the 4-minute poll completed 12 cycles
- **Skill Operation**: ADD
- **Target Skill ID**: n/a

## Skillbook Updates

### ADD
```json
{
  "skill_id": "regex-cross-harness-precision",
  "statement": "Check unanchored transcript regexes on Codex and Droid history; pasted prose inflates false positives.",
  "context": "Changing reflect-nudge or any human-turn classifier patterns",
  "evidence": "PR #6367, commit b2caf0c40",
  "atomicity": 85
}
```

### UPDATE

| Skill ID | Current | Proposed | Why |
|----------|---------|----------|-----|
| pr-review/pr-validator-needs-prepare-body-file-and-diff-backed-paths | Rerun the validator before opening the PR | Run it right after the PR opens | The validator requires `--pr-number`; opened as PR #6409 |

### TAG

| Skill ID | Tag | Evidence | Impact |
|----------|-----|----------|--------|
| pr-review/pr-validator-needs-prepare-body-file-and-diff-backed-paths | helpful (recurrence) | PR #6367 Validate PR failure | 7 |

### REMOVE

| Skill ID | Reason | Evidence |
|----------|--------|----------|

## Deduplication Check

| New Skill | Most Similar | Similarity | Decision |
|-----------|--------------|------------|----------|
| Learning 1 | pr-review/pr-validator-needs-prepare-body-file-and-diff-backed-paths | High | Update existing, no new memory |
| Learning 2 | none found by keyword search | Low | Add |
| Learning 3 | none found by keyword search | Low | Add |
| Learning 4 | ci-infrastructure-observations (mentions rate limits) | Medium | Add to Hindsight only |

## Phase 5: Persist and Close

### Memory Persistence

| Learning | Atomicity | Existing Match | Result |
|----------|-----------|----------------|--------|
| Learning 1 | 90% | pr-validator-needs-prepare-body-file-and-diff-backed-paths | Update opened as PR #6409 |
| Learning 2 | 85% | none | Added to Hindsight; Serena skipped (needs a branch and index row) |
| Learning 3 | 82% | none | Added to Hindsight; Serena skipped (needs a branch and index row) |
| Learning 4 | 78% | ci-infrastructure-observations | Added to Hindsight; Serena skipped |

### +/Delta

#### + Keep
- Evidence marked OBSERVED or INFERRED, with run IDs and commits.

#### Delta Change
- Run the description validator as part of opening the PR, not after CI fails.
- Measure precision on more than one corpus before overruling a reviewer.

### Delta Triage

#### Actionable Items Identified

| Delta Item | Category |
|------------|----------|
| No pre-open description-vs-diff check | Tool Gap |
| `get_pr_checks.py --wait` gives up fast on secondary rate limits | Tool Gap |

#### Findings for the owner

| Item | Evidence (path:line) | Proposed action | Class |
|------|----------------------|-----------------|-------|
| No pre-open check compares the description to the diff | `scripts/validation/pr_description.py:1254-1256` makes `--pr-number` required unless `PR_NUMBER` is set | Add a local `--body-file` mode and run it before `new_pr.py` | Filed: [#6405](https://github.com/rjmurillo/ai-agents/issues/6405) |
| `--wait` exits 3 on a GraphQL secondary limit | `get_pr_checks.py` output: "retrying in 0.1s" then exit 3 | REST fallback | Duplicate of [#6391](https://github.com/rjmurillo/ai-agents/issues/6391); evidence comment added |
| `test_concurrent_partitions_record_into_one_database` failed once in CI | `tests/validation/test_pre_push_testmon_concurrent_db.py:97`, job 115110944568 | Measure failure rate; find lost-row cause | Filed: [#6406](https://github.com/rjmurillo/ai-agents/issues/6406) |

### ROTI Assessment

**Score**: 3

**Benefits Received**:
- Found a tool gap behind a repeat failure, and a memory whose advice could not be followed.
- Recorded why `rather than` was dropped, with the corpus counts.

**Time Invested**: about 20 minutes

**Verdict**: Continue

### Helped, Hindered, Hypothesis

#### Helped
- Run IDs and commit SHAs captured during the session.

#### Hindered
- No session log; the trace relies on the transcript alone.

#### Hypothesis
- A local pre-open mode of `pr_description.py` (#6405) would have saved one CI cycle here.
