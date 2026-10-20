# Retrospective: 42-issue sweep and round 2 (2026-10-17 to 2026-10-19)

## Session Info
- **Date**: 2026-10-19
- **Agents**: orchestrator (main session), 42 triage agents with a GPT 5.6 Sol second opinion, 32 wave-1 fix agents, 19 wave-2 continuation agents and 10 fresh issue agents, 36 wave-3 ship agents, 4 security reviewers for verifier hunks, round-2 workflow (112 agents), Claude Opus 5.5 fallback reviewers
- **Task Type**: Bug
- **Outcome**: Partial

## Phase 0: Data Gathering

### Scope and Evidence Base

Scope: the 42-issue sweep of `rjmurillo/ai-agents` (plus `rjmurillo/ubuntu-machine-config` PRs #218 to #223) from 2026-10-17 to 2026-10-19, and its round 2 (post-merge audit, shepherd, triage and fix).

Evidence base: scratchpad files `triage.json`, `fix.json`, `wave2.json`, `wave3.json`, `round2.json`, and `secreview.json`, parsed with Python and never read whole; GitHub issues #6667, #6722, #6742, #6745, #6747 and PRs #6695, #6718, #6746, #6749, #6750 read through the `github` skill scripts; `git log origin/main`. No session log exists: session log creation is discontinued (`.claude/rules/universal.md`, MUST NOT 10). Each claim is marked OBSERVED (a tool result or file read in this pass), INFERRED (a reading of the evidence), SUPPLIED (a session fact the orchestrator gave, not found in the files), or UNKNOWN. Per `.claude/rules/retros.md` MUST 5, this critiques processes and artifacts, not people. Times are local (UTC-07:00) unless marked Z.

Triggers: the user corrected the work explicitly (label audit, decision D2), and `main` went red (the ADR-083 review-by date reds the required `Run Python Tests` check on every branch, #6742).

### Evidence Links

- Mid-turn label fan-out: `wave2.json` key `labels` (38 audited labels); `.serena/memories/orchestrator-observations.md` (PR #6749, merge `aab0bb0587`, 2026-10-18)
- Review loops: `wave2.json` key `cont` (19 PRs, 76 rounds); issue [#6745](https://github.com/rjmurillo/ai-agents/issues/6745); fix [#6750](https://github.com/rjmurillo/ai-agents/pull/6750), merge `62bcbe976d` (2026-10-19)
- Round cap: `src/claude/skills/review/SKILL.md:44` (3 rounds); `check_pr_round_cap.py` default 5
- ADR-083 red check: issue [#6742](https://github.com/rjmurillo/ai-agents/issues/6742), run 39178372754; fix [#6746](https://github.com/rjmurillo/ai-agents/pull/6746), merge `7e43f7f89d` (2026-10-18T19:49:23-07:00)
- Baseline refusal: `scripts/validation/check_adr_lifecycle.py:1378-1379` ("The baseline may only shrink"); `scripts/validation/adr_lifecycle_baseline.json` description ("never added or raised")
- ADR-119 mid-run merge: [#6718](https://github.com/rjmurillo/ai-agents/pull/6718), merge `5d69fdbd8d` (2026-10-18T11:17:29-07:00); breakage [#6722](https://github.com/rjmurillo/ai-agents/issues/6722); fixes [#6736](https://github.com/rjmurillo/ai-agents/pull/6736) `ace3602e5f` (2026-10-18) and [#6748](https://github.com/rjmurillo/ai-agents/pull/6748) `1721f61821` (2026-10-18T22:33:38-07:00)
- Semantic conflict: [#6674](https://github.com/rjmurillo/ai-agents/pull/6674) merge `a782716add` (2026-10-18T20:16:04-07:00) before [#6695](https://github.com/rjmurillo/ai-agents/pull/6695) merge `46977580f1` (2026-10-18T21:56:54-07:00); `round2.json` names `detect_stale_bot_review.py:388-389` returning `_CI_UNKNOWN` for the old `{"AllPassing": True}` fixture
- Verifier security review: `secreview.json`; merges `71ea6ba983` (#6694), `46977580f1` (#6695), `08994b6190` (#6701), `7ddf410788` (#6716), all 2026-10-18 or 2026-10-19
- Semgrep io_uring: [#6740](https://github.com/rjmurillo/ai-agents/pull/6740), merge `6baae9f616` (2026-10-18T16:59:54-07:00)
- Pre-push collection flake: issue [#6747](https://github.com/rjmurillo/ai-agents/issues/6747) (2026-10-19)
- Prior retro: `.project-toolkit/retrospective/2026-10-13-issue-sweep-fanout.md`; its memory commit `7862817b8c` (2026-10-13, PR #6460)

### Failure Mode Classification

Against `.agents/governance/FAILURE-MODES.md` (index lines 17-31, 13 classes on 2026-10-19 at `12fb85c119`):

| Failure | Class | Why |
|---------|-------|-----|
| Mistake 1: relayed label request acted on by about 20 subagents | No match. Nearest is 7 (Self-Contained Agent Delegation Failure) | Each subagent had its own task context. What none had was an owner for repo-wide state. The 2026-10-13 retro proposed a class for fan-out resource exhaustion, and class 13 now names a different failure (state conflation in a boolean guard). Both incidents are one shape: a shared resource with no owner under parallel delegation. `.claude/rules/retros.md` MUST 2 asks for a linked ADR; this retro does not write one, because a new class is an owner decision. See Findings for the owner |
| Mistake 2: up to 9 fix-and-review rounds per PR | 12. Post-completion continuation | The bounded round counted 0 findings on 4 of 6 PRs. Those PRs met their contract rounds earlier, and the loop kept going because each round raised new scope |
| Mistake 3: option A offered without running the gate | 9. Confident-Incorrectness Recurrence | An effort estimate was stated as fact without running `check_adr_lifecycle.py`, which refuses the option |
| Mistake 4: launch with `args.pending = '__FROM_FILE__'` | 7. Self-Contained Agent Delegation Failure (delegator side), recurrence | Same class as the 2026-10-13 `__FILL__` launch. The guard existed only in memory |
| Second `pgrep -f` self-match in wave 2 | 7, recurrence of the 2026-10-13 `pkill` self-match | Wave-2 quirks record two agents whose `pgrep -f` matched their own monitor shells |

### 4-Step Debrief

**Step 1: Observe (facts only)**
- OBSERVED (`triage.json`): 42 issues triaged. Final verdicts: FIX 24, BLOCKED_HUMAN 12, CLOSE_FIXED 3, KEEP_TRACKER 3. 35 of 42 were arbitrated. The Sol second opinion ran on 16 of 42; 26 failed, 12 of them citing "out of credits". Where it ran, it agreed on 7 of 16.
- OBSERVED (`fix.json`): wave 1 opened 33 PRs for 32 items. 30 reached PR_OPENED, 1 NO_CHANGE_NEEDED (#6149), 1 BLOCKED (#6506 batch 4: four local commits, none pushed). Agents logged 75 noticed items, filed 1 issue, and recorded 6 eureka notes.
- OBSERVED (`wave2.json`): 19 continuation PRs ran 76 review rounds (rounds 1 to 5 of wave 2). Sol completed 8 of 76; the other 68 recorded an "out of credits" Sol error and fell back to Opus. After 5 wave-2 rounds, six PRs still had 1 to 3 must-fix findings: #6676 (1), #6681 (1), #6686 (2), #6687 (2), #6690 (3), ubuntu-machine-config #220 (2).
- SUPPLIED: wave 1 ran up to 4 rounds per PR before wave 2, for up to 9 in total. `fix.json` summaries cite "round 3 findings" on most items, so wave 1 ran at least 3.
- OBSERVED (`wave2.json`): the label audit covered 38 agent-applied labels (24 issues, 12 PRs, 2 ubuntu-machine-config PRs) and set keep=false on 12. SUPPLIED: 13 removed. UNKNOWN: where the 13th removal is recorded.
- SUPPLIED: the user's label request reached about 20 running subagents. One created `blocked:human`; the orchestrator created `blocked:owner-action`. The orchestrator consolidated on `blocked:human`. Policy denied `gh label delete`, so the empty label remains. OBSERVED: `round2.json` contains `blocked:human` 23 times and `blocked:owner-action` 3 times.
- OBSERVED (`wave3.json`): 36 ship agents. MERGED 16, BLOCKED_CI 9, BLOCKED_HUMAN 7, READY_NOT_MERGED 3, FAILED 1. Of the 9 BLOCKED_CI, 7 were blocked by `Verify dispatch closure against base` (#6722), 1 by the ADR-083 red `Run Python Tests` (#6681), and 1 by `semgrep-cloud-platform/scan` (#6676). Two stragglers merged (#6740, #6721).
- OBSERVED (`secreview.json`): 4 security reviews of verifier hunks (#6694, #6695, #6701, #6716). Each returned APPROVE_WITH_NOTES with `can_weaken_gate: false`, carrying 9, 11, 8, and 10 notes. All four merged after owner approval.
- OBSERVED (#6742): ADR-083 `review-by: 2026-10-18` passed and moved `review-by-past-due` from 1 to 2, against a baseline of 1. The required `Run Python Tests` check went red on every branch. Issue opened 2026-10-19T00:04Z; review held 00:18Z; owner decisions posted 02:11Z; #6746 merged 02:49Z.
- SUPPLIED: before the review, the orchestrator offered option A (add ADR-083 to `adr_lifecycle_baseline.json`) as minutes of work without running `check_adr_lifecycle.py`. OBSERVED: the gate refuses baseline growth (`check_adr_lifecycle.py:1378-1379`). The owner then answered decision D2 and four ADR questions (#6742 comment, 2026-10-19T02:11Z).
- OBSERVED (#6722, `git log`): #6718 (ADR-119 symlinks) merged from another session at 11:17 on 2026-10-18. From then on, the dispatch closure check reported 14 files "not in the base ref" on every PR. #6748 merged at 22:33.
- OBSERVED (`round2.json`): round 2 ran 112 agents, 10,070,341 tokens, and 2,618 tool calls. 24 fix agents failed with "You've hit your weekly limit". The Sol post-merge audit ran on 0 of 45 PRs. Sol issue triage ran on 1 of 19.
- OBSERVED (`round2.json`): the fallback audit of 45 PRs confirmed 35 findings, refuted 263, and flagged 259. Round-2 issue triage gave FIX 9, BLOCKED_HUMAN 4, KEEP_TRACKER 4, CLOSE_FIXED 2. 5 issue fixes merged.
- SUPPLIED: the final-round launch passed `args.pending = '__FROM_FILE__'`, ran 0 agents, and was relaunched with an `Array.isArray` guard. UNKNOWN: the scratchpad has no copy of the workflow script (search for `__FROM_FILE__` and `Array.isArray` found no sweep file).
- OBSERVED (`round2.json`): `#6674` merged tests that fed `{"AllPassing": True}` with no `RequiredState`. #6695's stricter `_ci_state` returned `_CI_UNKNOWN` for that fixture, so both tests reported NOT_READY. This surfaced at the full-suite pre-push run, not in CI on either PR.
- OBSERVED (`wave2.json` quirks): 2 agents logged `pgrep -f` matching their own monitor shells. 3 logged compound Bash commands denied by permissions. 1 logged that semgrep did not hit io_uring ENOMEM after #6740.
- OBSERVED (`fix.json` summaries): several pushes cite "disk check (63G)" before push. No ENOSPC halt is recorded this sweep.
- SUPPLIED: a shared-scratchpad body file collision led to per-agent private temp dirs. UNKNOWN: which PR or comment the collision hit; no scratchpad file records it.

**Step 2: Respond (reactions)**
- Pivots: open-ended review to a bounded contract (diff-introduced defects plus unmet ACs); two label names to one; Sol-first review to Opus fallback; shared scratchpad to private temp dirs.
- Retries: the final-round relaunch after `__FROM_FILE__`; ship agents re-ran the dispatch closure check (attempts 1 and 2) on #6669, #6674, and #6688.
- Escalations: D2 and four ADR-083 questions (#6742); four verifier approvals; label consolidation; `gh label delete` denied by policy.
- Blocks: `Run Python Tests` red on every branch (#6742); dispatch closure red on every PR (#6722); Claude weekly limit (24 agents); Codex credits (twice).

**Step 3: Analyze (interpretations)**
- INFERRED: the costliest process loss was the review loop. Its exit test ("no new issues") depended on a reviewer whose scope had no bound. The round cap bounded cost on paper, but the user instruction was read as overriding it, so nothing bounded the loop.
- INFERRED: guards that went into prompt text after 2026-10-13 held. The disk check before push appears in wave-1 summaries, and no ENOSPC recurred. Guards stored only in Serena memory recurred: launch-arg validation (`orchestration/orchestration-observations.md:66`) and `pgrep` self-match (line 67). Memory is retrieval, not activation.
- INFERRED: both this sweep and the 2026-10-13 sweep failed on a shared resource with no owner. Then it was disk and inodes; now it was repo labels and reviewer credit. Per-item delegation is sound. The gap is the resources every item touches.
- Bias guard (identity check): the user's instruction "repeat recursively until no new issues" is the comfortable thing to blame. The evidence points at an approach, open-ended adversarial review, not at the instruction. Bounded review on the same six PRs converged in one round. The review skill's own cap is also not the hero: it bounds rounds, and #6745 shows a cap stops a loop without making it converge.

**Step 4: Apply (actions)**
- Freeze the finding contract after round 1 (done: #6750).
- Name one owner for any shared-state mutation in a fan-out brief. Relayed messages are report-only for subagents.
- Run the gate a decision option touches before offering the option.
- Move the launch-arg guard from memory into the workflow script source the orchestrator reuses.

### Execution Trace

| Time | Agent | Action | Outcome | Energy |
|------|-------|--------|---------|--------|
| 10-17 20:45 | triage (42) | Triage with Sol second opinion | 42 verdicts; Sol failed on 26 (12 cite out of credits) | High |
| 10-18 05:45 | fix wave 1 (32) | Fix, review up to 4 rounds | 33 PRs; 1 blocked unpushed | High |
| 10-18 (time UNKNOWN) | user, then about 20 subagents | Mid-turn label request relayed | Two labels; 12 or 13 of 38 later removed | Sad |
| 10-18 11:12 | wave 2 (19 + 10) | 5 more review rounds; 10 fresh issues | 76 rounds, Sol 8 of 76; 6 PRs did not converge | Stalled |
| 10-18 11:17 | another session | #6718 (ADR-119) merges | Dispatch closure red on every PR (#6722) | Blocked |
| 10-18 16:59 | fix agent | #6740 `EIO_BACKEND=posix` merges | Semgrep io_uring ENOMEM fixed | High |
| 10-18 17:00 | CI | ADR-083 review-by passes at 00:00Z | `Run Python Tests` red on every branch | Blocked |
| 10-18 17:04 | orchestrator | Files #6742; offers option A | Option A refused by gate; D2 plus 4 questions | Sad |
| 10-18 17:12 | wave 3 (36) | Ship | 16 merged, 9 BLOCKED_CI, 7 BLOCKED_HUMAN | Medium |
| 10-18 17:14 | orchestrator | Files #6745 (frozen contract) | Bounded round: 0 counted on 4 of 6 | High |
| 10-18 19:17 | security (4) | Review verifier hunks | 4 APPROVE_WITH_NOTES, 0 can weaken a gate | High |
| 10-18 19:49 | owner, orchestrator | #6746 merges ADR-083 amendment | Required check green again | High |
| 10-18 20:16 to 21:56 | ship | #6674 then #6695 merge | Semantic test conflict caught at pre-push | Medium |
| 10-18 22:33 | fix agent | #6748 merges | #6722 closed 22:34 | High |
| 10-19 (time UNKNOWN) | orchestrator | Final-round launch `__FROM_FILE__` | 0 agents; relaunch with `Array.isArray` | Stalled |
| 10-19 to 19:47 | round 2 (112) | Audit 45, shepherd 6, triage 19 | Weekly limit killed 24 fix agents; Sol 0 of 45 | Medium |
| 10-19 19:48 | owner | #6750 merges | Frozen finding contract in `review` | High |

#### Timeline Patterns
- Every hard block came from a shared dependency the sweep did not own: a required check (ADR date), a non-required check (ADR-119), reviewer credit, and the weekly limit.
- Energy rose each time a bound replaced an open loop: the bounded review round, the security review before the owner ask, and `EIO_BACKEND=posix`.

#### Energy Shifts
- High to stalled at wave 2: 76 rounds with no trend to zero (for example #6686 went 1, 2, 4, 1, 2 must-fix).
- Stall points: dispatch closure red for about 11h16m (11:17 to 22:33 on 10-18); `Run Python Tests` red for about 2h49m (00:00Z to 02:49Z on 10-19, INFERRED start at the UTC date rollover).

### Outcome Classification

**Mad (Blocked)**
- `Run Python Tests` red on every branch for about 2h49m (#6742).
- Dispatch closure red on every PR for about 11h16m; 7 wave-3 PRs blocked (#6722).
- Weekly limit killed 24 round-2 fix agents.
- Codex credits ran out twice; Sol ran 0 of 45 audits.
- Six PRs did not converge after 5 wave-2 rounds.

**Sad (Suboptimal)**
- Two label names; 12 (SUPPLIED: 13) of 38 labels removed.
- Option A offered without running the gate; two extra owner decision rounds.
- `__FROM_FILE__` launch ran 0 agents (recurrence).
- `pgrep -f` self-match in 2 agents (recurrence).
- #6674 and #6695 test conflict found only at pre-push.
- #6506 batch 4: four commits left unpushed (BLOCKED).
- 3 READY_NOT_MERGED: #6686 and #6711 stopped with pushes in flight; ubuntu-machine-config #218 waited on merge order.
- Shared-scratchpad body collision (SUPPLIED).

**Glad (Success)**
- Bounded review round: 0 counted findings on 4 of 6 PRs; 1 real defect on each of the other 2 (#6676, #6681).
- Security review of verifier hunks before the owner ask: 4 of 4 approved and merged.
- `EIO_BACKEND=posix` (#6740) cleared semgrep io_uring ENOMEM.
- Per-agent private temp dirs after the collision.
- ADR-083 criteria re-measured, not copied from the pre-written amendment (#6742).
- #6750 landed the frozen finding contract.
- No disk exhaustion; pushes cite a disk check.
- 16 wave-3 merges, 2 straggler merges, 5 round-2 issue fixes merged.

**Distribution**: Mad 5, Sad 8, Glad 8. Success rate by event count: 8 of 21 (38%), up from 4 of 12 (33%) on 2026-10-13.

## Phase 1: Insights Generated

### Five Whys: Mistake 1, the relayed label request

**Problem:** a mid-turn user request produced two labels for one meaning, and the audit removed 12 (SUPPLIED: 13) of 38 agent-applied labels as wrong.

**Q1:** Why did two labels and wrong labels appear?
**A1:** OBSERVED (SUPPLIED for the count of 20): the harness relayed the request to about 20 running subagents, and each acted on it alone. One created `blocked:human` while the orchestrator created `blocked:owner-action`.

**Q2:** Why did each subagent act?
**A2:** INFERRED: the subagent briefs said nothing about relayed messages. A relayed user message reads as a direct instruction, so each subagent treated it as in scope.

**Q3:** Why did the label land on the wrong items?
**A3:** OBSERVED (`wave2.json` reasons): the 12 removals were items whose next step was agent work: "Normal fix PR", "Next step is agent work", "a normal fix PR with green checks". No written test said what counts as owner-only action, so each agent judged alone.

**Q4:** Why was there no owner and no test?
**A4:** INFERRED: the sweep was built per item. Repo-wide state (labels) belongs to no item, and the brief has no field that names an owner for shared state.

**Q5:** Why does the brief lack that field?
**A5:** INFERRED: the 2026-10-13 retro fixed the same shape for disk (a semaphore) but framed it as a resource budget, not as shared-state ownership. Labels, settings, and issue bodies were never in scope of that fix.

**Root Cause:** fan-out briefs name no single owner for shared-state mutations, and a relayed message reaches every running subagent.
**Actionable Fix:** the orchestrator brief names one owner (the orchestrator) for shared state. Subagents treat relayed messages that mutate shared state as report-only. A label gets a written criterion before anyone applies it.

### Five Whys: Mistake 2, review loops up to 9 rounds

**Problem:** six PRs ran up to 9 fix-and-review rounds, past the 3-round cap at `src/claude/skills/review/SKILL.md:44`, and still had open must-fix findings.

**Q1:** Why so many rounds?
**A1:** SUPPLIED: the user said "repeat recursively until no new issues". The orchestrator used "no new issues" as the exit test.

**Q2:** Why did "no new issues" never arrive?
**A2:** OBSERVED (`wave2.json`): must-fix counts did not trend to zero. #6686 went 1, 2, 4, 1, 2; #6690 went 2, 2, 2, 1, 3. OBSERVED (#6745): each round could raise pre-existing defects, nice-to-haves, and new scope.

**Q3:** Why could each round raise new scope?
**A3:** OBSERVED (#6745): the review skill capped rounds (3; `check_pr_round_cap.py` 5) but nothing bounded what a later round may count.

**Q4:** Why was the cap passed instead of escalating at round 3?
**A4:** INFERRED: the cap binds a loop "with no human checkpoint". The user instruction was read as that checkpoint, so the orchestrator relaunched instead of using the round-3 escalation (every open finding to the operator).

**Q5:** Why did the orchestrator not see the loop was diverging?
**A5:** INFERRED: no per-round finding trend was checked between waves. Wave 2 launched on wave 1's open findings, not on evidence that counts were falling.

**Root Cause:** the loop's exit test depended on an open-ended reviewer with no frozen finding contract; the cap bounds cost, not scope.
**Actionable Fix:** done in #6750 (`src/claude/skills/review/SKILL.md:50-52`): rounds after the first count only diff-introduced defects and unmet acceptance criteria. Remaining: when an instruction asks for "until clean", state once that the frozen contract defines clean.

### Five Whys: Mistake 3, option A offered without running the gate

**Problem:** the owner had to answer D2 and four ADR questions after option A turned out to be refused by the gate.

**Q1:** Why was a second decision round needed?
**A1:** OBSERVED: `check_adr_lifecycle.py:1378-1379` refuses any baseline growth: "The baseline may only shrink; fix the regression instead of recording it."

**Q2:** Why was a refused option offered?
**A2:** SUPPLIED: its effort was estimated from the file's shape (one JSON entry) without running the check.

**Q3:** Why was the check not run?
**A3:** INFERRED: every open PR was red on a required check, which pushed for a fast answer. A decision option's feasibility was treated as a recommendation, not as a claim that needs a gate result (`.claude/rules/voice.md`, "Clear The Gate Or Drop The Claim").

**Q4:** Why did the decision process not catch it?
**A4:** OBSERVED: `.claude/skills/decision-question/SKILL.md:43-47` already skips a question when "repository or safety policy mandates one option" or "reading available evidence or tools resolves the uncertainty". Nothing asks for a per-option feasibility check, so a refused option can still reach the user.

**Q5:** Why does that matter more here?
**A5:** INFERRED: the baseline file's own description says "never added or raised". One read of the file header, or one run of the check, would have removed option A.

**Root Cause:** a decision option was presented without running the gate it would change.
**Actionable Fix:** before offering an option that edits a gate's input, run the gate on that edit and cite the result in the option.

### Five Whys: Mistake 4, `__FROM_FILE__` launch

**Problem:** the final-round workflow launched with `args.pending = '__FROM_FILE__'` and ran 0 agents.

**Q1:** Why 0 agents?
**A1:** SUPPLIED: `pending` was a sentinel string, not an array, so the script found no work.

**Q2:** Why did the script accept a string?
**A2:** SUPPLIED: it had no type guard until the relaunch added `Array.isArray`.

**Q3:** Why was there no guard, after the 2026-10-13 retro asked for one?
**A3:** OBSERVED: the guard lives only in `.serena/memories/orchestration/orchestration-observations.md:66` ("Assert `Array.isArray(args)` at the top of the script"), added in `7862817b8c` (2026-10-13). A search of `templates/`, `src/claude/skills/`, `src/claude/agents/`, and `.agents/governance/` for `Array.isArray` and `__FILL__` returned 0 files.

**Q4:** Why did memory not prevent it?
**A4:** INFERRED: Serena memory activates only when someone searches it. No step searches memory before a workflow launch.

**Q5:** Why was the guard put in memory?
**A5:** INFERRED: the workflow script is written fresh each sweep through a harness skill, so the repo has no script source to hold the guard. `.claude/rules/universal.md` MUST NOT 7 warns against this: an optional memory service is not a binding.

**Root Cause:** a must-obey launch guard was stored on a retrieval-only surface with no activation step.
**Actionable Fix:** keep a reusable workflow script skeleton with the arg guard, or a launch preflight the orchestrator always runs. The same root cause covers the `pgrep -f` self-match recurrence (line 67).

### Fishbone Analysis

**Problem:** the sweep needed 3 rounds and 2 days, and left 20 of 36 wave-3 PRs unmerged at wave end.

| Category | Contributing factors |
|----------|----------------------|
| Prompt | No owner for shared state; no relayed-message rule; no frozen finding contract until #6750; no per-option feasibility check |
| Tools | `gh label delete` denied by policy; `pgrep -f` self-match; compound Bash commands denied (3 agents) |
| Context | Launch guards stored in memory only; ADR-083 pre-written amendment (re-measured, not copied) |
| Dependencies | Codex credits out twice; Claude weekly limit (24 agents); #6718 merged mid-run by another session; ADR-083 date rollover |
| Sequence | #6674 merged before #6695 without a rerun of #6695's suite against it; wave 2 launched without a finding-trend check |
| State | Shared scratchpad (collision); unpushed commits on #6506 batch 4; pushes running when agents stopped |

**Cross-category patterns**: unowned shared state appears under Prompt (labels), Dependencies (credits, other sessions), Sequence (merge order), and State (scratchpad). That cluster is the root-cause family, the same family as the 2026-10-13 disk exhaustion.

**Controllable vs uncontrollable**

| Factor | Controllable? | Action |
|--------|---------------|--------|
| Shared-state owner in briefs | Yes | Name the orchestrator as sole owner |
| Frozen finding contract | Yes | Done (#6750) |
| Option feasibility | Yes | Run the gate before offering |
| Launch arg guard | Yes | Move into a reusable script or preflight |
| Merge order between sibling PRs | Yes | Rerun the suite on the later PR after the earlier merges |
| Reviewer credit | Partly | Probe credit per wave; plan the Opus fallback |
| Weekly limit | No | Checkpoint results; resume after reset |
| Other sessions merging (#6718) | No | Watch main for red non-required checks and file once |
| ADR review-by date | Partly | List review-by dates inside the sweep window at launch |

### Force Field Analysis

**Desired state**: a guard learned in one retro is active in the next sweep.
**Current state**: 2 of the 2026-10-13 memory-only guards recurred within 6 days; the prompt-embedded disk guard held.

| Driving force | Strength | Restraining force | Strength |
|---------------|----------|-------------------|----------|
| Retros already name the guard | 3 | Workflow scripts are written fresh each sweep | 4 |
| Orchestrator template already holds a wave cap (`templates/agents/orchestrator.shared.md`) | 3 | Memory activates only on search | 4 |
| Prompt-embedded guards held (disk check) | 4 | No launch preflight exists | 3 |
| Owner reads Findings for the owner | 2 | Each sweep adds new guards, so the list grows | 2 |

Net: 12 driving, 13 restraining. Strengthen by moving guards into text that every launch reads. Reduce by giving workflow scripts a reusable skeleton.

### Patterns and Shifts

| Pattern | Frequency | Impact | Category |
|---------|-----------|--------|----------|
| Memory-only guard recurs | 2 (launch args, `pgrep` self-match) | Medium | Failure |
| Shared resource with no owner under fan-out | 4 this sweep (labels, credits, scratchpad, weekly limit); 4 on 2026-10-13 | High | Failure |
| Independent bounded check converges where open-ended does not | 2 (bounded review 4 of 6; verifier security review 4 of 4) | High | Success |
| Another session or a calendar date reds every PR | 2 (#6718, ADR-083) | High | Failure |

| Shift | When | Before | After | Cause |
|-------|------|--------|-------|-------|
| Review contract | 2026-10-18, #6745; landed #6750 2026-10-19 | Open-ended rounds to a cap | Frozen contract after round 1 | Bounded round converged 4 of 6 |
| Reviewer | Triage and wave 2 | Sol first | Opus fallback (68 of 76 rounds) | Codex credits out |
| Disk | Since 2026-10-13 | ENOSPC halts twice | No halt; disk check before push | Guard in prompts |
| Temp files | Mid-sweep | Shared scratchpad | Per-agent private temp dir | Body collision (SUPPLIED) |

Compared with the 2026-10-13 retro:

| 2026-10-13 learning | This sweep |
|---------------------|------------|
| L1 fan-out resource budget | Held for disk (no ENOSPC). Did not extend to labels or credits |
| L3 launch arg validation | Recurred (`__FROM_FILE__`); guard was memory-only |
| L4 kill by process group, not name pattern | Recurred as a `pgrep -f` self-match in 2 agents |
| L6 skeptic pass before bulk close | Held in spirit: 35 of 42 verdicts arbitrated |
| L7 file-or-report policy | 75 noticed, 1 filed in wave 1. UNKNOWN: whether the 74 others reached the owner |
| Weekly limit (88 calls) | Recurred (24 agents) |

### Learning Matrix

**Continue**: bounded review contract; security review of verifier hunks before the owner ask; re-measuring an ADR's criteria at review time; `EIO_BACKEND=posix`; per-agent temp dirs; disk check before push.
**Change**: open-ended review loops; relayed messages acted on by every subagent; decision options without a gate run; memory-only launch guards.
**Idea**: a workflow script skeleton with the arg guard; a sweep preflight that lists ADR review-by dates and reviewer credit.
**Invest**: an owner-decided failure class for unowned shared state under fan-out.

### Impact

| Area | Severity | Effect |
|------|----------|--------|
| Required CI (`Run Python Tests`) | High | Red on every branch for about 2h49m (#6742) |
| Non-required CI (dispatch closure) | High | Red on every PR for about 11h16m; 7 wave-3 PRs blocked (#6722) |
| Review throughput | High | 76 wave-2 rounds; 6 PRs unconverged until the bounded round |
| Repo labels | Medium | 12 (SUPPLIED: 13) of 38 removed; empty `blocked:owner-action` label remains |
| Owner attention | Medium | D2 plus four ADR questions after a refused option |
| Agent capacity | Medium | 24 fix agents lost to the weekly limit; Sol ran 0 of 45 audits |
| Launch hygiene | Low | One 0-agent launch, no damage |

## Phase 2: Diagnosis

### Successes (Tag: helpful)
| Strategy | Evidence | Impact | Atomicity |
|----------|----------|--------|-----------|
| Count only diff-introduced defects and unmet ACs after round 1 | Bounded round: 0 counted on 4 of 6 PRs, 1 real defect each on #6676 and #6681; landed as #6750 | 9 | 100% |
| Security-review verifier hunks before asking the owner | `secreview.json`: 4 of 4 APPROVE_WITH_NOTES, `can_weaken_gate: false`; all merged | 8 | 100% |
| Run semgrep with `EIO_BACKEND=posix` on Linux | #6740 merged; a later push hit no ENOMEM (`wave2.json` quirk) | 6 | 85% |
| Give each parallel agent a private temp dir | SUPPLIED: collision stopped after the change | 5 | 75% |
| Re-measure ADR criteria instead of copying a pre-written amendment | #6742 review: 3 of 5 criteria contradicted | 7 | 90% |

### Failures (Tag: harmful)
| Strategy | Error Type | Root Cause | Prevention | Atomicity |
|----------|------------|------------|------------|-----------|
| Every subagent acts on a relayed shared-state request | Unowned shared state | No owner field in fan-out briefs | One owner; relayed messages report-only | 100% |
| Review until "no new issues" | Post-completion continuation | No frozen finding contract | #6750 | 100% |
| Offer a gate-baseline edit as an option without running the gate | Confident incorrectness | Feasibility not treated as a gate claim | Run the gate before offering | 100% |
| Launch-arg guard kept in memory only | Delegation failure (recurrence) | Retrieval-only surface | Guard in a reusable script or preflight | 100% |
| Merge sibling PRs without rerunning the later suite | Sequence | Merge order not tracked | Rerun suite after a sibling merge | 100% |

### Near Misses
| What Almost Failed | Recovery | Learning |
|--------------------|----------|----------|
| #6674 and #6695 test conflict | Full-suite pre-push caught it before merge | CI on each PR alone missed it; the later PR needs a rerun after the earlier merges |
| ADR-083 pre-written amendment would have recorded a false fact | Review re-measured the criteria | Treat a pre-written outcome as a hypothesis (already in memory) |
| Four verifier changes could have weakened gates | Security review before the owner ask | Owner approved on evidence, not on the author's summary |
| #6506 batch 4 had four unpushed commits | Agent reported BLOCKED with SHAs | A BLOCKED report with SHAs kept the work recoverable |
| 2 PRs stopped with pushes in flight (#6686, #6711) | Reported READY_NOT_MERGED with unconfirmed remote head | Confirm a push with `git ls-remote`, not process state (wave-2 quirk) |

## Phase 3: Decisions

### Action Classification

| Class | Finding | Action |
|-------|---------|--------|
| Keep | Bounded review contract; verifier security review; `EIO_BACKEND=posix`; private temp dirs; disk check before push | Retain |
| Drop | Open-ended "until no new issues" loops; every subagent acting on a relayed message | Replace |
| Add | Shared-state owner rule; option-feasibility gate run; full-suite rerun after a sibling merge | New observations; owner decides on binding surfaces |
| Modify | Launch-arg guard and `pgrep` guidance | Move from memory to a script skeleton or preflight (owner decision) |

### SMART Validation

| Statement | S | M | A | R | T |
|-----------|---|---|---|---|---|
| Route a mid-turn shared-state request to one agent | Y | Y (labels per item) | Y | Y | Y (on a relayed message) |
| After round 1, count only diff-introduced defects plus unmet ACs | Y | Y (counted findings) | Y | Y | Y (round 2 and later) |
| Run the gate check before offering a baseline edit | Y | Y (gate exit code) | Y | Y | Y (building a decision brief) |
| Put the launch-arg guard in the workflow script | Y | Y (0-agent launches) | Y | Y | Y (at launch) |
| Security-review verifier hunks before owner approval | Y | Y (verdict per PR) | Y | Y | Y (before the ask) |
| Give each parallel agent a private temp directory | Y | N (collision evidence is SUPPLIED only) | Y | Y | Y (at spawn) |
| Rerun the full suite after a sibling merge | Y | Y (test result) | Y | Y | Y (before push) |
| Re-check reviewer credit before each wave | Y | Y (calls that ran) | Y | Y | Y (per wave) |

### Action Sequence

| Order | Action | Owner | Depends On | Blocks |
|-------|--------|-------|------------|--------|
| 1 | Done: frozen finding contract (#6750) | Repo owner | None | None |
| 2 | Persist the eight learnings as memory evidence (this change) | This retro | None | 3, 4 |
| 3 | Decide a binding surface for launch-arg and shared-state guards | Repo owner | 2 | 5 |
| 4 | Decide whether to add a failure class for unowned shared state under fan-out (ADR) | Repo owner | 2 | None |
| 5 | Add the guard to the chosen surface | Repo owner | 3 | None |

## Phase 4: Extracted Learnings

Scores below are `score_atomicity.py` results. Across 15 tries, the only penalty it applied was a missing number (-25%). 7 of the 8 final statements scored 100%, so SMART validation above is the stricter filter.

### Learning 1
- **Statement**: Route a mid-turn shared-state request to one agent; 12 of 38 relayed labels were wrong.
- **Atomicity Score**: 100%
- **Evidence**: `wave2.json` label audit (12 keep=false of 38; SUPPLIED 13); two labels created for one meaning
- **Skill Operation**: UPDATE
- **Target Skill ID**: orchestrator-observations

### Learning 2
- **Statement**: Count only diff-introduced defects plus unmet criteria after round 1; 4 of 6 converged.
- **Atomicity Score**: 100%
- **Evidence**: `wave2.json` 76 rounds; #6745 bounded round; #6750 merge `62bcbe976d`
- **Skill Operation**: TAG
- **Target Skill ID**: orchestrator-observations

### Learning 3
- **Statement**: Run the gate check before offering a baseline edit; ADR-083 option A was refused.
- **Atomicity Score**: 100%
- **Evidence**: `check_adr_lifecycle.py:1378-1379`; #6742 owner decisions comment (2026-10-19T02:11Z)
- **Skill Operation**: ADD
- **Target Skill ID**: orchestrator-observations

### Learning 4
- **Statement**: Put the launch-arg guard in the workflow script; memory-only guidance recurred after 6 days.
- **Atomicity Score**: 100%
- **Evidence**: `orchestration/orchestration-observations.md:66` added `7862817b8c` (2026-10-13); `__FROM_FILE__` launch (SUPPLIED, 2026-10-19); 0 hits for the guard in templates and skills
- **Skill Operation**: ADD
- **Target Skill ID**: orchestration/orchestration-memory-only-guards-recurred-in-the-next-sweep

### Learning 5
- **Statement**: Security-review verifier hunks before owner approval; 4 of 4 then merged.
- **Atomicity Score**: 100%
- **Evidence**: `secreview.json`; merges `71ea6ba983`, `46977580f1`, `08994b6190`, `7ddf410788`
- **Skill Operation**: ADD
- **Target Skill ID**: orchestrator-observations

### Learning 6
- **Statement**: Give each parallel agent a private temp directory; one shared scratchpad path collided.
- **Atomicity Score**: 75%
- **Evidence**: SUPPLIED only; no scratchpad record of the collision
- **Skill Operation**: ADD
- **Target Skill ID**: orchestration/orchestration-observations

### Learning 7
- **Statement**: Run the full suite before push after a sibling merge; #6674 broke #6695 tests.
- **Atomicity Score**: 100%
- **Evidence**: `round2.json` (`detect_stale_bot_review.py:388-389`, `_CI_UNKNOWN`); merges `a782716add` then `46977580f1`
- **Skill Operation**: ADD
- **Target Skill ID**: orchestration/orchestration-observations

### Learning 8
- **Statement**: Re-check reviewer credit before each wave; Sol later ran 0 of 45 audits.
- **Atomicity Score**: 100%
- **Evidence**: `triage.json` (Sol 16 of 42), `wave2.json` (8 of 76), `round2.json` (0 of 45 audits, 1 of 19 triages)
- **Skill Operation**: UPDATE
- **Target Skill ID**: orchestrator-observations

## Skillbook Updates

### ADD
```json
[
  {
    "skill_id": "orchestrator-gate-before-option",
    "statement": "Run the gate check before offering a baseline edit; ADR-083 option A was refused.",
    "context": "Building a decision brief whose option edits a gate's input",
    "evidence": "check_adr_lifecycle.py:1378-1379; issue #6742",
    "atomicity": 100
  },
  {
    "skill_id": "orchestration-memory-only-guards-recur",
    "statement": "Put the launch-arg guard in the workflow script; memory-only guidance recurred after 6 days.",
    "context": "Persisting a guard from a retro that a launch must obey",
    "evidence": "orchestration-observations.md:66 (7862817b8c, 2026-10-13); __FROM_FILE__ launch 2026-10-19",
    "atomicity": 100
  },
  {
    "skill_id": "orchestrator-verifier-security-review",
    "statement": "Security-review verifier hunks before owner approval; 4 of 4 then merged.",
    "context": "A PR changes a script the completion gate runs",
    "evidence": "secreview.json; PRs #6694 #6695 #6701 #6716",
    "atomicity": 100
  },
  {
    "skill_id": "orchestration-private-temp-dirs",
    "statement": "Give each parallel agent a private temp directory; one shared scratchpad path collided.",
    "context": "Spawning parallel agents that write body files",
    "evidence": "Session fact (supplied); no file record",
    "atomicity": 75
  },
  {
    "skill_id": "orchestration-sibling-merge-rerun",
    "statement": "Run the full suite before push after a sibling merge; #6674 broke #6695 tests.",
    "context": "Two open PRs touch the same module and one merges first",
    "evidence": "round2.json; merges a782716add then 46977580f1",
    "atomicity": 100
  }
]
```

### UPDATE

| Skill ID | Current | Proposed | Why |
|----------|---------|----------|-----|
| orchestrator-observations (mid-turn message bullet) | One owner should act and the rest should report | Add consolidation outcome, the denied label delete, and the audit's removal reasons | Evidence for the existing lesson |
| orchestrator-observations (out-of-credit bullet) | First outage, 26 of 42 triage checks | Add the later outage: 8 of 76 wave-2 rounds, 0 of 45 audits, 1 of 19 triages | Recurrence evidence |
| orchestration/orchestration-observations (line 66, launch args) | Two launches failed | Add the 2026-10-19 `__FROM_FILE__` recurrence | Recurrence evidence |
| orchestration/orchestration-observations (line 67, `pgrep`) | `pkill -f` matched its own monitor | Add the two wave-2 `pgrep -f` self-matches and `git ls-remote` as the push check | Recurrence evidence |

### TAG

| Skill ID | Tag | Evidence | Impact |
|----------|-----|----------|--------|
| orchestrator-observations (review convergence Eureka) | helpful | #6750 merged `62bcbe976d` (2026-10-19) | 9 |
| orchestrator-observations (pre-written amendment Eureka) | helpful | #6746 merged with re-measured criteria | 7 |
| orchestration/orchestration-observations (fan-out budget, line 63) | helpful | No ENOSPC this sweep; pushes cite a disk check | 8 |

### REMOVE

| Skill ID | Reason | Evidence |
|----------|--------|----------|
| none | No learning was contradicted | n/a |

## Deduplication Check

| New Skill | Most Similar | Similarity | Decision |
|-----------|--------------|------------|----------|
| Learning 1 (relayed shared state) | `orchestrator-observations.md` mid-turn bullet (PR #6749) | 90% | Augment existing bullet |
| Learning 2 (frozen contract) | `orchestrator-observations.md` review convergence Eureka | 95% | TAG only |
| Learning 3 (gate before option) | `pr-review/triage-001-verify-before-stale-closure` | 30% | Add bullet to `orchestrator-observations.md` |
| Learning 4 (memory-only guards) | `orchestration/orchestration-the-wave-cap-lives-in-the-orchestrator-template-not-in-a-hand-written-brief` | 50% (same family: binding surface; different surface pair and recurrence evidence) | New memory, linked |
| Learning 5 (verifier security review) | `orchestration/orchestration-observations.md` background commit-security bullet | 40% | Add bullet to `orchestrator-observations.md` |
| Learning 6 (private temp dirs) | none found (`search_memory.py "scratchpad temp collision"`) | under 20% | Add bullet to `orchestration/orchestration-observations.md` |
| Learning 7 (sibling merge rerun) | none found | under 20% | Add bullet to `orchestration/orchestration-observations.md` |
| Learning 8 (reviewer credit) | `orchestrator-observations.md` out-of-credit bullet | 85% | Augment existing bullet |

## Phase 5: Persist and Close

### Memory Persistence

| Learning | Atomicity | Existing Match | Result |
|----------|-----------|----------------|--------|
| 1 Relayed shared-state request | 100% | `orchestrator-observations` | Updated |
| 2 Frozen finding contract | 100% | `orchestrator-observations` | Updated (outcome appended) |
| 3 Gate before option | 100% | none | Added (bullet in `orchestrator-observations`) |
| 4 Memory-only guards recur | 100% | `orchestration/orchestration-the-wave-cap-lives-in-the-orchestrator-template-not-in-a-hand-written-brief` | Added (`orchestration/orchestration-memory-only-guards-recurred-in-the-next-sweep`) |
| 5 Verifier security review | 100% | none | Added (bullet in `orchestrator-observations`) |
| 6 Private temp dirs | 75% | none | Added (bullet in `orchestration/orchestration-observations`) |
| 7 Sibling merge rerun | 100% | none | Added (bullet in `orchestration/orchestration-observations`) |
| 8 Reviewer credit | 100% | `orchestrator-observations` | Updated |

Writes went to `.serena/memories/` files in the linked worktree, not through Serena MCP tools, which write to the main checkout (`.claude/rules/universal.md` MUST NOT 11).

### +/Delta

#### + Keep
- Parsing the six scratchpad JSON files with Python turned supplied figures into OBSERVED counts. It also found one mismatch (12 vs 13 label removals).
- Comparing against the 2026-10-13 retro exposed the main insight: prompt-embedded guards held and memory-only guards recurred.

#### Delta Change
- Record launch args and workflow script text in the scratchpad. Mistake 4 could not be checked against any file.
- Record clock times for mid-turn user messages; the label request has no timestamp.
- `score_atomicity.py` applied one penalty type (a missing number) across 15 tries, so it does not separate strong from weak learnings.

### Delta Triage

#### Actionable Items Identified

| Delta Item | Category |
|------------|----------|
| Launch-arg and `pgrep` guards live only in memory | Process Improvements |
| No failure class for unowned shared state under fan-out | Missing Documentation |
| Empty `blocked:owner-action` label remains | Process Improvements |
| `decision-question` has no per-option feasibility check | Process Improvements |
| `score_atomicity.py` gives 100% to a short statement with a number | Tool/Script Awareness |
| Workflow launch args not saved to the scratchpad | Process Improvements |

#### Findings for the owner

| Item | Evidence (path:line) | Proposed action | Class |
|------|----------------------|-----------------|-------|
| Launch-arg guard and `pgrep` self-match guidance live only in memory and recurred within 6 days | `.serena/memories/orchestration/orchestration-observations.md:66-67`; 0 hits for `Array.isArray` or `__FILL__` in `templates/`, `src/claude/skills/`, `src/claude/agents/`, `.agents/governance/` | Put both guards in a surface every launch reads (orchestrator template or a launch preflight) | Optional enhancement |
| No failure class covers unowned shared state under parallel delegation (labels, disk, credits); the 2026-10-13 proposal was not adopted, and class 13 now names a different failure | `.agents/governance/FAILURE-MODES.md:17-31` | Decide whether to add the class with an ADR, per `.claude/rules/retros.md` MUST 2 | Optional enhancement |
| Fan-out briefs name no owner for shared-state mutations; relayed messages reach every subagent | `templates/agents/orchestrator.shared.md` (no match for "relayed", "mid-turn", or "shared state") | Add one line: the orchestrator alone mutates shared state; subagents report relayed requests | Optional enhancement |
| Empty `blocked:owner-action` label remains after consolidation; `gh label delete` was denied by policy | SUPPLIED; `round2.json` still references `blocked:owner-action` 3 times | Owner deletes the label | Side quest |
| `decision-question` skips a question when tools resolve it, but does not check each option's feasibility | `.claude/skills/decision-question/SKILL.md:43-47` | Add a step: run the gate an option would change and cite the result | Optional enhancement |
| `score_atomicity.py` scored 7 of 8 final statements at 100%; its only penalty in 15 tries was a missing number | `.claude/skills/retrospective/scripts/score_atomicity.py` (this pass) | Tighten the scorer or document that SMART validation is the real filter | Side quest |
| Pre-push `tests/mutation` collection differs per xdist worker | Issue #6747 (open, 2026-10-19) | Already filed; no new action | Side quest |

### ROTI Assessment

**Score**: 3

**Benefits Received**:
- A cross-retro finding with two recurrences as evidence: guards in memory recur, guards in prompts hold.
- Four Five Whys chains, each ending in a fix or a finding for the owner.
- Supplied figures checked against files: wave-2 Sol 8 of 76, round-2 audits 0 of 45, 24 agents lost to the weekly limit, label removals 12 vs 13.

**Time Invested**: one pass. Six JSON files (about 1.25 MB) were parsed with Python, not read. Ten GitHub items were read through the `github` skill.

**Verdict**: Continue

### Helped, Hindered, Hypothesis

#### Helped
- Structured JSON results per wave made counts checkable.
- The 2026-10-13 retro gave a baseline to measure recurrence against.
- Memory commit `7862817b8c` dated the guard, which turned "it recurred" into "it recurred 6 days after it was written down".

#### Hindered
- No scratchpad record of the workflow script, the launch args, or the scratchpad collision.
- No timestamp for the mid-turn label request.
- The atomicity scorer does not separate statements.

#### Hypothesis
- If the launch-arg guard lives in a script skeleton the orchestrator copies, the next sweep has 0 placeholder launches. Test it on the next sweep launch.
