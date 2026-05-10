# Retrospective: PR #1989 (REQ-009 Implementation, Recursive Failure)

## Session Info

- **Date**: 2026-05-10
- **PR**: #1989 (REQ-009, draft)
- **Predecessor PR**: #1965 (merged, 58 commits, 120 bot threads)
- **Goal**: Implement REQ-009 mitigations (M1 stable-zero wrapper, M4 rework warning, M5 bot-cascade pre-push) to fix failure modes documented in PR #1965 retro.
- **Outcome**: 21 commits, 46 bot threads, still draft. All three predecessor failure modes reproduced.
- **Task type**: Defect mitigation (fix the fix)

---

## Failure Mode Classification

Per `.agents/governance/FAILURE-MODES.md` and FM-NEW classes introduced in the PR #1965 retro.

| # | Failure Mode | Instance in PR #1989 | Commit Cost |
|---|---|---|---|
| FM-1 | Context Reading Failure | M1 inherited a misdiagnosed root cause from retro RCA-1; `get_unresolved_review_threads.py` already paginates correctly | ~5 commits |
| FM-1 | Context Reading Failure | Em-dashes in `req-009-retro-fixes-pr-1965.md` authored by the same agent that maintains the prohibition rule | 1 commit |
| FM-NEW-A | Additive Bot Reviewer Cascade | 31 threads on Iteration 1 commits, 10 new threads on cb1bdf19 alone from 5 independent bots | ~12 commits |
| FM-NEW-B | Non-Atomic Compound Change | M1/M4/M5 each had multi-site token/contract changes spread across commits | ~6 commits |
| FM-4 | False Completion Marker | `--diff-filter=R` caused M4 to return 0 files reworked; false absence of signal | 2 commits |

The PR that was built to prevent FM-1, FM-NEW-A, and FM-NEW-B reproduced all three. This is the defining fact of this retrospective.

---

## Phase 0: Data Gathering

### Commit and Thread Counts

| Metric | PR #1965 | PR #1989 |
|---|---|---|
| Commits | 58 | 21 (draft) |
| Bot threads | 120 | 46 (draft) |
| Review iterations | 11 | 2 (Iteration 1: 31 threads; Iteration 2: 10 new on cb1bdf19) |
| Bot reviewers firing | 4 | 5 (Copilot, CodeRabbit, Cursor, Devin, Gemini) |

Thread density (threads per commit): PR #1965 = 2.1; PR #1989 = 2.2. The rate is unchanged.

### P0 Bugs Introduced (Implementation Bugs)

| ID | Location | Bug | Caught by |
|---|---|---|---|
| B1 | `rework_warning.py` | `--diff-filter=R` restricted git log to renamed files only; ordinary edits invisible | Cursor, Copilot, CodeRabbit, Devin (4/5 bots converged) |
| B2 | CLI flag | `--strict-pagination action="store_true" default=True`: flag impossible to disable | Copilot, CodeRabbit |
| B3 | `wait_for_unresolved_zero.py main()` | Exit codes flattened to 1; ADR-035 contract violated despite being cited in docstring | Copilot, CodeRabbit |
| B4 | `complete_session_log.py` import | `_load_rework_module()` at module scope: sibling fault crashes unrelated critical path | CodeRabbit |
| B5 | `_collapse_rename` | Brace parser regex too restrictive; `path/{old => new}/filename` form not handled | Gemini |
| B6 | `_invoke_underlying` | Unguarded `subprocess.run`: TimeoutExpired, FileNotFoundError, OSError crash polling loop | Gemini, CodeRabbit |

### P0 Bugs Introduced (Fix-Iteration Bugs, commit cb1bdf19)

| ID | Location | Bug | Caught by |
|---|---|---|---|
| B7 | CI coverage gate | `--cov=wait_for_unresolved_zero` references module under `.claude/skills/**`; cannot be imported by name in CI | Copilot (at push) |
| B8 | Recent-bot-review path | `gh api ... \|\| true` swallows auth/network failures; "no reviews" is a false pass | Copilot |
| B9 | `pr-review-observations.md` Session 15 | Memory entry says `get_unresolved_review_threads.py` "silently undercounts"; M1 depends on it. Contradiction authored same day | Copilot |
| B10 | `req-009-retro-fixes-pr-1965.md` | Em-dashes present; explicit project rule prohibits em/en-dashes | Copilot |

### Real-World Test Results

M1 (stable-zero wrapper) tested against PR #1989 as live test bed:

- Returns 10 unresolved threads. `fetched_pages_complete=true`. Exit codes propagate correctly.
- Concept is valid. Implementation bugs (B1-B6) were mechanical errors, not design errors.

M4 (rework warning) tested against PR #1989:

- Returns 0 files reworked. Max file edits on this branch = 4. Threshold = 6.
- M4 cannot fire on ordinary work at this threshold. The detector has low signal value for real PRs.

---

## Phase 1: Five Whys on the Recursive Pattern

The highest-order question: why did a PR built to fix failure modes reproduce those same failure modes?

**Problem**: PR #1989 triggered FM-1, FM-NEW-A, and FM-NEW-B while implementing their mitigations.

**Q1**: Why did PR #1989 reproduce the failure modes it was mitigating?
**A1**: The mitigations were implemented using the same methodology that caused the original failures.

**Q2**: Why was the same methodology used?
**A2**: The mitigations addressed tooling gaps (missing pagination, missing pre-push hook) but did not address the implementation behavior (read before write, batch before push, enumerate co-change sites upfront).

**Q3**: Why did the mitigations target tooling rather than behavior?
**A3**: The PR #1965 retro framed failure modes as capability gaps (no paginating tool, no pre-push check) rather than as discipline gaps (agent does not read before acting).

**Q4**: Why were the failure modes framed as capability gaps?
**A4**: Tools are easier to specify than behavioral constraints. A new script has a clear acceptance test. A behavioral change in how an agent reads context does not.

**Q5**: Why are behavioral constraints harder to enforce?
**A5**: Tooling enforcement runs in CI. Behavioral enforcement requires either a pre-task checklist that the agent executes before writing any code, or a spec gate that blocks the first commit until the agent demonstrates it read the relevant source.

**Root cause**: the PR #1965 retro correctly named the failure modes but prescribed tooling mitigations for behavioral failures. New tools executed with the same behavior produce the same failure modes. The recursive reproduction was predictable from the retro's own RCA if applied one level deeper.

---

## Phase 2: Diagnosis

### Is REQ-009 the Wrong Abstraction?

No. The three mitigations (stable-zero wrapper, rework signal, bot-cascade pre-push) are valid. M1 works in end-to-end test. The abstractions are correct. The implementation methodology failed, not the requirements.

The specific diagnosis:

- **M4 calibration**: threshold-6 is wrong for repos with ordinary PRs (max 4 file edits here). The metric needs a relative measure (edits relative to PR size) or a lower threshold, or both. This is a requirement gap, not a methodology gap.
- **M5 self-application**: M5 (bot-cascade pre-push hook) should have been the first thing pushed and run on every subsequent commit for PR #1989. Instead it was shipped as an output artifact, never applied to its own PR.
- **B9 self-contradiction**: a memory entry and the code contradicted each other within the same day. The agent wrote both without reading either against the other.

### Critical Failures (P0)

| Finding | Evidence | Root Cause |
|---|---|---|
| `--diff-filter=R` flag semantics wrong | M4 returns 0 for all ordinary edits | Read from memory ("looked correct") not from git man page; FM-1 |
| ADR-035 violated in docstring-citing file | B3: exit codes flattened to 1 | Cited contract, did not verify implementation against it |
| Fix-iteration bugs on cb1bdf19 | 10 new threads immediately on push | Batching rule not applied; FM-NEW-A; FM-NEW-B |
| Em-dashes in plan file | B10 | FM-1: agent maintains rule, did not apply rule to own output |

---

## Phase 3: Three Concrete Process Changes

These are distinct from the three interventions in the PR #1965 retro (pagination contract test, canonical-mirror glob widening, co-change checklists).

### Process Change 1: Require Self-Application Before Shipping a Guard

**Problem**: M5 (bot-cascade pre-push hook) was never applied to PR #1989 during development. The hook that detects open threads before pushing was not running on the branch that would have most benefited from it.

**Rule**: any PR that ships a pre-push or pre-commit guard MUST demonstrate that guard running against its own branch in the PR description. The description must include the terminal output of the guard on the final commit. If the guard cannot run against the shipping branch (circular dependency), the PR must explain why and propose a bootstrap sequence.

**Enforcement**: add a check to the PR template: "If this PR ships a hook or guard, include output of that guard run against this branch." Reviewers treat absence as a blocker.

**Estimated impact**: would have prevented B7 (broken CI coverage gate that could never execute) and surfaced the M5 design gap before merge.

### Process Change 2: Require a Contradiction Check Before Any Memory Write

**Problem**: B9 shows the agent wrote a memory entry (`get_unresolved_review_threads.py` silently undercounts) and then wrote code that depends on that same script, within the same session, without checking whether the two were consistent.

**Rule**: before writing any Serena memory entry, search existing memory for the subject term. Before writing code that depends on a memory-cited tool, read the tool's current implementation. If the memory and the code contradict, resolve the contradiction before committing either.

**Enforcement**: add to `.agents/steering/claude-skills.md`: "Before `mcp__serena__write_memory`, run `search_memory.py` for the subject. Before depending on a tool cited in memory, read the tool's source. Document contradiction resolution in the commit message."

**Estimated impact**: would have prevented B9 and the credibility damage of shipping contradictory artifacts in the same day.

### Process Change 3: Apply a Calibration Gate to Any Threshold-Based Detector Before Shipping

**Problem**: M4 rework warning uses threshold-6 but the test bed (PR #1989) has max 4 file edits. The detector cannot fire on its own PR. No calibration step was run before the threshold was committed.

**Rule**: any PR that ships a threshold-based signal (rework count, thread count, file count) must include a calibration table in the PR description. The table shows the threshold value, a sample of real PRs measured against it, and the expected firing rate. A detector that cannot fire on the last 5 PRs in the repo is not calibrated.

**Enforcement**: add a spec acceptance criterion template field: "If this requirement includes a numeric threshold, provide a calibration table using the last 5 merged PRs as sample data." The implementer must populate this field before the first commit of the detecting code.

**Estimated impact**: would have caught M4 threshold-6 before commit and produced a calibrated threshold (2 or 3) that actually fires on real work.

---

## Phase 4: Inherited Failure Mode Status

| FM | Mitigation PR #1965 Proposed | Status in PR #1989 |
|---|---|---|
| FM-1: Context Reading | MEMORY entry: pre-draft from source artifacts | Violated (B1 flag semantics, B10 em-dashes, B9 memory contradiction) |
| FM-NEW-A: Bot Cascade | Pre-push hook warning on open threads | Hook shipped but not self-applied; cascade continued at same rate |
| FM-NEW-B: Non-Atomic Change | Co-change checklists in spec | Checklists not used; M1/M4/M5 contracts spread across commits |

All three mitigations are in the correct direction. None was applied to the PR that shipped them. The failure modes are behavioral, not tooling.

---

## Remediations Summary

| Issue | Action | Owner | Priority |
|---|---|---|---|
| Guards not self-applied | PR template check: guard output required in description | architect | P0 |
| Memory contradiction on write | Add pre-write search step to steering; add source-read step before depending on cited tool | architect | P0 |
| Threshold uncalibrated | Spec template: calibration table required for any numeric threshold | architect | P1 |
| M4 threshold-6 wrong | Recalibrate to 2 or 3 using real PR sample; add relative measure option | implementer | P1 |
| B9 memory entry stale | Update `pr-review-observations.md` to reflect actual pagination behavior after M1 verification | implementer | P1 |
| ADR-035 citation without verification | Add lint rule: if docstring cites an ADR, verify implementation satisfies cited contract before commit | devops | P2 |

---

## Phase 6: Retrospective Self-Assessment

### Return on Time Invested: 3 (high return)

The recursive failure is a cleanly observable pattern. The three new process changes are each testable. The calibration gate in particular addresses a class of bugs (detector that cannot detect) that will recur in any threshold-based work.

### What Helped

- End-to-end test of M1 against the live PR confirmed the concept works. The bugs were mechanical.
- Bot convergence on B1 (4/5 bots flagged `--diff-filter=R`) made the flag error undeniable.
- Retro from PR #1965 was specific enough to trace which failure modes recurred.

### What Hindered

- RCA-1 in the PR #1965 retro misdiagnosed `get_unresolved_review_threads.py` as lacking pagination. M1 was designed against a false premise. A pre-implementation source read would have found the existing pagination before any code was written.
- M5 was designed as a standalone artifact rather than a development tool for the PR that shipped it.
- No calibration step exists anywhere in the current process. Thresholds are chosen by intuition.

### Hypothesis for Next Session

Run M5 as the first commit of any PR, before any implementation commits. If the pre-push hook fires during development, the developer is working in the same environment the hook is designed to protect. A hook that cannot run during its own development is not ready to ship.

---

## Evidence Links

- PR: https://github.com/rjmurillo/ai-agents/pull/1989
- Predecessor PR: https://github.com/rjmurillo/ai-agents/pull/1965
- Predecessor retro: `.agents/retrospective/2026-05-10-pr-1965-review-axes-convergence.md`
- PR #1887 retro (same cascade pattern, first occurrence): `.agents/retrospective/2026-05-05-pr-1887-iteration-paradox.md`
- Failure modes taxonomy: `.agents/governance/FAILURE-MODES.md`
- ADR-035 exit codes: `.agents/architecture/ADR-035-exit-code-standardization.md`
- Canonical-source-mirror rule: `.claude/rules/canonical-source-mirror.md`

---

## Retrospective Handoff

### Skill Candidates

| Skill ID | Statement | Atomicity | Operation | Target |
|---|---|---|---|---|
| guard-self-application | Any PR shipping a hook or guard must demonstrate that guard running against its own branch. | 91% | ADD | |
| memory-contradiction-check | Search existing memory before writing; read cited tool source before depending on it. | 88% | ADD | |
| threshold-calibration-gate | Any numeric threshold requires a calibration table from 5 real PRs before commit. | 90% | ADD | |
| adr-citation-verification | If a docstring cites an ADR contract, verify implementation satisfies it before committing. | 87% | ADD | |

### Memory Updates

| Entity | Type | Content | File |
|---|---|---|---|
| PR-1989-Recursive-Failure | Pattern | Tooling mitigations for behavioral failures reproduce the same failures | `.serena/memories/learnings-retro-methodology.md` |
| Guard-Self-Application | Pattern | Hook/guard must run against its own shipping branch; absent output = not ready | `.serena/memories/skills-pr-review.md` |
| Threshold-Calibration | Pattern | Detectors that cannot fire on the last 5 real PRs are not calibrated; measure before commit | `.serena/memories/skills-metrics.md` |

### Git Operations

| Operation | Path | Reason |
|---|---|---|
| git add | `.agents/retrospective/2026-05-10-pr-1989-recursive-failure.md` | Retrospective artifact |

### Handoff Summary

- **Skills to persist**: 4 candidates (atomicity >= 87%)
- **Memory files touched**: learnings-retro-methodology.md, skills-pr-review.md, skills-metrics.md
- **Recommended next**: architect (PR template check for guard self-application + calibration table in spec template) then skillbook (persist 4 skills)
