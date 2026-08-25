# Retrospective: issue-5192-adr-052-036-reciprocity

## Session Info

- **Date**: 2026-08-25
- **Agent**: Claude Code (Claude Sonnet 5), single session on branch `claude/autoplan-goal-1ewz33`, triggered via `/goal autoplan https://github.com/rjmurillo/ai-agents/issues/5192`.
- **Task Type**: Resolve the one remaining ADR pair in issue #5192 (dangling ADR supersessions): ADR-052 claimed "Supersedes ADR-036" while Proposed; ADR-036 read Accepted with no reciprocal marking. Five of the six flagged pairs in #5192 were already fixed on an unmerged sibling PR (#5209); this session's scope was the ADR-052/ADR-036 pair alone.
- **Outcome**: Owner decision obtained via `AskUserQuestion` (accept ADR-052, supersede ADR-036, the harder of three offered options). Ran a full 6-agent `adr-review` debate (architect, critic, independent-thinker, security, analyst, high-level-advisor) in parallel background agents before making any edit, per the repo's mandatory "any ADR edit fires adr-review" rule. All six converged independently on the same shape without cross-agent visibility. Landed 5 atomic commits: the ADR pair plus a new debate log, the byte-identical AGENTS.md twins, templates/README.md and templates/AGENTS.md, three canonical skill files, and their regenerated Copilot mirrors plus a vendor-portability baseline update. Opened issue #5282 as ADR-052's implementation-tracking successor (#124 had closed on decision-only delivery). PR not yet opened at retrospective-write time; push was blocked by three sequential gates, documented below.

## Phase 1: Insights Generated

### Finding 1: Self-inflicted em/en-dash violation across nine files, caught only by the pre-commit gate

**What happened**: `.claude/rules/universal.md` MUST NOT 5 (no em/en dashes, always-on context for the entire session) and `.claude/rules/voice.md` (same prohibition, restated) were both loaded from the start. Despite that, the first `git commit` attempt on the ADR-052/ADR-036/debate-log group failed at the `staged-dash-policy` lefthook job, which named three files containing em dashes. A repo-wide grep then found the same character in six more files this session had also edited (`.claude/agents/AGENTS.md`, `src/claude/AGENTS.md`, `templates/README.md`, `templates/AGENTS.md`) that had not yet been staged. All nine were written using em dashes as a normal prose connective across roughly 300 lines of new/edited text, entirely unprompted by any source material (none of the six agent review outputs quoted back to the session contained em dashes in a way that would explain contagion).

**Root cause**: The rule was present in context the entire session but was not actively self-checked against generated prose before staging. This is the exact pattern the 2026-08-21 retrospective (`pr-automerge-goal-session-2.md`, Finding 2) already recorded once for a single PR body: "confident generation of PR-body text did not include a self-check pass against a rule the session already knew and had cited elsewhere in the same session." This session repeated it at roughly 9x the file-count scale (nine files versus one), which is evidence the prior retrospective's proposed fix ("grep any PR body text for U+2014/U+2013 before submitting") was not actually adopted as a habit, only recorded once.

**Cost**: One failed commit attempt (immediately visible, not silently absorbed), one `grep` sweep plus a Python find-and-replace pass across nine files, one re-staging and re-commit cycle. Fully recoverable, no CI round burned since the local gate caught it before push.

**Classification**: Same as the 2026-08-21 retrospective's Finding 2: does not cleanly fit an existing `FAILURE-MODES.md` class. Closest in spirit to FM #9 (Confident-Incorrectness Recurrence)'s general shape of "high confidence, unwarranted, first check catches it," but FM #9's specific trigger (claiming parity with an uncited canonical source) does not apply. No new class proposed for a second instance of the same un-adopted fix; instead see Phase 4 Learning 1, which proposes a mechanical rather than a memory-based fix, since the memory-based fix already failed to transfer once.

### Finding 2: Misread a validator's error message as a real defect before checking what it actually measured

**What happened**: After editing and regenerating, `uv run python scripts/validation/check_generated_staleness.py` reported `STALENESS DETECTED: uncommitted regen drift` naming four files, including `src/claude/AGENTS.md`, a file `.claude/rules/claude-agents.md` explicitly documents as hand-maintained and never generated. The initial reading treated this as a possible real defect (a generator regenerating a file that should never be touched by a generator). Reading the validator's own module docstring and its fix suggestion ("regenerate and commit") before acting revealed the check compares the current working tree against `git show HEAD`, so any uncommitted diff under `OWNED_PREFIXES` (which includes the entire broad `src/` prefix) reports as "staleness" regardless of whether the diff came from a generator or a correct hand-edit. The same was true for the `check_skill_md_portability.py` failure, which was a real but expected ratchet-baseline drift (new legitimate references pushed two files' suppressed-ref counts up by one each), fixed with the documented `--update-baseline --allow-marker-grow` flags rather than by second-guessing the new references themselves.

**Root cause**: Read the terse summary line and the file list first, and started forming a hypothesis about a code defect, before reading the validator's own longer docstring (which explicitly documents the compare-against-HEAD behavior and names the exact remedy) or its `--help` output. The information needed to resolve the ambiguity in under a minute was already in the file; the session read it, but only after an initial wrong hypothesis had already started to form.

**Cost**: Near-zero. The correct diagnosis (verified by direct execution, not assumption) took about two tool calls once the docstring was actually read, and the interim wrong hypothesis was never acted on or stated as fact to anyone. Recorded because it is a near-miss, not because it cost anything measurable this time.

**Classification**: No `FAILURE-MODES.md` class matches a near-miss with zero downstream cost. Not elevated to a finding requiring remediation; recorded per the retrospective's evidence requirement since it illustrates a discipline this session got right (verify before hypothesizing further) after a brief wrong start.

### Finding 3: Commit message described only a subset of what the commit actually contained

**What happened**: The first `git commit` invocation, targeting the three ADR/debate-log files, failed at the dash-policy gate (Finding 1) before any commit object was created. After fixing the dashes and re-staging, the session staged two more files (the AGENTS.md twins) intending a *second*, separate commit, then ran `git commit` with the *second* commit's message. Because the first attempt had never actually succeeded, all five files (three ADR-related plus two AGENTS.md) landed in one commit carrying a message titled only "repair stale ADR-036 status citations in AGENTS.md," which undersold the ADR-052/ADR-036 content that made up the bulk of the diff.

**Root cause**: After a failed commit attempt, the session did not re-verify `git log` / `git status` state before proceeding to the next staging step, and assumed (incorrectly) that the first commit had landed as intended. The mismatch was caught by a deliberate post-commit `git log --oneline` and `git show --stat` check run out of habit, not because anything flagged it automatically.

**Cost**: One `git commit --amend` on a not-yet-pushed local commit to correct the message. Zero cost to anyone else since nothing had been pushed; would have been a real, harder-to-fix defect (a misleading permanent commit message) if caught only after push, which per this repo's git safety protocol should never be amended once shared.

**Classification**: No exact `FAILURE-MODES.md` match. Adjacent to FM #4 (False Completion Markers) in spirit (treating a step as done without verifying it), but FM #4's canonical shape is about task-level completion claims, not single git operations. Not proposed as a new class for one instance.

### Finding 4: Two more push-time gates hit sequentially, both environment-class issues already partially documented by a prior session

**What happened**: `git push` failed twice before succeeding. First, `push-ref-policy` reported `push validation requires complete Git history. .git/shallow pins history...`, fixed with `git fetch --unshallow origin`, the exact fix and exact gate the 2026-08-21 retrospective (`2026-08-21-pr-automerge-goal-session-2.md`, Finding 1, Learning 1) already documented for this remote-session container class. Second, after unshallowing, `retrospective-policy` reported `git push requires retrospective evidence for this session`. **Correction (2026-08-25, review): the 2026-08-21 retrospective was in fact committed** (PR #5202, commit `2dd747176`) and is present in this repository; the claim that it "was never committed" conflated two different artifacts. Its own Phase 5 table notes only that one of its learnings was "not yet written to Serena memory," a separate persistence step, not the retrospective file's own git status. What actually kept it from satisfying this session's gate is simpler: `check_retrospective_evidence`'s date check (`_today_retrospective_exists`) only accepts a retrospective dated today or yesterday relative to the current session, and 2026-08-21 was four days stale against this session's 2026-08-25 run. Reading `scripts/validation/git_hook_policy.py:check_retrospective_evidence` directly (rather than guessing at an env-var bypass) showed the actual satisfying conditions: a documentation-only push, a trivial single-file session under 10 minutes old, or a retrospective file dated today under `.agents/retrospective/`. This file is that retrospective.

**Root cause**: The shallow-clone gap is a genuine environment default in this container class (confirmed present again, three sessions after the first documented instance), not a session error. The retrospective-gate encounter was not a missing-precedent gap; a committed, findable example existed. The session simply needed a same-day one and had to read the enforcing script's source directly to learn the exact date-window and bypass conditions rather than finding them stated in a rule file.

**Cost**: One `git fetch --unshallow origin` (network-bound, a few seconds to tens of seconds depending on repo size) and one retrospective file (this one), which is itself the intended remediation, not overhead avoided.

**Classification**: Environment/process gap, not an agent failure mode. Recorded per Learning 2 below since the shallow-clone half is now confirmed present in at least three independent sessions in this container class and still has no automated fix (only a documented manual one). The retrospective-gate half had a committed example present (the 2026-08-21 retrospective), just not one dated recently enough for this session's date-window check; the gap is that the gate's exact date-window and bypass conditions live only in the enforcing script's source, not in a rule file a session could read without opening `git_hook_policy.py` directly.

### Patterns and Shifts

| Pattern | Frequency | Impact | Category |
|---------|-----------|--------|----------|
| Em/en-dash rule present in always-on context is not mechanically self-checked before staging prose | Second documented occurrence (2026-08-21: one file; 2026-08-25: nine files) | Low-medium per incident, always caught locally by `staged-dash-policy` before push in both cases, but the memory-only fix from the first occurrence did not transfer | Self-review gap, recurring |
| Shallow clone blocks the first push in this remote-session container class | Third documented occurrence in this repo's retrospective corpus (session class first noted 2026-08-19, reconfirmed 2026-08-21 and 2026-08-25) | Low: one `git fetch --unshallow origin`, seconds to tens of seconds, but recurs every session in a fresh container and has no automated fix | Environment default, recurring, unfixed |
| Push-time gates (`retrospective-policy`) have no committed worked example in `.agents/retrospective/` for a session to learn the contract from, forcing a source-read of the enforcing script | First observed this session; plausible root cause is that the one prior session that hit an adjacent path never committed its own retrospective | Low-medium: cost about two tool calls to resolve by reading `git_hook_policy.py` directly, but a documented recipe would have made it a lookup instead of an investigation | Documentation gap |

## Phase 2: Diagnosis

### Successes (Tag: helpful)

| Strategy | Evidence | Impact |
|----------|----------|--------|
| Ran a full 6-agent `adr-review` debate in parallel background agents before making any edit, rather than proceeding directly from the owner's `AskUserQuestion` answer | All six reviews returned independently, without cross-agent visibility, and converged on the same fix shape (frontmatter + `implemented` split, a first-screen "still operative" callout, correction of stale facts, repair of status-only citations, debate log, new tracking issue) | Caught a real defect in ADR-052's own text (a misdescription of what ADR-036 actually claimed, unrebutted evidence) that a bare status-flip would have shipped as an "Accepted" record; also correctly scoped what NOT to touch (lefthook.yml, CI workflows, the actual migration code), preventing scope creep into a multi-week implementation |
| Verified every load-bearing fact directly (file counts via `ls | wc -l`, byte-identity of the AGENTS.md twins via `diff`, the `detect_agent_drift.py` exclusion claim via `grep`) before citing any of it in the ADR edits, rather than trusting any single review agent's numbers | Found small discrepancies between different agents' reported counts (21/23 vs 31/32/33 depending on which agent measured) and used the session's own fresh measurement instead of picking one agent's figure | Matches `.claude/rules/canonical-source-mirror.md`'s binding requirement to verify behavioral/factual claims before citing them, and avoided propagating a stale or agent-specific miscount into a governance record |
| Regenerated Copilot mirrors via the actual generator (`build/scripts/generate_skills.py`) rather than hand-editing `src/copilot-cli/skills/`, then verified the diff matched expectations before committing | `git diff --stat src/copilot-cli/skills/` showed exactly the three expected files with a minimal, correct diff | Complied with `.claude/rules/knowledge-persistence.md` MUST NOT 2 and avoided the exact class of incident `.claude/rules/generated-artifacts.md` exists to prevent (a hand-edited generated file silently reverted or drifting in CI) |
| Fixed two small pre-existing defects found on the exact lines being edited (a broken relative link in `templates/AGENTS.md`, a nonexistent `Generate-Agents.ps1` self-contradiction in ADR-036) inline rather than expanding scope to hunt for more | Both fixes were one-line, on lines already open for the primary edit, and noted explicitly in the commit message and in-file comment | Matches `voice.md`'s "Ownership: See Something, Say Something" (inline for small, on-path fixes) without boiling the ocean into an unrelated cleanup pass |

### Failures (Tag: harmful)

| Strategy | Error Type | Root Cause | Prevention |
|----------|------------|------------|------------|
| Wrote em/en dashes across nine files despite the prohibition being in always-on context all session | Self-inflicted rule violation, recurrence of a previously-documented pattern | Generated prose was not mechanically checked against a known rule before staging (see Finding 1) | See Phase 4 Learning 1: a mechanical self-check, not a memory entry, since the memory-based fix from 2026-08-21 did not transfer |
| Assumed the first `git commit` attempt had succeeded before staging the next group and committing again | Unverified assumption about git state after a failed operation | Did not re-check `git status`/`git log` immediately after a failed commit before proceeding | Always run `git log --oneline -1` (or equivalent) immediately after any commit attempt that could have failed, before staging further changes |

## Phase 3: Decisions

### Action Classification

#### Keep (TAG as helpful)

| Finding | Skill/Memory ID | Note |
|---|---|---|
| Run the full multi-agent `adr-review` debate before any ADR edit, even when the owner's decision is already made | Existing repo rule (CLAUDE.md skill routing, `.claude/skills/adr-review/SKILL.md`) | Confirmed working as designed this session; the debate changed the shape of the fix substantially versus a naive bare status flip |
| Verify every factual claim by direct execution before citing it, especially when multiple independent sources (six review agents) report slightly different numbers | `.claude/rules/canonical-source-mirror.md` | Confirmed working; would flag as a new pattern to persist if this repo did not already have a binding rule for it |

#### Add (New skill/memory)

- A mechanical pre-stage self-check for prohibited em/en dashes across all files touched in the current change, not reliance on the rule being "in context." See Phase 4 Learning 1.
- The shallow-clone-on-first-push trap in this remote-session container class is now confirmed on its third independent occurrence (2026-08-19, 2026-08-21, 2026-08-25) with no automated fix, only a manual `git fetch --unshallow origin`. Worth escalating from a retrospective-only note to an actual Serena memory entry or a `SessionStart` hook check, since the memory-entry path from the 2026-08-21 retrospective was explicitly left undone ("not yet written to Serena memory") and the gap recurred.

#### Modify (UPDATE existing)

- The 2026-08-21 retrospective's Learning 1 ("origin/HEAD-unset and shallow-clone traps... proposed skill: `pr-automerge/container-clone-defaults`") was proposed but, per that retrospective's own Phase 5 table, never persisted to Serena memory. This session is direct evidence the gap it described recurred exactly as predicted. Recommend the next session that touches this actually writes the memory entry rather than re-proposing it a third time.

## Phase 4: Extracted Learnings

### Learning 1

- **Statement**: Before staging any commit whose diff includes newly-authored or newly-edited prose, run a mechanical check for prohibited em/en dashes (`grep -rn $'\xe2\x80\x94\|\xe2\x80\x93'` or equivalent) across every file in the diff, rather than relying on the rule being present in always-on context. The always-on-context approach has now failed to prevent this specific violation twice in two consecutive documented sessions (2026-08-21: one file; 2026-08-25: nine files), which is evidence that "the rule is loaded" is not sufficient to guarantee "the rule is applied" for high-volume prose generation.
- **Atomicity Score**: ~85% (single, narrow, mechanically checkable rule; the fix is a grep command, not a judgment call)
- **Evidence**: This session's `staged-dash-policy` lefthook job failed on the first commit attempt, naming three files; a follow-up repo-wide grep found six more files with the same violation that had not yet been staged. The 2026-08-21 retrospective independently documents the same class of failure on a PR body, also caught only by a downstream gate (`scripts/validation/pr_description.py:validate_no_dashes` via CI) rather than by self-check.
- **Skill Operation**: ADD
- **Target Skill ID**: `voice/pre-stage-dash-check` (proposed)

### Learning 2

- **Statement**: A fresh clone in this remote-session container class is shallow by default and blocks the first `git push` with `push-ref-policy: push validation requires complete Git history`, requiring `git fetch --unshallow origin` before the push can proceed. This is now confirmed on three independent sessions (2026-08-19, 2026-08-21, 2026-08-25) with no automated remediation; each session has had to rediscover or recall the fix rather than have it applied automatically or documented in a place the session reliably reads before the first push.
- **Atomicity Score**: ~80% (single environment fact, single fix command, but "reliably reads before first push" implies either a SessionStart hook or a memory entry that is actually searched, neither of which currently exists)
- **Evidence**: This session's `git push` failed with `.git/shallow pins history at 2c85d2547c053780c0ef83d0f8a6ef0be7916b7c`; `git fetch --unshallow origin` resolved it, matching the exact fix and exact error shape (differing only in the pinned commit SHA) the 2026-08-21 retrospective recorded for the same gate.
- **Skill Operation**: ADD (this time, actually persist to Serena memory or a `SessionStart` hook, since the 2026-08-21 retrospective's identical proposal was not persisted and the gap recurred)
- **Target Skill ID**: `pr-automerge/container-clone-defaults` (re-proposed; see 2026-08-21 retrospective for the original proposal that was not carried through)

## Phase 5: Persist and Close

### Memory Persistence

| Learning | Existing Match | Result |
|---|---|---|
| Learning 1 (pre-stage dash check) | 2026-08-21 retrospective documents the same class once, not persisted to Serena memory | Recorded here; owner is issue #5288 (opened this session specifically because the prior retrospective's identical proposal was never persisted) |
| Learning 2 (container clone defaults) | 2026-08-21 retrospective proposed the identical memory entry, explicitly left unpersisted | Recorded here for the second time; owner is issue #5288, same as Learning 1 |

### Delta Triage

| Delta Item | Category | Priority | Destination |
|---|---|---|---|
| Two learnings proposed identically in a prior retrospective and not persisted, now recurred | Process | P2 | Issue #5288 (opened this session): persist both, and decide whether the shallow-clone half is better fixed as a `SessionStart` hook (a deterministic environment fact, not tacit knowledge) than as a memory entry |
| ADR-052's actual Migration Plan (Phases 1-3) needs re-scoping against six agent surfaces before implementation starts | Process | P2 | Tracked at issue #5282, opened this session; explicitly out of scope for this session's own work |

### ROTI Assessment

**Score**: 3 (Benefit clearly exceeded effort)

**Benefits Received**: Resolved the one remaining unfixed pair from issue #5192 with a governance-record fix that a 6-agent debate substantially improved over a naive status flip, catching a real factual defect in ADR-052's own Prior Art section and preventing the fix from recreating the exact dangling-trust bug it was meant to close (in the opposite direction: superseded-but-still-live). Correctly scoped the change to reciprocity bookkeeping and explicitly declined to attempt the actual multi-week migration inline, opening a properly-scoped tracking issue instead. Caught and fixed a self-inflicted rule violation before it reached CI, though the violation itself (nine files) was larger than the single-file instance the same repo already has on record.

**Verdict**: Continue

## Failure Mode Classification

**Finding 1** (recurring em/en-dash self-violation): **Correction (2026-08-25, review): does not fit FM #9.** `.agents/governance/FAILURE-MODES.md:288` defines FM #9's shape as "partial signal, premature conclusion, confident delivery, multi-round correction," and its Detection section names a PR correcting the same mistake across three or more commits. This finding's actual shape is a single-shot catch: the em-dash violation was caught and fixed at the first pre-commit gate, with no multi-round correction. It also is not true that the 2026-08-21 retrospective "assigned" FM #9 to its own instance of this pattern; that retrospective's own Finding 2 explicitly says the event "does not cleanly fit an existing `FAILURE-MODES.md` class" and calls FM #9 only the closest analogy in general shape, the same hedge this retrospective's Finding 1 (above, this same file) independently reached before this addendum over-firmed it. Neither existing class in `FAILURE-MODES.md` cleanly covers "high-confidence prose generation that violates a rule already loaded in context, caught on the first downstream gate before any multi-round correction is needed." Per `.claude/rules/retros.md` MUST 2, a class that does not fit needs a new class proposed in a linked ADR, not a forced fit to the nearest existing one; that ADR is not proposed here (two retrospectives now show the pattern, which is the evidence such a proposal would need, but authoring it is out of scope for this correction).

**Findings 2 and 3** (misread-then-self-corrected validator output; commit-message/content mismatch) are process near-misses, not failure-mode instances: both were caught and corrected within the same session before any external consequence (no CI round burned, nothing pushed in the wrong state), which is the distinguishing property `FAILURE-MODES.md`'s classes describe failures reaching an external gate or reviewer, not internal self-corrections. Recorded as evidence per this file's completeness requirement, not classified.

**Finding 4** (shallow-clone and retrospective-gate friction on push) is an environment/process gap external to agent reasoning, not an agent failure mode; it is the subject of Learning 2 and issue #5288 above rather than a `FAILURE-MODES.md` classification.
