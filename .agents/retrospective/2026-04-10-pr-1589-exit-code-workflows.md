# Retrospective: PR #1589 Exit Code Workflows (fix/668-exit-code-workflows)

## Session Info

- **Date**: 2026-04-09 to 2026-04-10
- **Branch**: fix/668-exit-code-workflows
- **PR**: #1589
- **Issue**: #668 (Phase 3 exit code standardization)
- **Sessions**: 3+ (expected 1)
- **Task Type**: Bug fix / refactor
- **Outcome**: Success, but far more costly than expected

---

## Phase 0: Data Gathering

### Timeline (from git reflog and conversation evidence)

| When | What | Session |
|------|------|---------|
| Apr 9, 4:28pm | Branch created, commit `971b19d8` (bash `exit_code_handler.sh`) | 1 |
| Apr 10, 9:16am | Commit `3cb05ee9` (Python rewrite per ADR-042) | 2 |
| Apr 10, 9:16am | PR #1589 created, pushed | 2 |
| Apr 9-10 overnight | Gemini and Copilot bot reviews: 10 comments filed | -- |
| Apr 10, ~9:45am | Session 3 starts: `/pr-review 1589` | 3 |
| Apr 10, 9:48am | Commit `668c7139` (fix 2 legitimate issues) | 3 |
| Apr 10, 9:49-9:50am | All 10 threads replied and resolved | 3 |
| Apr 10, ~9:50am | User runs `/review`, triggers gstack onboarding waterfall | 3 |
| Apr 10, ~9:52am | User interrupts: "this took MANY more turns and sessions than expected" | 3 |
| Apr 10, 9:55am | Retrospective agent produces sanitized version | 3 |
| Apr 10, 9:58am | Cherry-pick to new branch, skill building begins | 3 |
| Apr 10, ~10:15am | 4 skill agents complete. User steers: "should be improvements to existing suite" | 3 |
| Apr 10, ~10:20am | Commit passes ruff but has unused variable warning | 3 |
| Apr 10, ~10:22am | Push fails: mypy errors (unparameterized dict) | 3 |
| Apr 10, ~10:25am | Fix with `dict[str, object]` causes new mypy error (`object has no .get()`) | 3 |
| Apr 10, ~10:28am | Fix with `dict[str, Any]`, push succeeds | 3 |
| Apr 10, ~10:30am | `gh pr create` blocked by hook. Must use `new_pr.py` script | 3 |
| Apr 10, ~10:32am | PR #1593 created | 3 |
| Apr 10, 4:53pm | PR #1589 merged | -- |

### 4-Step Debrief

#### Step 1: Observe (Facts Only)

**Implementation work (sessions 1-2):**
- Session 1 produced a bash implementation that violated ADR-042 (Python-first)
- Session 2 had to redo the work in Python, discarding the bash version
- This means the first session's implementation was wasted effort

**PR review work (session 3):**
- 10 bot comments, 8 stale (referenced files deleted in commit 2)
- 2 legitimate issues fixed in 1 commit
- Agent correctly identified staleness before attempting fixes

**Skill building (session 3 continued):**
- 4 skill candidates built in parallel
- User had to steer that skills belong in existing github suite, not standalone
- 3 of 4 dropped after evaluation (capability already existed or low value)
- The surviving script required 3 fix iterations (unused var, mypy x2) before push

**Tooling friction (session 3):**
- `/review` triggered gstack onboarding gates (lake intro, telemetry, proactive, routing)
- User had to manually interrupt the onboarding waterfall
- Push failed once on mypy, required 2 fix attempts
- `gh pr create` blocked by skill-first hook, required using `new_pr.py`

#### Step 2: Respond (Reactions)

- **Pivots**: Session 1 bash implementation had to be thrown out and redone in Python (ADR-042)
- **Steering required**: User intervened at least 4 times in session 3 alone:
  1. Interrupted gstack onboarding waterfall
  2. Corrected skill placement (existing suite vs standalone)
  3. Noted retrospective was inaccurate (too sanitized)
  4. Directed to check actual session history, not fabricate
- **False starts**: First mypy fix (`dict[str, object]`) created a new error
- **Blocks**: Hook blocked standard `gh pr create` command

#### Step 3: Analyze (Interpretations)

**Pattern: Session 1 wasted work.** The bash implementation was thrown out because it violated ADR-042. The agent should have checked ADR-042 before writing bash. This is a retrieval-led reasoning failure.

**Pattern: Bot reviewers create noise on multi-commit PRs.** 80% of review comments referenced deleted files. No tooling detected this automatically.

**Pattern: Retrospective agents produce sanitized output.** The first retrospective described the work as "pivots: none" and "efficiency: ~50%". The real efficiency was far lower. The retrospective agent had no access to the conversation's actual friction, only the summary provided to it.

**Pattern: Type system iteration tax.** The mypy fix required 2 attempts because `dict[str, object]` is too strict for JSON API responses. This is a known pattern with GraphQL/REST return types.

**Pattern: Tooling ceremony exceeds task complexity.** For a task that boiled down to "reply to 10 bot comments and resolve threads," the ceremony included: session protocol, gstack onboarding, skill-first hooks, pre-push validation with mypy, and mandatory script usage for PR creation.

#### Step 4: Apply (Actions)

- Add stale-comment detection to pr-comment-responder (DONE: detect_stale_pr_comments.py)
- Check ADR constraints before choosing implementation language
- Use `dict[str, Any]` for GraphQL/REST JSON responses (skip `dict[str, object]`)
- Retrospective agents need access to actual conversation friction, not just outcome summaries

### Outcome Classification

**Mad (Blocked/Failed)**
- Session 1 bash implementation discarded (violated ADR-042)
- Push failed on mypy, required 2 fix iterations
- `gh pr create` blocked by hook

**Sad (Suboptimal)**
- 8 of 10 bot comments were noise from deleted files
- Gstack onboarding waterfall interrupted review work
- Retrospective agent produced inaccurate, sanitized output
- User had to steer 4+ times in a single session
- First mypy fix created a new error

**Glad (Success)**
- Correctly identified 8/10 comments as stale before attempting fixes
- Fixed all legitimate issues in 1 commit
- All 10 threads resolved in batch
- Stale comment detection script built and shipped
- 3 low-value skill candidates correctly dropped

**Distribution**

- Mad: 3 events
- Sad: 5 events
- Glad: 5 events
- Efficiency: ~25-30% (significant rework, steering, and tooling friction)

---

## Phase 1: Generate Insights

### Five Whys: Multi-Session Duration

**Problem**: A task scoped as 1 session (reply to bot comments) required 3+ sessions.

**Q1**: Why did it require 3+ sessions?
**A1**: Session 1 produced a bash implementation that had to be discarded and redone in Python.

**Q2**: Why was bash used when ADR-042 mandates Python?
**A2**: The agent did not check ADR-042 before choosing an implementation language.

**Q3**: Why didn't the agent check ADR-042?
**A3**: Retrieval-led reasoning failure. The agent started coding before reading constraints.

**Q4**: Why does the session protocol not enforce constraint checking?
**A4**: The session gates check for Serena init and memory queries, but not for ADR constraint verification before implementation.

**Q5**: Why are ADR constraints not part of pre-implementation gates?
**A5**: The protocol assumes agents will follow AGENTS.md ("Python for new scripts, ADR-042"). No enforcement mechanism exists.

**Root Cause**: No pre-implementation ADR constraint check. Agents can skip retrieval and start coding in the wrong language.

### Five Whys: Excessive Steering

**Problem**: User had to intervene 4+ times in session 3 to correct agent behavior.

**Q1**: Why did the agent need steering?
**A1**: It followed skill instructions literally (gstack onboarding, standalone skills) without considering the user's actual goal.

**Q2**: Why did it follow instructions literally?
**A2**: Skill prompts (gstack preamble, SkillForge) have mandatory gates that fire regardless of context.

**Q3**: Why don't these gates consider context?
**A3**: They check binary state (onboarded: yes/no) not task context (is this a focused PR review?).

**Q4**: Why is task context not considered?
**A4**: Skill prompts are designed for fresh sessions, not for mid-task invocations.

**Q5**: Why aren't skill prompts context-aware?
**A5**: Design gap. Skills fire their full preamble on every invocation, including gates that only matter once.

**Root Cause**: Skills lack context-awareness. Every invocation runs the full ceremony regardless of what the user is actually trying to do.

### Learning Matrix

**Continue (What worked)**
- Classify comments by validity before attempting fixes
- Build skills in parallel with subagents
- Drop candidates that duplicate existing capability

**Change (What did not work)**
- Writing code before checking ADR constraints
- Running full skill preambles mid-task
- Retrospective agents summarizing without conversation evidence
- Using `dict[str, object]` for JSON API responses

**Ideas (New approaches)**
- Pre-implementation ADR constraint checker
- Context-aware skill invocation (skip onboarding when mid-task)
- Retrospective agent should receive raw turn count and steering events

**Invest (Long-term improvements)**
- Stale comment detection as a reusable utility (DONE)
- Lightweight session state persisted across sessions
- Enforcement mechanism for ADR constraints before code generation

---

## Phase 2: Diagnosis

| Finding | Priority | Category | Evidence |
|---------|----------|----------|----------|
| Session 1 work discarded (ADR-042 violation) | P1 | Wasted Work | Bash handler deleted in commit 2, Python rewrite required |
| 8/10 bot comments were stale | P1 | Noise | 8 referenced files deleted from commit 1 |
| User steered 4+ times in single session | P1 | Autonomy Failure | Onboarding interrupt, skill placement, retro accuracy, session evidence |
| Retrospective agent produced inaccurate output | P2 | Quality | Described as "pivots: none", real efficiency ~25% not ~50% |
| Push failed on mypy, 2 fix iterations | P2 | Tooling Tax | dict[str, object] -> dict[str, Any] via failed intermediate |
| Gstack onboarding waterfall | P2 | Ceremony | 5+ gates fired on `/review` invocation mid-task |
| gh pr create blocked by hook | P3 | Friction | Had to discover and use new_pr.py instead |

---

## Phase 3: Decide What to Do

### Action Classification

| Action | Category | Priority | Status |
|--------|----------|----------|--------|
| Add stale-file detection to github skill suite | ADD | P1 | DONE (detect_stale_pr_comments.py) |
| Use `dict[str, Any]` for JSON API responses | CONVENTION | P1 | Applied |
| Check ADR constraints before choosing implementation language | PROCESS | P1 | Open |
| Make retrospective agents cite conversation evidence | IMPROVE | P2 | Open |
| Context-aware skill invocation (skip gates mid-task) | IMPROVE | P2 | Open |

---

## Phase 4: Extracted Learnings

### Learning 1: Stale Comment Detection

- **Statement**: Check if commented files exist at PR HEAD before triaging bot review comments.
- **Atomicity Score**: 91%
- **Evidence**: 8 of 10 comments on PR #1589 targeted files deleted in commit `3cb05ee9`
- **Status**: DONE (detect_stale_pr_comments.py shipped in PR #1593)

### Learning 2: ADR Constraint Checking

- **Statement**: Read ADR constraints (especially ADR-042 for language choice) before writing implementation code.
- **Atomicity Score**: 90%
- **Evidence**: Session 1 produced bash code that violated ADR-042, wasting the entire session's implementation work.
- **Status**: Open

### Learning 3: JSON API Type Annotations

- **Statement**: Use `dict[str, Any]` for GraphQL/REST JSON responses. `dict[str, object]` breaks `.get()` chains.
- **Atomicity Score**: 95%
- **Evidence**: mypy fix attempt with `dict[str, object]` caused `"object" has no attribute "get"` error, requiring a second fix.
- **Status**: Applied

### Learning 4: Retrospective Accuracy

- **Statement**: Retrospective agents produce sanitized output when given outcome summaries instead of raw conversation evidence. They need turn counts, steering events, and failure counts.
- **Atomicity Score**: 85%
- **Evidence**: First retro said "pivots: none" and "efficiency: ~50%". Real data: 3 mad events, 5 sad events, 4+ user interventions, ~25% efficiency.
- **Status**: Open

---

## Phase 5: Honest Accounting

### Turn and Steering Count (Session 3 only)

| Metric | Count |
|--------|-------|
| User messages | ~15 |
| Agent tool calls | ~50+ |
| User steering corrections | 4 |
| Failed pushes | 1 |
| Fix iterations (lint/mypy) | 3 |
| Hook blocks | 1 |
| Subagents spawned | 5 (1 retro, 4 skill builders) |
| Skills dropped after eval | 3 of 4 |

### What the Original Retrospective Got Wrong

1. **"Pivots: None"** - Wrong. Session 1 pivoted from bash to Python. Session 3 pivoted from standalone skills to github suite integration.
2. **"Efficiency: ~50%"** - Generous. Real efficiency closer to 25-30% given wasted session 1 work and session 3 tooling friction.
3. **"Retries: None"** - Wrong. mypy required 2 fix attempts. Push required 2 attempts.
4. **"Blocks: Session ceremony"** - Incomplete. Also blocked by mypy failures, hook guards, and inaccurate first retrospective.

---

## Phase 6: Close the Retrospective

### +/Delta

**+ Keep**
- Comment validity triage before attempting fixes
- Parallel skill building with subagents
- Dropping low-value candidates with evidence

**Delta Change**
- Check ADR constraints before writing code (would have saved session 1)
- Use `dict[str, Any]` for JSON responses (would have saved 1 fix iteration)
- Feed retrospective agents raw conversation data, not sanitized summaries
- Skip skill preamble gates when invoked mid-task

### ROTI

**Score**: 1 (Benefit roughly equals effort)

The stale comment detection script adds real value. But the total cost across 3+ sessions for what should have been a 1-session task was high. Most of the excess cost came from: wasted bash implementation, tooling ceremony, and steering corrections.

### Provenance

- **PR #1589**: https://github.com/rjmurillo/ai-agents/pull/1589
- **PR #1593**: https://github.com/rjmurillo/ai-agents/pull/1593 (this retrospective + stale detection script)
- **Commits**: `971b19d8`, `3cb05ee9`, `668c7139`, `a20813a7`, `8cd3efa1`, `745d5321`, `aa3f90d1`
