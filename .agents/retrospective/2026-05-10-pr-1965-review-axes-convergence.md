# Retrospective: PR #1965 (feat/issue-1934-review-axes-convergence)

## Session Info

- **Date**: 2026-05-10
- **PR**: #1965 (feat/issue-1934-review-axes-convergence)
- **Issues**: #1934 (child), #1933 (epic)
- **Goal**: Establish 6 canonical axis files as single source of truth for PR-quality prompts; eliminate drift between /review (local) and CI quality gate.
- **Outcome**: Merged, 58 commits, 120+ bot threads resolved, 15+ /loop turns.
- **Agents**: orchestrator, implementer, retrospective
- **Task type**: Feature (convergence refactor + new canonical module)

---

## Failure Mode Classification

Five distinct failure modes from `.agents/governance/FAILURE-MODES.md` fired in this session.

| # | Failure Mode | Instances | Commit Cost |
|---|---|---|---|
| FM-4 | False Completion Markers | 3 (thread query returned 0; sync step skipped; continue-after-error missed) | ~8 commits |
| FM-1 | Context Reading Failure | 2 (Step 0 blank elicitation; canonical regex not read before mirroring) | ~7 commits |
| FM-X | New: Additive Bot Reviewer Cascade | Every push | ~20 commits |
| FM-X | New: Non-Atomic Compound Change | Verdict token spread (3 commits instead of 1) | ~5 commits |
| FM-2 | Continuation Reset (parallel session conflict) | 1 (autofix-pr stash collision) | ~4 commits |

FM-X entries represent failure modes not yet in the taxonomy. Proposed classes are defined under Remediations below.

---

## Phase 0: Data Gathering

### Execution Trace (selected)

| Phase | Commits | Theme |
|---|---|---|
| Spec + plan | 1-2 | REQ-008 EARS syntax; spec sub-ID bug (CodeRabbit +1 commit) |
| M0-M2 axis files + sync | 3-14 | Axis files seeded; sync_plugin_lib + build_all run separately twice each |
| Round 2-4 fixes | 15-26 | Verdict token spread (UNKNOWN, NON_COMPLIANT across 3 commits); regex doc out of sync |
| Round 5-7 | 27-36 | continue-after-error bug; vendored path survival; frontmatter strict |
| Round 8-11 | 37-50 | Doc-code regex divergence on all 6 axis files; /review command regex out of sync (15-file cascade) |
| Round 12+ | 51-58 | Stash conflict from concurrent autofix-pr session; final CI green |

### Outcome Classification

- **Blocked**: thread query silent zero (3 occurrences); sync step missed (2 occurrences); stash conflict (1 occurrence).
- **Suboptimal**: verdict token spread; spec sub-ID syntax; Step 0 blank elicitation.
- **Success**: all 6 axis files landed; /review and CI share one module; 0 remaining threads.

---

## Phase 1: Five Whys on Highest-Impact Root Causes

### RCA-1: Thread query returned 0 when 12 threads were open

1. Why did the agent declare "done"? The completeness check returned 0 unresolved.
2. Why did the query return 0? `get_unresolved_review_threads.py` does not paginate and silently returns the first page only.
3. Why was pagination absent? The script was written for small PRs; no contract test for "more than 100 threads" exists.
4. Why was no contract test written? The tool was treated as a utility, not a boundary with a testable contract.
5. Why was it treated as a utility? No rule required evidence-of-completeness tools to have pagination tests.

**Root cause**: tooling that gates completeness decisions has no enforced pagination contract. Silent truncation becomes a false completion marker.

### RCA-2: Doc-code regex divergence on 6 axis files (16-file cascade)

1. Why did 6 axis files document the wrong regex? The agent wrote the docstring from memory, not from the canonical `_EXTRACT_VERDICT_PATTERN`.
2. Why from memory? Step 1 of the implementation did not include "grep canonical source before writing mirroring docstring."
3. Why not? The canonical-source-mirror rule (`.claude/rules/canonical-source-mirror.md`) was not checked before writing axis prompts.
4. Why not checked? The rule applies to hooks and scripts. Axis prompt files were not in scope in the author's working model.
5. Why the scoping mismatch? The rule's `applyTo` glob does not cover `.claude/review-axes/`.

**Root cause**: canonical-source-mirror rule has a glob gap. Prompt files that embed regex contracts are not bound by it, so the read-before-mirror discipline was skipped.

### RCA-3: Verdict token spread across 3 commits

1. Why did UNKNOWN and NON_COMPLIANT land in 3 separate commits? Each bot reviewer flagged a different code site independently.
2. Why were sites handled separately? The agent treated each bot comment as an independent ticket.
3. Why not batched? No checklist existed for "every location a new verdict token must appear" (action.yml, `$blockingVerdicts`, exit_code case, emoji map, alert map, merge prose).
4. Why no checklist? The verdict token contract was not documented as an atomic multi-site change.
5. Why undocumented? The spec (REQ-008) described behavioral outcomes, not the internal implementation topology.

**Root cause**: the spec was outcome-level only. No implementation checklist enumerated co-change sites for a verdict token addition.

---

## Phase 2: Diagnosis

### Critical Failures (P0)

| Finding | Evidence | Root Cause |
|---|---|---|
| Thread query silent zero | 3 premature "done" declarations | No pagination; FM-4 |
| Sync step partial run | "Validate Generated Files" CI failures on alternating commits | No pre-push checklist enforcing both sync_plugin_lib AND build_all in order |
| Concurrent session stash collision | UU conflicts after autofix-pr push | No guard preventing parallel push sessions on the same branch |

### Structural Wastes (P1)

| Finding | Impact |
|---|---|
| Bot reviewer cascade (4 bots, fresh scan per push) | ~20 commits are pure bot-response commits |
| Verdict token non-atomic | 3 commits where 1 was sufficient |
| Regex doc divergence (axis files + /review command) | Two separate 6-15 file cascades |
| Step 0 blank elicitation | 1 extra turn, user frustration |

---

## Phase 3: Three Highest-Leverage Interventions

These three changes would have cut commit count from 58 to approximately 25.

### Intervention 1: Enforce pagination on any completeness-gate tool

**Impact**: eliminates the 3 false "done" declarations. Estimated savings: 8 commits.

**Mechanism**: add a pytest contract test for `get_unresolved_review_threads.py` that asserts cursor-paginated behavior when total > 100. The test runs in CI. No completeness gate may use a tool that lacks this test.

**Proposed ADR**: extend ADR-034 (investigation-session-qa-exemption) to require that any script used as a completeness signal must have a pagination contract test. Add to `.agents/governance/TESTING-RIGOR.md`.

### Intervention 2: Widen canonical-source-mirror rule to cover prompt files

**Impact**: catches regex doc divergence at write time rather than at bot-review time. Two 6-15 file cascades eliminated. Estimated savings: 15 commits.

**Mechanism**: update `.claude/rules/canonical-source-mirror.md` `applyTo` glob to include `.claude/review-axes/`, `.claude/skills/*/SKILL.md`, and `.github/prompts/`. Any file in these paths that uses the word "matches", "mirrors", or embeds a regex literal must cite the canonical source and quote it verbatim on the first commit.

**Proposed change**: file rule edit + steering note in `.agents/steering/claude-skills.md`.

### Intervention 3: Require co-change checklists for multi-site contract tokens

**Impact**: collapses verdict token spread from 3+ commits to 1. Prevents any future token addition from producing the same cascade. Estimated savings: 5 commits.

**Mechanism**: add a `co-change-checklist` section to the spec template for changes that introduce or rename verdict tokens. The checklist enumerates every site the token must appear: action.yml validity case, `$blockingVerdicts` array, exit_code case, emoji map, alert map, merge prose, docstrings in axis files, CI prompt mirrors. The implementer must check all sites in one commit.

**Proposed change**: update `templates/agents/implementer.shared.md` Evidence Standards section to require co-change checklists when spec includes "new verdict" or "rename token" keywords.

---

## Phase 4: New Failure Mode Proposals

### FM-NEW-A: Additive Bot Reviewer Cascade

**Description**: 4 independent bot reviewers (Copilot, Cursor Bugbot, Devin, CodeRabbit) each run a full-PR scan on every push. Each push can open 4-12 new threads regardless of whether the diff is targeted. The fix-one-trigger-three pattern is structural, not agent error.

**Root cause**: bots rate-limit by commit SHA, not by thread state. Each push is a fresh review surface.

**Mitigation** (not elimination): batch all bot-response fixes into one push per review round. Never push a single-file fix commit when pending bot threads exist. Wait for the full review pass, cluster by root cause (per `.claude/MEMORY.md` guidance), then push one batched commit.

**Proposed enforcement**: add a pre-push hook that warns when there are open bot review threads. The agent must explicitly acknowledge "pushing with N open threads, batching all fixes" before proceeding.

### FM-NEW-B: Non-Atomic Compound Change

**Description**: a conceptually atomic change (add a new verdict token) is spread across 3 or more commits because each bot thread is treated as an independent unit of work.

**Root cause**: no pre-implementation checklist enumerates all co-change sites. Sites are discovered reactively from bot feedback.

**Mitigation**: co-change checklists in spec (see Intervention 3). The implementer writes all sites in one commit rather than discovering them from review.

---

## Remediations Summary

| Issue | Action | Owner | Priority |
|---|---|---|---|
| Thread query pagination | Add contract test to `get_unresolved_review_threads.py`; gate completeness on pagination-verified tool | implementer | P0 |
| Canonical-source-mirror glob gap | Widen `applyTo` in `.claude/rules/canonical-source-mirror.md` | architect | P0 |
| Co-change checklist absent | Add co-change-checklist section to spec template | architect | P1 |
| Bot cascade no batching rule | Add pre-push hook warning on open threads; document batch-fix protocol | devops | P1 |
| Concurrent session conflict | Document single-session-per-branch constraint in SESSION-PROTOCOL.md | architect | P1 |
| Step 0 blank elicitation | Add MEMORY entry: pre-draft Q1-Q6 from issue body before asking | agent instruction | P2 (already in MEMORY.md) |
| Spec sub-ID syntax | CodeRabbit catches this; acceptable single-commit cost | n/a | P3 |

---

## Phase 6: Retrospective Self-Assessment

### Return on Time Invested: 3 (high return)

The failure modes documented here are structural and recurring. PR #1887 found bot cascade and pagination issues first. This session confirmed them at larger scale (58 vs 69 commits, same root causes). The three interventions are concrete and implementable. The new failure mode classifications give future sessions a classification target.

### What Helped

- Bot thread clustering (`MEMORY.md` guidance) reduced the blast radius on rounds 8-11.
- context-mode batch indexing kept the working context from flooding.
- `gh pr view --json commits` gave an accurate commit timeline without scrolling.

### What Hindered

- `get_unresolved_review_threads.py` silent truncation was invisible; no error, no warning.
- sync_plugin_lib and build_all are separate commands with no wrapper that runs both. Every missed pairing produced a CI failure.
- The canonical-source-mirror rule did not bind the axis prompt files, so the regex divergence was invisible until bot review.

### Hypothesis for Next Session

Add a single `sync_all.py` script that runs `sync_plugin_lib.py` then `build_all.py` in order and exits non-zero if either fails. A pre-push hook that calls `sync_all.py --check` would have prevented all sync-related CI failures.

---

## Evidence Links

- PR: https://github.com/rjmurillo/ai-agents/pull/1965
- Issue: https://github.com/rjmurillo/ai-agents/issues/1934
- Epic: https://github.com/rjmurillo/ai-agents/issues/1933
- Prior retro (same bot cascade pattern): `.agents/retrospective/2026-05-05-pr-1887-iteration-paradox.md`
- Canonical-source-mirror rule: `.claude/rules/canonical-source-mirror.md`
- Failure modes taxonomy: `.agents/governance/FAILURE-MODES.md`

## Retrospective Handoff

### Skill Candidates

| Skill ID | Statement | Atomicity | Operation | Target |
|---|---|---|---|---|
| completeness-gate-pagination | Any script used as a completeness gate must have a pagination contract test. | 91% | ADD | |
| canonical-mirror-prompt-files | Read and quote canonical source before embedding a regex in any prompt file. | 93% | ADD | |
| verdict-token-co-change | Add all co-change sites for a verdict token in one commit. | 90% | ADD | |
| bot-review-batch-fix | Batch all bot-thread fixes into one push per review round; never push single-file fixes with open threads. | 88% | ADD | |

### Memory Updates

| Entity | Type | Content | File |
|---|---|---|---|
| PR-1965-Learnings | Learning | Silent pagination truncation in completeness tools causes false completion markers | `.serena/memories/learnings-pr-review-completeness.md` |
| Canonical-Mirror-Gap | Pattern | canonical-source-mirror rule must cover prompt files embedding regex contracts | `.serena/memories/skills-canonical-source.md` |
| Verdict-Token-Co-Change | Pattern | New verdict tokens have 7+ co-change sites; enumerate all in spec before implementing | `.serena/memories/skills-verdict-token-atomic.md` |

### Git Operations

| Operation | Path | Reason |
|---|---|---|
| git add | `.agents/retrospective/2026-05-10-pr-1965-review-axes-convergence.md` | Retrospective artifact |

### Handoff Summary

- **Skills to persist**: 4 candidates (atomicity >= 88%)
- **Memory files touched**: learnings-pr-review-completeness.md, skills-canonical-source.md, skills-verdict-token-atomic.md
- **Recommended next**: skillbook (persist 4 skills) then architect (widen canonical-source-mirror glob + co-change checklist in spec template)
