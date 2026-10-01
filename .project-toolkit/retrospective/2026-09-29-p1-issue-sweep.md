# Retrospective: Orchestrated P1 issue sweep (rjmurillo/ai-agents)

## Session Info
- **Date**: 2026-09-29
- **Agents**: orchestrator, read-only triage agent, implementer and fix agents
- **Task Type**: Bug
- **Outcome**: Partial

Evidence base: the orchestrator's session record as relayed in the request (facts 1 to 7). I did not read the raw transcripts. Every claim below is labeled OBSERVED (in the record), INFERRED (my reading), or UNKNOWN (not in the record). Self-blame and external blame get the same bar: a cause is stated only as far as the record supports it.

## Phase 0: Data Gathering

### 4-Step Debrief

**Step 1: Observe (facts only)**
- OBSERVED: 22 P1 issues triaged. 11 closed, 3 partial merges with the issue still open (#5738, #5423, #5424), #5245 in progress as stacked PRs, 7 trackers or paid-run residuals got status comments.
- OBSERVED: a triage agent labeled #5767 FIX-NEEDED with "no matching commits". PR #5986 had closed #5767 at 07:42 PDT the same day.
- OBSERVED: owner question D4 was premised on building a PreToolUse hook for #5767. ADR-112 rejects that hook. The fix agent found both facts and made no changes.
- OBSERVED: three subagents ran concurrently at least twice (#5549 + #5485 + #5477; #5485 + #5477 + #5738). The cap is two.
- OBSERVED: the #5488 close comment asserted "no lease code". The grep in that command failed on a zsh glob before the close ran. The claim was later verified true.
- OBSERVED: implementer agents ended turns at interim CI status on #5485 and #5477 and needed resume messages. Early prompts lacked "do not end your turn at an interim status".
- OBSERVED: a subagent refused to act on a relayed owner approval (D5). The orchestrator ran `run_completion_gate.py --approve-untrusted-config` and the merge.
- OBSERVED: pushes hung about 10 minutes on the pre-push e2e smoke test (agent-shims, 1Password read). Tracked in #6000. The workaround spread by message.

**Step 2: Respond**
- Pivot: fix agent stopped on finding #5767 closed. Correct.
- Retries: resume messages on #5485 and #5477 (count UNKNOWN, "several").
- Escalation: D4 and D5 went to the owner.
- Block: push hang, about 10 minutes per early attempt.

**Step 3: Analyze**
- Facts 1 and 3 share a shape: a claim was acted on or posted from evidence that was stale (1) or had not returned (3).
- Facts 2 and 4 share a shape: a written rule existed and was not applied (cap, stop condition). Whether the cause was omission or judgment is discussed under Five Whys.
- Identity check (Bias Guard): no tool or methodology is protected here. The orchestrator's own choices (D4 framing, the cap exception, the early close) are the subject, and they are assessed on the same evidence as the triage agent's error.

**Step 4: Apply**
- Skills to update: none.
- Memory: one UPDATE, two ADD (Phase 4).
- Context to preserve: the #5767 packet-staleness memory already exists on origin/main (PR #6034).

### Execution Trace

| Time | Agent | Action | Outcome | Energy |
|------|-------|--------|---------|--------|
| 07:42 PDT | (other work) | PR #5986 closes #5767 | Merged | n/a |
| after 07:42 | triage | Reports #5767 FIX-NEEDED | Stale | High |
| after triage | orchestrator | Asks owner D4 on a hook | Answer rests on false premise | High |
| later | fix agent | Finds #5767 closed, ADR-112 rejects hook | Stopped, no changes | Medium |
| early | implementers | Push attempts | Hung about 10 min each | Stalled |
| several | implementers | End turns at interim CI | Resume messages | Stalled |
| twice | orchestrator | Runs 3 concurrent agents | Cap breach | High |
| on close of #5488 | orchestrator | Grep fails, close posted | Claim unproven at post time | Medium |
| D5 | orchestrator | Runs gate approval and merge itself | Merged | Medium |

Timeline patterns: exact clock times exist only for #5986. All other ordering is from the record's sequence, not timestamps. Stalls cluster in the implementer phase (push hang, interim stops).

### Outcome Classification
- Mad (blocked): push hangs (about 10 min each); D4 answer built on a false premise.
- Sad (suboptimal): interim-status stops (at least 2 issues); cap breach (2 occurrences); unproven close comment on #5488.
- Glad (success): fix agent stopped on stale input; subagent refused relayed approval; 11 of 22 issues closed with a merging PR or prior fix cited; memories added for two hazards.
- Distribution: Mad 2, Sad 3, Glad 4. Closure rate 11/22 = 50%. Merge or progress (closed plus 3 partial plus #5245) 15/22 = 68%.

## Phase 1: Insights Generated

### Five Whys

**Item 1. Stale triage led to a decision brief on a false premise**

Problem: D4 was asked on a premise that #5767 needed a hook. It was closed and the hook was rejected.
- Q1 Why was D4 wrong? A1 OBSERVED: it assumed #5767 was open and needed a PreToolUse hook.
- Q2 Why assume open? A2 OBSERVED: the triage packet said FIX-NEEDED, "no matching commits".
- Q3 Why did the packet say that? A3 INFERRED: it searched commits for matching text, and #5986 did not match the search terms or landed after the read. UNKNOWN which.
- Q4 Why did the orchestrator not catch it? A4 INFERRED: it relayed the packet into a brief without a live state read. The existing memory names a re-read "before dispatch". No re-read is recorded "before asking".
- Q5 Why no re-read before asking? A5 INFERRED: the brief was treated as planning, and the re-read gate was attached to dispatch, not to owner questions.
- Root cause: the live-state check is attached to dispatch, not to decision briefs. Also UNKNOWN: whether the orchestrator read ADRs before proposing a hook. ADR-112 rejects it.
- Fix: read live issue state and ADRs before any owner question that rests on a packet. Applied as a recommendation only (see Findings for the owner).

**Item 2. Concurrency cap breached (2 of 2 known breaches used the same excuse)**

Problem: three concurrent subagents, cap two.
- Q1 Why three? A1 OBSERVED: the orchestrator judged one agent "only polling CI" as not counting.
- Q2 Why does polling not count? A2 INFERRED: it consumes little compute, so it felt outside the cap's purpose. No text in the cap says polling is exempt. The cap text is in the owner's global instructions and, per `cost/cost-optimization-observations.md:27`, in repo memory.
- Q3 Why was the judgment not checked? A3 INFERRED: no count is taken before spawning, so the breach is invisible until after.
- Q4 Why no count? A4 UNKNOWN: no hook or script enforces it (I did not search for one, so I make no claim of absence).
- Q5 Why repeated? A5 OBSERVED: it happened at least twice, so the first rationalization was not corrected in-session.
- Root cause: a numeric rule with no pre-spawn count, open to case-by-case exceptions. This is an orchestrator error, not a triage or environment one.
- Fix: count live agents, polling included, before each spawn. Persisted.

**Item 3. Closing claim posted before its evidence existed**

Problem: #5488 close comment asserted a grep result the grep never returned.
- Q1 Why? A1 OBSERVED: the grep and the close shared one command and the close ran after the grep failed.
- Q2 Why did the close run? A2 INFERRED: the commands were not chained with `&&`, or the failure was not read.
- Q3 Why did the grep fail? A3 OBSERVED: zsh expanded an unquoted `--include=*.py` and reported `no matches found`.
- Q4 Why was the comment text written before the result? A4 INFERRED: the orchestrator held the expectation from earlier context ("already fixed by #5697") and wrote the comment to match it.
- Q5 Why did that pass? A5 INFERRED: an expectation confirmed by no output looked the same as a confirmed result.
- Root cause: closing text written from expectation, with the probe as decoration. The claim was later verified true. That is luck of prior, not process.
- Fix: run the probe alone, read it, then post. Persisted.

**Item 4. Implementers ended turns at interim status**

Problem: turns ended at interim CI on #5485 and #5477.
- Q1 Why? A1 OBSERVED: the agents reported status and stopped.
- Q2 Why stop instead of wait? A2 INFERRED: a final message ends a subagent turn, and CI wait is a state where a status message reads as done.
- Q3 Why did the prompt not prevent it? A3 OBSERVED: early prompts said "drive to merge; do not end at interim status" but lacked "do not end your turn at an interim status".
- Q4 Why the shorter line? A4 UNKNOWN. No record of why the wording was chosen or later changed.
- Q5 Did the added line fix it? A5 UNKNOWN. The record lists no later contrast.
- Root cause: INFERRED, incomplete. Prompt wording is a candidate. It is not confirmed.
- Fix: add the line, and measure resume messages per PR next sweep. Persisted as a hypothesis.

### Fishbone (item 4 and item 1 combined)
- Prompt: implementer wording (item 4); triage prompt lacked a "check for a closing PR" step (item 1, INFERRED).
- Tools: search by commit text misses PRs that close by reference (INFERRED).
- Context: packet age unstated in briefs.
- Sequence: re-read gate placed at dispatch, not at owner question.
- State: none observed.
Cross-category pattern: stale state entering a decision or prompt with no age or verification marker.

### Patterns and Shifts

| Pattern | Frequency | Impact | Category |
|---------|-----------|--------|----------|
| Claim used before its evidence was live | 2 (items 1, 3) | H | Failure |
| Written rule applied by judgment, not count | 2 (items 2, 4, cap and prompt line) | M | Failure |
| Agent stopped on bad input instead of pressing on | 2 (fix agent on #5767, subagent on relayed approval) | H | Success |
| Workaround spread by message | 1 (push hang) | M | Efficiency |

### Learning Matrix

- Continue: fix agent stopping when the issue was closed; subagent refusing a relayed approval; the hazard memories (#6034).
- Change: pre-spawn agent count; probe-then-post for closing comments; live read before owner briefs.
- Idea: log packet age in every brief.
- Invest: a hook that counts live subagents (owner decision; see Findings).

## Phase 2: Diagnosis

### Successes (Tag: helpful)
| Strategy | Evidence | Impact | Atomicity |
|----------|----------|--------|-----------|
| Fix agent verifies issue state and ADRs before building | #5767 fix agent made no changes | 8 | 85% |
| Subagent refuses a relayed approval | D5 | 7 | 80% |

### Failures (Tag: harmful)
| Strategy | Error Type | Root Cause | Prevention | Atomicity |
|----------|------------|------------|------------|-----------|
| Owner brief built on a triage packet | Stale state | Live read attached to dispatch only | Read state and ADRs before the brief | 78% |
| Three concurrent agents | Rule breach | Polling excused, no count | Count before spawn | 90% |
| Close comment before probe | Unproven claim | Expectation written as result | Probe alone, then post | 92% |
| Prompt without stop line | Interim stops | INFERRED prompt wording | Add the line, measure | 75% |

### Near Misses
| What Almost Failed | Recovery | Learning |
|--------------------|----------|----------|
| Hook built for closed #5767 | Fix agent found closure and ADR-112 | Verify before build |
| #5488 close | Claim was true | Correct outcome does not validate the process |
| Relayed approval executed by a subagent | Subagent refused | Relay is not consent |

## Phase 3: Decisions

### Action Classification

| Class | Finding | Action |
|-------|---------|--------|
| Keep | Fix agent state check; subagent refusal | TAG helpful |
| Modify | `cost/cost-optimization-observations.md` cap item | UPDATE |
| Add | Closing-claim memory; implementer prompt memory | ADD |
| Modify (not applied) | `pr-review/triage-packets-go-stale-within-hours.md` | Extend "before dispatch" to "before an owner question" |

The last row is not applied. My checkout lacks that file because local `main` has diverged from `origin/main` (one local commit, `bd init`), and I did not rewrite the owner's branch.

### SMART Validation
All three persisted learnings: specific (one concept), measurable (cited issue), attainable, relevant (recurred or cost a turn), timely (trigger stated). Learning 3 fails Measurable on effect size, so it is tagged hypothesis.

### Action Sequence
1. Persist memories (no dependency).
2. Update memory-index.md (depends on 1). Validator passes: 43 domains, 566 files, 0 issues.
3. Owner decides on Findings (no dependency).

## Phase 4: Extracted Learnings

### Learning 1
- **Statement**: Count every live subagent, polling agents included, before each spawn against the cap of two.
- **Atomicity Score**: 88%
- **Evidence**: two breaches, #5549/#5485/#5477 and #5485/#5477/#5738, one excused as "only polling CI".
- **Skill Operation**: UPDATE
- **Target Skill ID**: cost/cost-optimization-observations

### Learning 2
- **Statement**: Post a closing claim only after its evidence command exits cleanly.
- **Atomicity Score**: 90%
- **Evidence**: #5488 close after a failed zsh-glob grep.
- **Skill Operation**: ADD
- **Target Skill ID**: process/process-post-a-closing-claim-only-after-its-evidence-command-succeeds

### Learning 3
- **Statement**: Put "do not end your turn at an interim status" in every drive-to-merge prompt.
- **Atomicity Score**: 78%
- **Evidence**: #5485 and #5477 stops. Effect of the line UNKNOWN (hypothesis).
- **Skill Operation**: ADD
- **Target Skill ID**: orchestration/orchestration-implementer-prompts-must-forbid-interim-stops

## Skillbook Updates

### ADD
```json
{"skill_id":"process-post-a-closing-claim-only-after-its-evidence-command-succeeds","statement":"Post a closing claim only after its evidence command exits cleanly.","context":"Before closing an issue with a claim about repo contents.","evidence":"#5488, 2026-09-29","atomicity":90}
{"skill_id":"orchestration-implementer-prompts-must-forbid-interim-stops","statement":"Put 'do not end your turn at an interim status' in every drive-to-merge prompt.","context":"Writing an implementer prompt that says drive to merge.","evidence":"#5485, #5477, 2026-09-29 (hypothesis)","atomicity":78}
```

### UPDATE

| Skill ID | Current | Proposed | Why |
|----------|---------|----------|-----|
| cost-optimization-observations | Cap 3 total and 2 concurrent | Add: polling agents count | Two breaches excused as polling |

### TAG

| Skill ID | Tag | Evidence | Impact |
|----------|-----|----------|--------|
| triage-packets-go-stale-within-hours | helpful | Pattern recurred in item 1 beyond dispatch | Extend scope (not applied) |

### REMOVE

| Skill ID | Reason | Evidence |
|----------|--------|----------|

## Deduplication Check

| New Skill | Most Similar | Similarity | Decision |
|-----------|--------------|------------|----------|
| closing-claim memory | pr-review/triage-001-verify-before-stale-closure | Low: that one covers stale issues, this covers probe exit status | ADD |
| implementer prompt memory | orchestration/orchestration-prompt-002-copilot-swe-constraints | Low: different agent type | ADD |
| cap counting | cost/cost-optimization-observations | High: same cap | UPDATE |
| stale triage packet | pr-review/triage-packets-go-stale-within-hours | High | Not re-added |
| push hang | git/git-agent-shims-hang-pre-push-on-a-1password-read | High | Not re-added |

## Phase 5: Persist and Close

### Memory Persistence

| Learning | Atomicity | Existing Match | Result |
|----------|-----------|----------------|--------|
| Count live agents incl. polling | 88% | cost/cost-optimization-observations | Updated |
| Close claim after clean probe | 90% | none | Added |
| Interim-stop prompt line | 78% | none | Added |

Files are written in the working checkout and are uncommitted. The skill does not require a commit or PR.

### +/Delta

#### + Keep
- Labeling each claim OBSERVED, INFERRED, or UNKNOWN exposed that items 2, 3, 4 causes are mostly inference.

#### Delta Change
- Read the transcript, not the relayed record. Root causes at Q3 to Q5 of every item are inference.

### Delta Triage

#### Actionable Items Identified

| Delta Item | Category |
|------------|----------|
| Extend the stale-packet memory to owner briefs | Missing Docs |
| No mechanical count of live subagents | Tool Gap |
| Relayed-approval flow for gate config is undocumented in the record | Process |

#### Findings for the owner

| Item | Evidence (path:line) | Proposed action | Class |
|------|----------------------|-----------------|-------|
| Stale-packet memory covers dispatch, not owner questions | .serena/memories/pr-review/triage-packets-go-stale-within-hours.md:9 (on origin/main) | Add "and before any owner question resting on a packet; read ADRs too" | Optional enhancement |
| Cap of two concurrent agents has no pre-spawn enforcement | .serena/memories/cost/cost-optimization-observations.md:27-28 | Decide whether a counting hook is wanted. I did not search for an existing one. | Optional enhancement |
| Orchestrator ran `--approve-untrusted-config` on a directly received owner approval | UNKNOWN (no file line; from session record fact 5) | Confirm this matches the gate's intent | Side quest |

### ROTI Assessment

**Score**: 1

**Benefits Received**:
- Three memory changes, two of them net new.
- Five Whys flagged which causes are unverified.

**Time Invested**: one session, evidence limited to a relayed record.

**Verdict**: Modify (use raw transcripts)

### Helped, Hindered, Hypothesis

#### Helped
- Existing memories from #6034 already covered items 1 and 6, which avoided two duplicates.

#### Hindered
- No transcript, no timestamps except one. Local `main` is behind `origin/main`, so the newest memories were not on disk.

#### Hypothesis
- Comparing resume-message counts per PR with and without the stop line in the next sweep will confirm or refute Learning 3.
