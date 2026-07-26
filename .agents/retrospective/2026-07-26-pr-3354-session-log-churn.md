# Retrospective: PR #3354, session-log churn against the commit gate

**Branch**: `fix/3342-harness-reference-size`
**Issue**: [#3342](https://github.com/rjmurillo/ai-agents/issues/3342)
**PR**: [#3354](https://github.com/rjmurillo/ai-agents/pull/3354)
**Status**: Final review autofix
**Outcome**: PARTIAL. Work delivered; process overhead triggered the needs-split label.

**Snapshot**: the commit trace and counts below are as of commit 15. The PR
later reached 22 commits and tripped the hard limit, not just the warn
threshold ([run 30190397373](https://github.com/rjmurillo/ai-agents/actions/runs/30190397373)).
The additional 7 are review-iteration fixes across three further rounds, which
strengthens Finding 1 rather than changing it: the share of commits carrying no
content change went up, not down.

---

## Failure Mode Classification

**Primary Failure Mode**: FM-9 (Confident-Incorrectness Recurrence)

The Cursor autofix bot applied a monotonic counter (3344) as `session.number` while writing a filename built from 3342. The bot delivered both with full confidence; the validator accepted the pair because the schema checks type (integer) and nothing checks the number against the filename that encodes it. The mismatch required five corrective commits across two merge cycles to fix.

**Secondary Pattern**: The validator's silent acceptance of 3344 is related to FM-10 (Silent Defaults and Guard-Clause Suppression) - the validation returned success when a semantic constraint was violated because that constraint was not encoded in the schema.

**Reference**: [`.agents/governance/FAILURE-MODES.md`](https://github.com/rjmurillo/ai-agents/blob/main/.agents/governance/FAILURE-MODES.md)

---

## Phase 0: Data Gathering

### Execution Trace

| Order | SHA | Type | Author | Subject |
|-------|-----|------|--------|---------|
| 1 | [`f3f7dbe0`](https://github.com/rjmurillo/ai-agents/commit/f3f7dbe0) | session | Cursor Agent | fix(session): populate endingCommit with last code-deliverable SHA |
| 2 | [`9f69ff63`](https://github.com/rjmurillo/ai-agents/commit/9f69ff63) | session | Cursor Agent | fix(sessions): correct duplicate session number and remove duplicate assertion |
| 3 | [`b34a7f68`](https://github.com/rjmurillo/ai-agents/commit/b34a7f68) | session | Cursor Agent | fix(sessions): align session log filename and id with session number |
| 4 | [`b09c57cf`](https://github.com/rjmurillo/ai-agents/commit/b09c57cf) | core | rjmurillo + Copilot | docs(harness): delete the vendor contract SKILL.md duplicated from its sidecar |
| 5 | [`da5401a1`](https://github.com/rjmurillo/ai-agents/commit/da5401a1) | core | rjmurillo + Copilot | test(harness): pin each contract fact against the file that owns it |
| 6 | [`34e2d9cb`](https://github.com/rjmurillo/ai-agents/commit/34e2d9cb) | session | rjmurillo + Copilot | chore(session): record the harness reference deduplication |
| 7 | [`d92d4004`](https://github.com/rjmurillo/ai-agents/commit/d92d4004) | merge | rjmurillo | Merge origin/main into fix/3342-harness-reference-size |
| 8 | [`f65741cb`](https://github.com/rjmurillo/ai-agents/commit/f65741cb) | merge | rjmurillo | Merge bot corrections into fix/3342-harness-reference-size |
| 9 | [`726796d1`](https://github.com/rjmurillo/ai-agents/commit/726796d1) | session | rjmurillo + Copilot | chore(session): correct the commit accounting after the merges |
| 10 | [`e876925d`](https://github.com/rjmurillo/ai-agents/commit/e876925d) | merge | rjmurillo | Merge the bot rename before correcting the session number |
| 11 | [`3e998763`](https://github.com/rjmurillo/ai-agents/commit/3e998763) | session | rjmurillo + Copilot | chore(session): restore the issue-derived session number |
| 12 | [`618d8e1a`](https://github.com/rjmurillo/ai-agents/commit/618d8e1a) | review-fix | rjmurillo + Copilot | fix(skills): correct exit-2 semantics and tighten contract pins |
| 13 | [`8a9ee9fa`](https://github.com/rjmurillo/ai-agents/commit/8a9ee9fa) | merge | rjmurillo | Merge remote-tracking branch 'origin/main' into fix/3342-harness-reference-size |
| 14 | [`006a8876`](https://github.com/rjmurillo/ai-agents/commit/006a8876) | review-fix | rjmurillo | docs(agent-harness-reference): stop claiming the sidecar holds every vendor fact |
| 15 | [`c4663154`](https://github.com/rjmurillo/ai-agents/commit/c4663154) | session | Cursor Agent | fix(session): align endingCommit with changesCommitted evidence |

### Commit Category Summary

| Category | Count | Share |
|----------|-------|-------|
| Session/bookkeeping | 7 | 47% |
| Merge commits | 4 | 27% |
| Review iteration fixes | 2 | 13% |
| Core work | 2 | 13% |

**Total**: 15 commits. Threshold: warn at 15 (ADR-008).

### Outcome Classification

**Glad (Success)**

- Core change was clean and minimal: 2 commits removed 261 lines of duplicate vendor content.
- SKILL.md dropped from 495 to 314 lines; the 500-line budget gate now passes.
- 30-fact sweep confirmed zero content loss.
- Negative controls all turned red when the removed text was absent.

**Sad (Suboptimal)**

- 11 of 15 commits carry no content change to source code or documentation.
- The bot injected a wrong session number (3344) that required 5 corrective commits across two merge cycles to fix.
- Two test pins did not hold the facts they claimed, requiring a second review cycle.

**Mad (Blocked)**

- None. The PR was never blocked; the overhead inflated the commit count without stalling delivery.

---

## Phase 1: Generate Insights

### Five Whys: Why did PR #3354 reach 15 commits?

**Problem**: PR accumulated 15 commits against a warn threshold of 15.

**Q1**: Why are there 15 commits?
**A1**: 7 session/bookkeeping commits and 4 merge commits account for 11 of 15.

**Q2**: Why did the session bookkeeping produce 7 commits?
**A2**: The Cursor autofix bot seeded `session.number` as 3344 (an incremented counter) while the log filename encoded 3342. Correcting the bot required 3 more commits from the bot plus 2 merge commits to absorb them, plus 2 additional cleanup commits to restore correct values.

**Q3**: Why did the bot choose 3344?
**A3**: The bot applies a monotonic counter to avoid collisions. It read 3343 as a collision with an existing session and incremented.

The first version of this retro said the project keys `session.number` off the issue number in the branch name. That is wrong, and review caught it. Counterexample: [`2026-07-26-session-3347-resolve-remaining-3347-review-threads.json`](https://github.com/rjmurillo/ai-agents/blob/main/.agents/sessions/2026-07-26-session-3347-resolve-remaining-3347-review-threads.json) carries `session.number: 3347` on branch `fix/3346-session-schema-enforcement`.

The invariant that does hold is filename to `session.number`: the session-init generator derives the log filename from the number, and tooling reads it back out. Measured across all 1153 committed logs, 3 violate it ([`2026-01-18-session-09-...`](https://github.com/rjmurillo/ai-agents/blob/main/.agents/sessions/2026-01-18-session-09-add-memory-naming-convention-section.json) at 7, [`2026-02-11-session-1-...`](https://github.com/rjmurillo/ai-agents/blob/main/.agents/sessions/2026-02-11-session-1198-pr-review-1146-security-fixes.json) at 1198, and [`2026-04-20-session-1711-...`](https://github.com/rjmurillo/ai-agents/blob/main/.agents/sessions/2026-04-20-session-1711-pr-description-backticks.json) at 1). Nothing in the schema or validator enforces it, which is why the bot's value passed.

**Q4**: Why does nothing enforce the filename convention?
**A4**: The session schema declares `session.number` as an integer with no constraint expression linking it to anything. The validator checks range and type, not the filename relationship. Tracked as [#3355](https://github.com/rjmurillo/ai-agents/issues/3355).

**Root Cause A**: The `session.number` convention is undocumented in the schema and unvalidated at seed time. Bots applying a reasonable default (monotonic counter) desynchronize the number from the filename silently.

**Q5 (merge commits)**: Why were there 4 merge commits?
**A5**: Two were required to bring the bot's corrections onto the branch. Two were required to keep the branch current with main. The causal-graph.json file conflicted on both main merges (noted in both merge commit messages), requiring manual resolution each time.

**Root Cause B**: causal-graph.json is a high-conflict file. Every branch that touches memory or sessions hits a merge conflict in it. Manual resolution creates merge commits even for short-lived branches.

### Fishbone Analysis

**Problem**: PR exceeded the commit warn threshold at 15.

**Category: Session/Schema**
- `session.number` has no linkage constraint to the filename that encodes it.
- Bot applies a monotonic counter; the filename it writes is derived from a different number.
- Validator does not catch the mismatch.

**Category: Tooling/Bot Behavior**
- Autofix bot detected a (false) collision and incremented the number.
- Bot corrections required two additional merge commits to absorb.
- The bot's file rename for the session log had to be undone manually.

**Category: Merge Hotspot**
- causal-graph.json conflicts on every sync with main.
- Two conflict resolutions created two merge commits.
- No merge strategy or regeneration script reduces this overhead.

**Category: Review Correctness**
- exit-2 semantics in SKILL.md asserted a global deny rule that does not exist in the sidecar.
- Two test pins matched unintended text, leaving them green when the target fact was absent.
- A self-check against the sidecar before pushing would have caught both.

**Cross-Category Pattern**: The causal-graph.json conflict appears in both the bot-correction merge cycle and the main-sync merge cycle. It is the single file that multiplied the merge commit count.

---

## Phase 2: Diagnosis

### Finding 1 [CRITICAL]: Session bookkeeping dominates the commit count

7 of 15 commits (47%) carry zero content change to source code or tested documentation. The Cursor bot's session number error generated a self-reinforcing correction cascade:

1. Bot seeds wrong number (f3f7dbe0, 9f69ff63, b34a7f68).
2. First manual merge absorbs bot corrections (f65741cb at T+2:35).
3. Manual cleanup after merge (726796d1 at T+2:36).
4. Bot rename undone with a second merge (e876925d at T+2:40).
5. Issue-number value restored (3e998763 at T+2:41).
6. Session accounting corrected again after all merges (34e2d9cb).
7. Final Cursor pass to align endingCommit (c4663154 at end).

Each step was correct in isolation. Together they consumed 7 commits that add no value to the PR's stated goal.

### Finding 2 [WARNING]: Merge commit accumulation from causal-graph.json conflicts

Both syncs with main (d92d4004, 8a9ee9fa) required manual conflict resolution in causal-graph.json. The bot correction cycle added two more merge commits (f65741cb, e876925d). The branch was open for less than 24 hours but collected 4 merge commits.

### Finding 3 [WARNING]: Review found a content correctness bug

618d8e1a fixed a factual error: the SKILL.md claimed exit 2 denies globally, but the sidecar's exit-code table states it warns and continues by default, denying only for PreToolUse and PermissionRequest. This was a correctness bug, not a style nit. A quick cross-read of the sidecar before the initial push would have caught it.

### Finding 4 [WARNING]: Test pins matched unintended residual text

Two pins in test_reference_versions_matcher_and_timeout_evidence passed when their target facts were absent, because the matching strings appeared elsewhere in the document. 618d8e1a tightened both pins to full sentences via _normalized_text. This is a test design issue: substring matching without normalization is ambiguous in multi-occurrence documents.

### Could this work have been split safely?

No. The two core commits (b09c57cf + da5401a1) are tightly coupled. Deleting the duplicate section without updating the test suite leaves the suite broken. The review iteration commits (618d8e1a + 006a8876) are corrections to the core commits and belong in the same PR.

The needs-split label reflects the commit count, not the scope. The scope is a single coherent change: remove duplicate content and fix the tests that enforced the wrong file location. Splitting on any logical boundary would produce a PR with broken tests or broken content.

**Verdict**: This PR should not have been split. The needs-split label is a process signal generated by overhead commits, not by scope creep.

---

## Phase 3: Decisions

### Action Classification

| Finding | Category | Proposed Action |
|---------|----------|-----------------|
| `session.number` convention unvalidated | ADD | Validate `session.number` against the number in the log filename, the invariant the generator relies on ([#3355](https://github.com/rjmurillo/ai-agents/issues/3355)) |
| Bot applies a numbering convention the filename does not follow | ADD | Document the invariant in session schema comments; add it to the session-init skill checklist |
| causal-graph.json conflict on every sync | ADD | Investigate merge strategy or regeneration script to reduce manual conflict resolution |
| Sidecar cross-read not performed pre-push | ADD | Add sidecar self-check to the pre-push skill checklist for harness reference work |
| Test pins using substring matching | ADD | Prefer full-sentence pinning via _normalized_text; add this to TESTING-RIGOR.md |

### SMART Validation

**Proposed skill: session-number-must-match-filename**
- Specific: one rule, one field, one source of truth.
- Measurable: the validator can compare `session.number` to the integer parsed from the log filename.
- Attainable: the filename is available wherever the log is.
- Relevant: applies on every PR that includes a session log.
- Timely: trigger at session-init and at pre-push validation.
- Atomicity: 91%

**Proposed skill: harness-sidecar-cross-check-before-push**
- Specific: check SKILL.md claims against the sidecar before pushing harness reference changes.
- Measurable: the sidecar's exit-code table is machine-readable; a diff catches mismatches.
- Attainable: existing test suite already asserts these facts; run them locally first.
- Relevant: applies to any commit touching agent-harness-reference content.
- Timely: trigger before each push, not just before PR creation.
- Atomicity: 88%

---

## Phase 4: Learning Extraction

### Learning 1

**Statement**: `session.number` must equal the number encoded in the session log filename.
**Atomicity Score**: 91%
**Evidence**: Commits [`9f69ff63`](https://github.com/rjmurillo/ai-agents/commit/9f69ff63) and [`3e998763`](https://github.com/rjmurillo/ai-agents/commit/3e998763) corrected the bot's 3344 to 3342 to match the filename. The causal chain required 5 commits and 2 merge cycles.
**Skill Operation**: ADD
**Target Domain**: session-protocol

### Learning 2

**Statement**: Pin content assertions to full sentences via _normalized_text, not substrings, in multi-occurrence documents.
**Atomicity Score**: 88%
**Evidence**: 618d8e1a found that "1.0.57 in text" and "| exit 2 | deny |" both matched unintended residual text. The matcher-bug sentence and the PreToolUse failure table each satisfied the substring without the target fact being present.
**Skill Operation**: ADD
**Target Domain**: testing-rigor

### Learning 3

**Statement**: For harness reference changes, run the contract-knowledge test suite locally before pushing; do not wait for review to surface sidecar contradictions.
**Atomicity Score**: 85%
**Evidence**: 618d8e1a corrected a factual error (exit-2 global deny claim) that the sidecar contradicts. The existing test suite covers this fact. Running the tests before the initial push would have caught it.
**Skill Operation**: ADD
**Target Domain**: harness-reference

### Learning 4

**Statement**: Session bookkeeping commits must not inflate the PR commit count; squash or amend them into their parent code commit before opening a PR.
**Atomicity Score**: 82%
**Evidence**: 7 of 15 commits in this PR carry only session log changes. The 15-commit threshold was met entirely by session and merge overhead, not by scope.
**Skill Operation**: ADD
**Target Domain**: session-protocol

---

## Phase 5: Process Patterns

### Pattern: Bot convention mismatch with project convention

The Cursor autofix bot applies a monotonic session counter, then writes a filename derived from a different number. The two agree when the counter happens to land on the same value. When they diverge (3342 against 3344 here), the log's number and its filename disagree and validation still passes.

**Frequency**: Unknown. This is the first documented instance.
**Detection**: A validator comparing `session.number` to the integer in the log filename would catch it at commit time. See [#3355](https://github.com/rjmurillo/ai-agents/issues/3355).
**Prevention**: Document the convention in the session schema. Enforce it in pre_pr.py.

### Pattern: causal-graph.json as merge hotspot

Every session-aware PR touches causal-graph.json. When two branches are open at the same time, both generate causal graph entries, and merging either one into the other produces a conflict. This PR had two conflict-resolving merges within 6 minutes (d92d4004 at T+2:31, f65741cb at T+2:35). A merge driver or append-only format for this file would eliminate the conflict class entirely.

**Frequency**: Observed across multiple PRs (also noted in the ADR-057 retro from 2026-07-25).
**Detection**: Any branch touching .agents/memory will produce a causal-graph conflict on sync with main if another PR merged during the branch's lifetime.
**Prevention**: Investigate an append-only or JSON-merge-driver strategy for causal-graph.json.

### Pattern: Needs-split label triggered by overhead, not scope

PR #3354's 15 commits break down as 2 core + 2 review fixes + 7 session + 4 merge. The substantive work is 4 commits. The threshold signal is accurate (the number is 15) but the diagnosis is wrong (the cause is not scope creep). A label that distinguishes "needs-split: scope" from "needs-split: overhead" would give clearer guidance.

---

## Phase 6: Close

### +/Delta

**+ Keep**
- Session log infrastructure is complete and auditable; when the convention is correct, the record is reliable.
- The core deletion was thorough: 30-fact sweep, 6 negative controls, zero gaps found.
- Commit messages carry enough detail to reconstruct the full causal chain.

**Delta Change**
- Validate `session.number` against the log filename at seed time, so a bot's counter cannot desynchronize the pair ([#3355](https://github.com/rjmurillo/ai-agents/issues/3355)).
- Add causal-graph.json to a list of files that need a merge strategy review.
- Amend or squash session log commits before PR creation to avoid inflating the commit count.
- Run the skill's own test suite locally before the first push when touching harness reference content.

### ROTI

**Score**: 2 (Benefit exceeds effort)

**Benefits received**:
- Identified the session.number validation gap with a concrete reproduction path.
- Named causal-graph.json as a recurring merge hotspot that has been observed in at least two consecutive PRs.
- Confirmed the needs-split label is measuring overhead, not scope, for this class of PR.
- Extracted 4 actionable skills above the 82% atomicity floor.

**Time invested**: One analysis pass over the 15-commit trace and the PR diff.

**Verdict**: Continue. The pattern analysis is more valuable than the individual commit diagnosis.

---

## Appendix: File Change Inventory

| File | Category | Net Change |
|------|----------|------------|
| .claude/skills/agent-harness-reference/SKILL.md | core | -181 lines (duplicate section removed) |
| src/copilot-cli/skills/agent-harness-reference/SKILL.md | core (mirror) | -181 lines |
| .claude/skills/agent-harness-reference/references/official-hook-contracts.md | core | +5 lines (orphaned vendor fact moved here, plus the dual Stop citation) |
| src/copilot-cli/skills/agent-harness-reference/references/official-hook-contracts.md | core (mirror) | +5 lines |
| tests/build_scripts/test_hook_contract_knowledge.py | tests | repointed assertions to owning files |
| .claude/.claude-plugin/plugin.json | manifest | version bump 0.6.106 to 0.6.113 |
| src/copilot-cli/.claude-plugin/plugin.json | manifest (mirror) | version bump 0.6.106 to 0.6.113 |
| .agents/memory/causality/causal-graph.json | bookkeeping | merge conflict resolution |

GitHub reported 10 changed files before this autofix. The final review adds this
analysis and one session log. The cumulative history also contains
added-then-deleted session artifacts that are absent from the final tree.
