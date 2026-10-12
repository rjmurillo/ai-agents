# Retrospective: v0.7.0 P2 sweep, 10 issues, 15 PRs (rjmurillo/ai-agents)

## Session Info
- **Date**: 2026-10-11 to 2026-10-12 (UTC)
- **Agents**: orchestrator, about 12 implementer agents, review agents
- **Task Type**: Bug
- **Outcome**: Partial (9 of 10 issues closed, 1 open with PR #6315 pending)

Evidence base: the orchestrator's session record as relayed in the request, checked against GitHub REST (paginated) and git on 2026-10-12. I did not read raw transcripts. Each claim is labeled OBSERVED, INFERRED, or UNKNOWN. UNKNOWN (relayed) means the orchestrator said it and no artifact confirms it.

Failure mode class (retros.md MUST 2): item 2 matches FAILURE-MODES.md class 9 (confident incorrectness). Item 5 matches class 4 (false completion marker, in claim form). Item 1 matches no class. The proposal for a new class is the first row of Findings for the owner.

Already covered, referenced and not repeated: PR #6316 (merged, rule quirks for agent templates, reachability test, portability ratchet) and PR #6317 (open, memories for tmp inode cap, check-runs pagination, GraphQL secondary limit, killed pre-push markers, skill support file source, 5851 decision).

## Phase 0: Data Gathering

### 4-Step Debrief

**Step 1: Observe (facts only)**
- OBSERVED: 13 sweep PRs merged 2026-10-12: #6301 e3efd0693, #6298 6964b7403, #6306 ce06312ac, #6304 088f9296b, #6303 ca1e027b2, #6299 b2b74f7fd, #6314 a9cd81144, #6293 a0708e774, #6318 5154e6ccf, #6319 8e7088f3b, #6320 49ccb4bfd, #6309 0cee6a298, #6316 75680f729. Two stay open: #6315 (Fixes #5399) and #6317.
- OBSERVED: the request listed #6320 as pending. It merged 2026-10-12T09:35:09Z.
- OBSERVED: issues closed `completed`: #5766, #5403, #5765, #5601, #6032, #5851, #5397, #5390. #5417 closed `not_planned` at 05:36:32Z. #5399 is open.
- OBSERVED: #5390 close comment (05:36:37Z) closes the epic. #6290 and #6291 (created 05:36Z) track parts 2 and 3 of #5389.
- OBSERVED: #6292 (created 06:05Z) records `df -i /tmp` at 1,048,560 of 1,048,576 inodes with 18% bytes used, 446 leaked ratchet directories, and 561,487 entries under `/tmp/pytest-of-richard` across 15 basetemps. It says about 12 agents ran `pre_pr.py` and `git push` at once.
- OBSERVED: `templates/agents/orchestrator.shared.md:347` sets "Max concurrent delegations per wave: 4 by default". Line 348 bars stash in a concurrent wave. A search of `templates/rules/` and `.claude/rules/` for concurrency, wave, and fan-out limits found neither.
- OBSERVED: memory `git/git-stash-is-shared-across-every-worktree.md` exists on origin/main (last commit 2026-08-04).
- OBSERVED: for #6320 head 26f0b26aa the first check-runs page returns 30 of 152 runs. For #6314 head 104801ca1 it returns 30 of 164. Paginated counts are 152 and 164.
- OBSERVED: `.claude/skills/github/scripts/pr/get_pr_checks.py:5` reads checks through GraphQL `statusCheckRollup`.
- OBSERVED: #4607 holds the new evidence comment (2026-10-12T08:11:42Z). GraphQL showed 4,669 and 4,752 of 5,000 remaining during both refusals. REST core showed 5,000.
- OBSERVED: `scripts/validation/pr_description.py:5` flags files a description names that are not in the diff. The ship contract carries a 3b CORRECTION that names `.claude/skills/<name>/` as the source for skill support files.
- OBSERVED: #5851 close comment records the owner choice of option B (#6314, native `bashOutputMaxChars`), then option C (#6299), over a hook (ADR-097, `.claude/rules/tool-use-hook-bar.md`).
- UNKNOWN (relayed): the ENOSPC duration, the number of agents that edited `src/claude`, the stash pop on the owner's stash, the wrong admin-merge claim and its retraction, the `timeout 110` push wrapper, the backwards recording of the description rule. No artifact holds these.

**Step 2: Respond**
- Pivots: the push-lock plus throttled resume replaced free-running pushes. REST polling at 5-minute intervals replaced GraphQL polling. Option B then C replaced a hook.
- Retries: agents re-derived the skill source tree. Pushes re-ran after kill.
- Escalations: the owner raised the inode cap. The owner made decision D1 on #5851.
- Blocks: every tool call failed with ENOSPC for a stretch (duration UNKNOWN). GraphQL refused calls twice for about 30 minutes each (relayed, matches #4607 comment).

**Step 3: Analyze**
- Three of seven items share one shape: a limit existed in one place and the brief for the fan-out did not carry it (wave cap, stash ban, skill source).
- Items 3 and 5 share a second shape: a read returned a partial answer and was treated as complete (GraphQL budget read from primary quota, first page of 30 read as all runs).
- Bias Guard: the orchestrator wrote the ship contract, ran the wave, and made the bypass claim. It gets the same evidence bar as the implementers. The repo's own orchestrator template states the cap, so the gap is where the cap lives, not who ignored it.
- Conformist test: the obvious lesson is "agents should not run in parallel". The evidence does not support it. Parallel fan-out merged 13 PRs between 07:03Z and 09:40Z. The loss came from an unbounded wave on a shared host, not from parallelism.

**Step 4: Apply**
- Rules: none new. Both candidates fail the always-on admission test or duplicate `orchestrator.shared.md`.
- Memories: four candidates (Phase 4), not written from this linked worktree.
- Issues: none filed by this retro. Findings table below.

### Execution Trace

| Time (UTC) | Agent | Action | Outcome | Energy |
|------------|-------|--------|---------|--------|
| 10-12 05:36 | orchestrator | Close #5417 (not planned), #5390 (completed), file #6290, #6291 | Closed | High |
| 10-12 06:05 | orchestrator | File #6292 after /tmp inode exhaustion | Open | Medium |
| 10-12 07:03 to 07:05 | agents | Merge #6301, #6298 | Merged | High |
| 10-12 07:59 | agent | Merge #6306 | Merged | Medium |
| 10-12 08:11 | orchestrator | Comment evidence on #4607 | Posted | Medium |
| 10-12 08:17 to 08:40 | agents | Merge #6304, #6293, #6309, #6303, #6299 | Merged | High |
| 10-12 09:26 | agent | Merge #6314, close #5851 at 09:27 | Merged | High |
| 10-12 09:32 to 09:40 | agents | Merge #6316, #6320, #6319, #6318, close #5397 at 09:40 | Merged | High |

Timeline patterns: OBSERVED times come from GitHub. The ENOSPC window, both GraphQL windows, and every agent turn are UNKNOWN in time. Merges cluster at 07:03, 08:17 to 08:40, and 09:26 to 09:40. INFERRED: the gaps between clusters include the lockout windows.

### Outcome Classification
- Mad: ENOSPC stopped all tool calls (item 1). Two GraphQL lockouts (item 3).
- Sad: skill source rediscovered by several agents (item 2). Owner stash popped, recovered (item 4). Wrong bypass claim, retracted (item 5). Hook-killing `timeout` wrapper (item 6). Description rule recorded backwards (item 7).
- Glad: triage-first fan-out. Design gate on #5851. Throttled resume with push-lock. Owner stash survived. Retraction before any bypass was used.
- Distribution: Mad 2, Sad 5, Glad 5. 9 of 10 issues closed (90%).

## Phase 1: Insights Generated

### Five Whys

**Item 1. Parallel pushes exhausted /tmp inodes and stopped every tool call**

Problem: every tool call returned ENOSPC while bytes were 18% used.
- Q1 Why did every call fail? A1 OBSERVED (#6292): the harness writes each call's output under `/tmp`, and inodes sat at 1,048,560 of 1,048,576.
- Q2 Why were inodes gone? A2 OBSERVED: 561,487 pytest basetemp entries plus 446 leaked ratchet scratch directories.
- Q3 Why so many at once? A3 OBSERVED: about 12 agents ran `pre_pr.py` and `git push` concurrently, each with its own worktree.
- Q4 Why 12 when the template says 4? A4 OBSERVED: the cap is at `orchestrator.shared.md:347`, and no rule in `templates/rules/` or `.claude/rules/` repeats it. UNKNOWN: whether the orchestrator agent template loaded in this session. The ship contract had no cap and added TMPDIR as step 3a only after the failure.
- Q5 Why did nothing check the host? A5 INFERRED: inodes do not show in `df -h`, and the contract treated each agent as independent of the host.
- Root cause: the wave bound lives in one agent template and not in the brief the fan-out used. No gate looks at host inode use.
- Contributing cause: ratchet scripts leak scratch on SIGTERM (tracked, #6292). `TMPDIR` does not move the harness output directory (covered in #6317 memory).
- Fix: copy the wave cap and the stash ban into any hand-written fan-out brief. Run `df -i /tmp` before each wave. The leak fix stays with #6292.

**Item 2. The ship contract named the wrong source of truth**

Problem: the contract said skill scripts live in `src/claude`. `build_all.py` reverts edits there.
- Q1 Why did agent edits vanish? A1 OBSERVED (contract 3b CORRECTION): the source is `.claude/skills/<name>/`, mirrored into `src/`.
- Q2 Why did the contract say `src/claude`? A2 INFERRED: `.claude/AGENTS.md` opens by calling `.claude/` a binplaced copy of the `src/claude/` tree. A reader who stops there infers the wrong direction. The same file lists each skill's non-SKILL.md files as hand-maintained.
- Q3 Why was the claim not caught? A3 UNKNOWN (relayed): no agent or orchestrator ran one edit through `build_all.py` before the wave.
- Q4 Why did several agents hit it? A4 OBSERVED: the contract was shared. One wrong line reached every brief. UNKNOWN: the count.
- Q5 Why no early correction path? A5 INFERRED: agents reported in final reports only, so a rediscovery did not reach siblings mid-wave.
- Root cause: a shared brief carried an unverified claim to every agent. This is FAILURE-MODES class 9.
- Fix: before a wave, make one real edit through the build in a scratch worktree for every path class the brief names. Memory for the correct tree is in #6317.

**Item 3. Parallel polling tripped the GraphQL secondary limit twice**

Problem: GraphQL refused calls for about 30 minutes, twice, with primary quota near full.
- Q1 Why refusals? A1 OBSERVED (#4607 comment): secondary limit on the shared account. Primary showed 4,669 and 4,752 of 5,000.
- Q2 Why was the account busy? A2 OBSERVED: 9 agents polled PR checks while about 14 PRs ran CI, on one identity (#4607 subject).
- Q3 Why did polling use GraphQL? A3 OBSERVED: `get_pr_checks.py:5` is GraphQL only.
- Q4 Why not catch it early? A4 INFERRED: `gh api rate_limit` showed a healthy budget, which hid the cause (same trap as closed #4690).
- Q5 Why does no REST path exist? A5 UNKNOWN: a search of closed and open issues for `get_pr_checks GraphQL` found only #3574. No issue tracks a REST path.
- Root cause: the check-status script has one transport, and the shared account has one budget.
- Fix: poll through REST check-runs at 5-minute intervals (used, worked). Memory is in #6317. Script change is a finding for the owner.

**Item 5. A check looked missing and a bypass was claimed**

Problem: the orchestrator said the merge used an admin bypass, then retracted (relayed).
- Q1 Why look missing? A1 OBSERVED: the check-runs endpoint returns 30 per page. #6320 has 152 runs, #6314 has 164.
- Q2 Why claim a bypass on that? A2 UNKNOWN (relayed): the claim came before the paginated read.
- Q3 Why before? A3 INFERRED: a merge that succeeded with a "missing" check looked like a bypass, and the explanation was written first.
- Root cause: an inference about a gate was stated as fact before the gate's evidence was complete. FAILURE-MODES class 4 in claim form.
- Fix: do not state a bypass until every required check name is matched in the paginated list. Pagination memory is in #6317.

**Items 4, 6, 7** have short chains.
- Item 4. Q: why `git stash; git stash pop`? INFERRED: used as a cheap "is the tree clean" guard. The stash stack is shared across worktrees, so the pop can take another agent's entry. Rule exists at `orchestrator.shared.md:348` and in the memory above. It was not in the contract until step 3a was added. Fix: guard with `git status --porcelain`, never stash.
- Item 6. Q: why `timeout 110` on push? INFERRED: a bound to stop a hung push. It kills pre-push hooks and leaks scratch. Covered by #6317 memory and contract step 3c.
- Item 7. Q: why was the rule recorded backwards? OBSERVED: `pr_description.py:5` flags a file the description names that is not in the diff. INFERRED: the agent read "must match the diff" as "diff files must be named". The reverse direction is a WARNING only. No memory holds the direction.

### Fishbone (item 1)
- Prompt: contract had no cap and no stash ban at first.
- Tools: ratchet scripts leak on SIGTERM; `df -h` hides inodes.
- Context: wave cap sits in an agent template only.
- Dependencies: tmpfs inode cap 1,048,576; harness output under `/tmp`.
- Sequence: 12 agents started together, not in waves.
- State: leaked directories accumulate across killed pushes.
- Cross-category pattern: Prompt and Context both reduce to "the limit was not in the brief".

### Patterns and Shifts
- A partial read treated as whole: GraphQL quota (item 3), check-runs page (item 5). Two instances, same session.
- A limit stated in one place and absent from the brief: wave cap, stash ban, skill source. Three instances.
- Shift: after the first failure the contract gained steps 3a, 3b, 3c. Failures became contract lines, which is the repo's pattern of replacing trust with a gate.

### Learning Matrix
- Continue: triage-first fan-out. Design gate before hook work. Push-lock plus throttle.
- Change: unverified shared brief. Unbounded wave. GraphQL-only status polling.
- Idea: a sample-edit check for any brief that names source paths.
- Invest: REST path in the check-status script.

## Phase 2: Diagnosis

### Successes (Tag: helpful)
| Strategy | Evidence | Impact | Atomicity |
|----------|----------|--------|-----------|
| Triage each issue before any implementer | #5417 not planned, #5390 completed, both at 05:36Z; 6 issues partly done (relayed) | 8 | 85% |
| Design gate before building a hook | #5851 close comment; ADR-097; #6314 is 4 files | 9 | 90% |
| Throttled resume with the push-lock | 212 lock files in `~/src/scratch/locks`; merges 09:26 to 09:40Z | 7 | 80% |
| Retract a claim after the paginated read | item 5 (relayed) | 6 | 80% |

### Failures (Tag: harmful)
| Strategy | Error Type | Root Cause | Prevention | Atomicity |
|----------|------------|------------|------------|-----------|
| 12 concurrent pre-push runs | Resource exhaustion | Cap not in the brief | Carry cap, check `df -i` | 88% |
| Shared brief with unverified source path | Confident incorrectness | No sample edit | Build one edit first | 88% |
| `git stash; git stash pop` as a guard | Shared state | Repo-global stack | `git status --porcelain` | 90% |
| Read first page as all runs | Partial read | Default page size 30 | `--paginate` | 90% (in #6317) |
| `timeout` around push | Killed hooks | Wrapper kills child | No wrapper | 85% (in #6317) |

### Near Misses
| What Almost Failed | Recovery | Learning |
|--------------------|----------|----------|
| Owner stash popped | Recovered, owner stash intact | A guard that touches shared state needs no shared state |
| Bypass claim | Retracted before use | Gate claims wait for the complete list |
| Hook for #5851 | Design gate stopped it | Check the ADR index before building |

### Traceability Health
Not applicable. No spec artifacts changed in this retro.

## Phase 3: Decisions

### Action Classification

| Class | Finding | Action |
|-------|---------|--------|
| Keep | Triage-first, design gate, push-lock throttle | TAG helpful |
| Add | Verify a brief with one real edit | memory candidate |
| Add | Carry the wave cap into a hand-written brief | memory candidate |
| Add | Status-guard without stash | memory candidate |
| Add | Description rule direction | memory candidate |
| Modify | `ci-check-runs-rest-call-needs-paginate` (in #6317) | add the retracted bypass claim as evidence, after #6317 merges |

Rules vs memories vs skills vs issues: no new always-on rule (the cap duplicates `orchestrator.shared.md:347`, and `AGENTS.md` bars growth without displacement). All four additions are memories. No skill edit. Two repo findings go to the owner as potential issues.

### SMART Validation
Each candidate names one action, one trigger, and one source. Learning 1 rests on one incident (n=1). Learning 4 rests on one validator docstring and one relayed error (n=1).

### Action Sequence
1. Merge #6317 (no dependency).
2. Persist the four memory candidates from the owning checkout (depends on 1 for index).
3. Owner decides the Findings table (no dependency).

## Phase 4: Extracted Learnings

### Learning 1
- **Statement**: Copy the orchestrator wave cap and stash ban into every hand-written fan-out brief.
- **Atomicity Score**: 80%
- **Evidence**: cap at `orchestrator.shared.md:347-348`; about 12 concurrent runs, #6292.
- **Skill Operation**: ADD
- **Target Skill ID**: orchestration/orchestration-carry-the-wave-cap-into-the-brief

### Learning 2
- **Statement**: Run one real edit through the build before a brief names a source path.
- **Atomicity Score**: 90%
- **Evidence**: ship contract 3b CORRECTION; `build_all.py` reverts `src/` edits.
- **Skill Operation**: ADD
- **Target Skill ID**: orchestration/orchestration-prove-a-brief-source-path-with-one-edit

### Learning 3
- **Statement**: Guard a clean tree with `git status --porcelain`, never `git stash; git stash pop`.
- **Atomicity Score**: 92%
- **Evidence**: owner stash popped by an agent (relayed); `git-stash-is-shared-across-every-worktree.md`.
- **Skill Operation**: ADD
- **Target Skill ID**: git/git-guard-a-clean-tree-with-status-not-stash

### Learning 4
- **Statement**: A file named under the PR `## Changes` heading must appear in the diff.
- **Atomicity Score**: 90%
- **Evidence**: `scripts/validation/pr_description.py:5`; direction recorded backwards by one agent (relayed).
- **Skill Operation**: ADD
- **Target Skill ID**: github/github-pr-description-named-files-must-be-in-the-diff

### Learning 5 (not extracted, duplicate)
- Pagination, GraphQL secondary limit, tmp inode cap, killed-hook markers, skill source tree, 5851 native-cap decision: all in #6317. Similarity above 70%. Decision: reference only.

## Skillbook Updates

### ADD
```json
{"skill_id":"orchestration-carry-the-wave-cap-into-the-brief","statement":"Copy the orchestrator wave cap and stash ban into every hand-written fan-out brief.","context":"Writing a ship contract or prompt for 5 or more parallel agents.","evidence":"#6292; orchestrator.shared.md:347-348","atomicity":80}
{"skill_id":"orchestration-prove-a-brief-source-path-with-one-edit","statement":"Run one real edit through the build before a brief names a source path.","context":"Any shared brief that tells agents where to edit.","evidence":"ship contract 3b CORRECTION, 2026-10-12","atomicity":90}
{"skill_id":"git-guard-a-clean-tree-with-status-not-stash","statement":"Guard a clean tree with git status --porcelain, never git stash then pop.","context":"Any agent checking for local changes in a repo with linked worktrees.","evidence":"owner stash popped, 2026-10-12 (relayed)","atomicity":92}
{"skill_id":"github-pr-description-named-files-must-be-in-the-diff","statement":"A file named under the PR ## Changes heading must appear in the diff.","context":"Writing or fixing a PR body before validate_pr_description.","evidence":"scripts/validation/pr_description.py:5","atomicity":90}
```

### UPDATE

| Skill ID | Current | Proposed | Why |
|----------|---------|----------|-----|
| ci/ci-check-runs-rest-call-needs-paginate (after #6317 merges) | Pagination warning | Add: do not claim a bypass until every required name matches the paginated list | Item 5 |

### TAG

| Skill ID | Tag | Evidence | Impact |
|----------|-----|----------|--------|
| git/git-stash-is-shared-across-every-worktree | helpful, not applied | Item 4 | Lesson existed, the contract omitted it |
| `.claude/rules/push-lock.md` | helpful | Merges 09:26 to 09:40Z | 7 |
| `.claude/rules/tool-use-hook-bar.md` | helpful | #5851 design gate | 9 |

### REMOVE

| Skill ID | Reason | Evidence |
|----------|--------|----------|

## Deduplication Check

| New Skill | Most Similar | Similarity | Decision |
|-----------|--------------|------------|----------|
| carry the wave cap | `orchestrator.shared.md:347` (agent text, not memory) | Medium: same cap, different surface | ADD |
| prove a brief source path | #6317 skill-support-files memory | Low: that one names the tree, this one names the check | ADD |
| guard with status | git-stash-is-shared-across-every-worktree | Medium: same hazard, this gives the replacement command | ADD |
| description direction | none found in memory index | Low | ADD |

## Phase 5: Persist and Close

### Memory Persistence

| Learning | Atomicity | Existing Match | Result |
|----------|-----------|----------------|--------|
| 1 wave cap in brief | 80% | none | Not written |
| 2 prove source path | 90% | none | Not written |
| 3 status guard | 92% | stash memory | Not written |
| 4 description direction | 90% | none | Not written |

Not written: this retro ran in a linked worktree. `universal.md` MUST NOT 11 routes memory writes through the owning checkout. The handoff lists the candidates.

### +/Delta

#### + Keep
- Paginated REST reads settled two relayed claims. #6320 was listed pending and had merged. Page one held 30 of 152 runs.
- Reading #6316 and #6317 diffs first cut four duplicate learnings.

#### Delta Change
- Seven friction items have no timestamps. Raw transcripts would turn UNKNOWN to OBSERVED.
- The request's counts ("about 12", "several") cannot be checked. Ask the orchestrator to log agent counts per wave.

### Delta Triage

#### Actionable Items Identified

| Delta Item | Category |
|------------|----------|
| No failure-mode class for shared-host resource exhaustion | Missing Documentation |
| Wave cap exists only in the orchestrator agent template | Process |
| `get_pr_checks.py` has no REST path | Tool Gap |
| Harness output directory ignores `TMPDIR` | Tool Gap |
| `.claude/AGENTS.md` opening line reads as if `src/claude` is the origin | Missing Documentation |

#### Findings for the owner

| Item | Evidence (path:line) | Proposed action | Class |
|------|----------------------|-----------------|-------|
| Propose a FAILURE-MODES class for shared-host resource exhaustion under unbounded fan-out, with an ADR | `.claude/rules/retros.md:28`; `.agents/governance/FAILURE-MODES.md:19-30` | Draft the ADR and the class 13 entry citing #6292 | Requested improvement |
| Wave cap applies only inside the orchestrator agent | `templates/agents/orchestrator.shared.md:347`; no match in `templates/rules/` | Decide whether a one-line pointer belongs in the ship or push-pr skill. Not a new always-on rule | Optional enhancement |
| Check-status script reads GraphQL only, so shared-account polling hits the secondary limit | `.claude/skills/github/scripts/pr/get_pr_checks.py:5`; #4607 comment 2026-10-12T08:11:42Z | Add a REST check-runs path with `--paginate`. No open issue tracks it | Optional enhancement |
| `TMPDIR` does not move the harness per-call output directory | #6292 body; `ci-tmp-inode-cap` memory in #6317 | Check Claude Code docs for a temp-directory setting. UNKNOWN whether one exists | Optional enhancement |
| `.claude/AGENTS.md` line 3 calls `.claude/` a binplaced copy of `src/claude/`, which invites the wrong source tree for skill support files | `.claude/AGENTS.md:3,8` | Add "skill support files originate here" to line 3 | Optional enhancement |

No Blocker rows. No issue filed by this retro: `.claude/skills/retrospective/SKILL.md` Phase 5 bars it, and no per-item owner authorization exists. #6292 already tracks the scratch leak.

### ROTI Assessment

**Score**: 2

**Benefits Received**:
- Two relayed claims corrected against GitHub (#6320 state, check-runs page size).
- Four atomic memory candidates, none duplicating #6316 or #6317.
- Five owner findings, each with a path.

**Time Invested**: one session of reads and GitHub queries.

**Verdict**: Continue.

### Helped, Hindered, Hypothesis

### Helped
- Merge timestamps from REST gave a trace without transcripts.
- The closed issues #4148 and #5436 showed the cap existed and where.

### Hindered
- Most friction items have no artifact. Claims about agent counts and durations stay UNKNOWN (relayed).
- `gh search issues` returned no rows for every query. `gh api search/issues` worked.

### Hypothesis
- If the orchestrator logs agents per wave and `df -i /tmp` before each wave to the per-issue handoff, the next sweep's retro turns item 1 from INFERRED to OBSERVED.

## Retrospective Handoff

### Skill Candidates

| Skill ID | Statement | Atomicity | Operation | Target |
|----------|-----------|-----------|-----------|--------|
| orchestration-carry-the-wave-cap-into-the-brief | Copy the orchestrator wave cap and stash ban into every hand-written fan-out brief. | 80% | ADD | - |
| orchestration-prove-a-brief-source-path-with-one-edit | Run one real edit through the build before a brief names a source path. | 90% | ADD | - |
| git-guard-a-clean-tree-with-status-not-stash | Guard a clean tree with git status --porcelain, never git stash then pop. | 92% | ADD | - |
| github-pr-description-named-files-must-be-in-the-diff | A file named under the PR ## Changes heading must appear in the diff. | 90% | ADD | - |

### Memory Updates

| Entity | Type | Content | File |
|--------|------|---------|------|
| Wave cap in brief | Skill | Learning 1 | `.serena/memories/orchestration/orchestration-carry-the-wave-cap-into-the-brief.md` |
| Prove source path | Skill | Learning 2 | `.serena/memories/orchestration/orchestration-prove-a-brief-source-path-with-one-edit.md` |
| Status guard | Skill | Learning 3 | `.serena/memories/git/git-guard-a-clean-tree-with-status-not-stash.md` |
| Description direction | Skill | Learning 4 | `.serena/memories/github/github-pr-description-named-files-must-be-in-the-diff.md` |
| Paginate memory | Pattern | Add retracted bypass claim, after #6317 merges | `.serena/memories/ci/ci-check-runs-rest-call-needs-paginate.md` |

### Git Operations

| Operation | Path | Reason |
|-----------|------|--------|
| git add | `.project-toolkit/retrospective/2026-10-12-v070-p2-sweep-resource-and-contract.md` | Retrospective artifact |

### Handoff Summary

- **Skills to persist**: 4 candidates (atomicity >= 70%)
- **Memory files touched**: none written; 4 new and 1 update proposed
- **Blockers for the owner**: 0
- **Recommended next**: skillbook from the owning checkout, after #6317 merges
