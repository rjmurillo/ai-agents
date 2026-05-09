# Execution Plan: REQ-006 Step 0 First Principles Gate

## Metadata

| Field | Value |
|-------|-------|
| **Status** | In Progress |
| **Created** | 2026-05-09 |
| **Owner** | implementer |
| **Complexity** | Low (Tier 1; two markdown files + optional ADR) |
| **Issue** | #1926 |
| **REQ** | REQ-006 |
| **DESIGN** | DESIGN-006 |
| **TASK** | TASK-006 |

## Objectives

- [ ] M1: Insert Step 0 gate in `.claude/commands/spec.md` (TASK-006-1, 2, 3, 4)
- [ ] M2: Mirror to `src/copilot-cli/skills/spec/SKILL.md` and verify XML (TASK-006-5, 6)
- [ ] M3: Run 13 dynamic + 2 static validation tests (TASK-006-8)
- [ ] M4 (optional): Write ADR-060 (TASK-006-7)

## Milestones

### M1: Core Gate in spec.md (root milestone)

**Outcome**: Step 0 First Principles gate is live in `.claude/commands/spec.md`. Any agent or human invoking `/spec` encounters the gate before Step 1.

**Tasks**:
- TASK-006-1: Insert Step 0 block (XS, 2-3h)
- TASK-006-2: Narrow Step 1 (XS, 1h)
- TASK-006-3: Update Step 3 Tier 5 bullet (XS, 0.5h)
- TASK-006-4: Add Step 9 critic checks with binary 9a/9b/9c phrasing (XS, 1h)

**Exit Criteria**:
- [ ] Step 0 block precedes Step 1 heading (grep verifiable)
- [ ] Step 1 contains "Do not re-elicit Q1-Q6 here" (grep verifiable)
- [ ] Tier 5 bullet contains `Re-validate Step 0 Q4` AND not `why not simpler?`
- [ ] Step 9 contains Check 9a, 9b, 9c with explicit PASS/FAIL conditions
- [ ] Hedge phrase list embedded as multi-word phrases only (no standalone `should`/`might`/`could`)
- [ ] Operational tests for speculative/aspirational/specific present
- [ ] Halt message schema (5 fields) present
- [ ] **Kill criteria reference present** in Step 0 prose: grep returns match for `STEP-0-METRICS.md` OR `kill criteria` (covers AC-13, was missing in v1)
- [ ] **STEP-0-METRICS.md tally write instruction present**: Step 0 prose instructs the agent to append a one-line tally entry (`<ISO timestamp>|<pass|fail>|<halt-trigger-or-none>`) to `.agents/sessions/STEP-0-METRICS.md` after each evaluation, creating the file lazily if absent (resolves STEP-0-METRICS.md ownership gap)

**Estimate**: 4.5-5.5h. **Dependencies**: none.

### M2: Mirror to Copilot CLI

**Outcome**: SKILL.md edited body sections are byte-identical to spec.md edited body sections. Frontmatter preserved unchanged. Per-line offset between the two files is acceptable so long as the four edited sections themselves match.

**Tasks**:
- TASK-006-5: Mirror to SKILL.md (XS, 1h)
- TASK-006-6: ~~Verify XML file~~ — **resolved during planning**: `src/copilot-cli/skills/memory/spec/skill-specification.xml` is memory-skill XML metadata, not spec body. No edit needed. (0h)

**Exit Criteria**:
- [ ] **Edited body sections only** of `src/copilot-cli/skills/spec/SKILL.md` are byte-identical to corresponding sections of `.claude/commands/spec.md`. Frontmatter and any pre-existing prose differences outside edited sections are out of scope. The "byte-identical" claim covers: (a) the new Step 0 block, (b) the Step 1 narrowing replacement text, (c) the Step 3 Tier 5 replacement text, (d) the Step 9 added checks.
- [ ] SKILL.md frontmatter unchanged (verified by diff of frontmatter region)
- [ ] PR description documents any structural deviation per `.claude/rules/canonical-source-mirror.md`

**Estimate**: 1h. **Dependencies**: M1 complete.

### M3: Validation (machine-checkable static + parser-based; LLM cases as documented spot-checks)

**Outcome**: Acceptance criteria are split into machine-verifiable (static + Python parser) and LLM-dependent (spot-checks). Machine cases are CI-stable; LLM cases are documented manual checks the implementer runs once with transcripts attached.

**Rationale for split** (resolves pre-mortem F1 + critic Finding 6): the original "13 dynamic /spec invocations" plan was structurally untestable — each invocation costs 5-15 min, results are non-deterministic across model versions, no harness exists. Replaced with a Python pytest at `tests/commands/test_spec_step0.py` that:
1. Parses the canonical hedge phrase list out of `.claude/commands/spec.md` (extract the fenced table).
2. Runs `re.search(phrase, answer, re.IGNORECASE)` against each T1-T13 input.
3. Asserts which trigger fires (H1/H2/H3/H4/H5) per expected outcome.

This makes T1, T5, T6, T7, T8, T11 fully automated. T2, T3, T4, T10, T12, T13 remain LLM-dependent (they probe the model's interpretation of the spec, not the regex). They become documented spot-checks, not gates.

**Tasks**:
- TASK-006-8a: Write `tests/commands/test_spec_step0.py` with parser + 6 automated cases (S, 2h)
- TASK-006-8b: Run 6 LLM spot-check invocations (T2, T3, T4, T10, T12, T13); attach transcripts to PR (XS, 1-2h)

**Exit Criteria**:
- [ ] `tests/commands/test_spec_step0.py` exists and passes
- [ ] Static-1 (grep checks) passes — encoded in the same pytest
- [ ] Static-2 (diff of edited sections between spec.md and SKILL.md is zero) passes — encoded in the same pytest
- [ ] T2, T3, T4, T10, T12, T13 spot-checks executed; transcripts attached to PR with model+version stamp
- [ ] Static check that H5 trigger phrase (e.g., "partial completion") is present in Step 0 block (covers T11 statically)

**Estimate**: 3-4h. **Dependencies**: M1 + M2 complete.

### M4 (optional): ADR-060

**Outcome**: `.agents/architecture/ADR-060-spec-step0-first-principles-gate.md` exists with Status: Proposed.

**Tasks**:
- TASK-006-7: Write ADR-060

**Exit Criteria**:
- [ ] File exists at canonical path
- [ ] Context, Decision, Consequences, Alternatives Considered sections present
- [ ] References REQ-006 and issue #1926

**Estimate**: 1h. **Dependencies**: none. Parallel with M1-M3.

## Dependency Graph

```
M1 (spec.md)
  └──> M2 (SKILL.md mirror; XML resolved no-op during planning)
         └──> M3 (pytest + 6 LLM spot-checks)

M4 (ADR-060) ──> independent, parallel with anything
```

Critical path: M1 → M2 → M3 (~8.5-10.5h, plus M4 1h if included = 9.5-11.5h total).

## Commit Strategy (single PR, bisect-friendly)

Commit 1 split into three sub-commits per critic Finding 5: the original "5 concepts in one commit" was not bisectable. Each sub-commit is independently revertible if a single concept fails review.

| # | Commit | Type | Files | Tasks |
|---|---|---|---|---|
| 1a | Insert Step 0 skeleton with six labelled questions Q1-Q6 | `feat(spec)` | `.claude/commands/spec.md` | TASK-006-1 part 1 |
| 1b | Add hedge phrase list + operational tests for speculative/aspirational/specific | `feat(spec)` | `.claude/commands/spec.md` | TASK-006-1 part 2 |
| 1c | Add halt message schema + kill criteria reference + STEP-0-METRICS.md tally instruction | `feat(spec)` | `.claude/commands/spec.md` | TASK-006-1 part 3 |
| 2 | Narrow Step 1, update Tier 5, add binary Step 9 checks (9a, 9b, 9c) | `feat(spec)` | `.claude/commands/spec.md` | TASK-006-2,3,4 |
| 3 | Mirror edited sections to Copilot CLI SKILL.md | `feat(spec)` | `src/copilot-cli/skills/spec/SKILL.md` | TASK-006-5 |
| 4 | Validation tests + static lint (pytest with parser, 6 automated cases) | `test(spec)` | `tests/commands/test_spec_step0.py` (new) | TASK-006-8a |
| 5 | ADR-060 (optional) | `docs(adr)` | `.agents/architecture/ADR-060-*.md` | TASK-006-7 |

Total commits: 6-7 (within 20-commit PR budget, well under the 10-commit warning threshold). Each commit ≤5 files per AGENTS.md (every commit here is 1 file).

LLM spot-checks (TASK-006-8b: T2, T3, T4, T10, T12, T13) are not commits; they are PR-description evidence.

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| SKILL.md structure differs from spec.md, requiring adapted placement | MED (CONFIRMED: 3-line frontmatter offset already known) | MED | M2 exit redefined to "edited body sections only," not full file. Frontmatter offset accepted. Document deviation per `.claude/rules/canonical-source-mirror.md` |
| Step 9 additions overlap an existing critic check | LOW | LOW | Diff Step 9 before/after; merge rather than append if overlap |
| Hedge phrase list still produces false positives in real use | MED | MED | Kill criteria (REQ-006-13) at 30-invocation review; tally written by Step 0 instruction (M1 exit criteria). At ≥30% false-positive rate, loosen list or remove standalone substring matching |
| `STEP_0_REQUIRES_ELICITATION` halt has no caller that recognizes it | HIGH | LOW | Documented in plan + ADR-060 as a prose convention only. The halt is enforcement-by-instruction, not enforcement-by-protocol. Acceptable for v1; future iteration adds machine-readable halt protocol when an orchestrator caller is built |
| Hedge substring matching degrades to LLM judgment-based pattern matching at runtime | HIGH | MED | Pytest parses the canonical hedge list out of spec.md and runs deterministic `re.search` on T1, T5, T6, T7, T8 inputs. The pytest catches drift between spec.md instruction text and real model behavior — the manual spot-checks (T2, T3, T4) document the H1/H2 boundary |
| spec.md and SKILL.md drift in future edits | HIGH (recurring pattern in this codebase per drift-detection retros) | MED | Pytest Static-2 check (diff of edited sections is zero) runs on every PR touching either file. New retro candidate if this fires |
| Step 0 itself fails its own kill criteria within first 30 invocations | MED | LOW (designed in) | REQ-006-13 makes this expected; loosen or remove in follow-up PR |
| LLM spot-checks (T2, T3, T4, T10, T12, T13) take longer than estimated | MED | LOW | Buffer: 1-2h band on TASK-006-8b. If spot-checks exceed 2h, document failures and stop; do not block PR on documenting all 6 |
| STEP-0-METRICS.md is never written (agent skips the tally instruction in production) | MED | MED (kill criteria become unfireable) | Add a static check that the tally instruction text is present in Step 0 prose. Long-term: hook-based tally that runs after each `/spec` regardless of model behavior. Not in scope for v1 |

## Reversibility

| Milestone | git revert covers | git revert does NOT cover |
|---|---|---|
| M1 (spec.md edits) | All prose changes; instant rollback | Any `STEP-0-METRICS.md` rows that landed before revert (the file lives in `.agents/sessions/`; manual cleanup required if rolled back). LLM behavior caches across sessions are not affected by revert (Step 0 stops being instructed; old halts already happened) |
| M2 (SKILL.md mirror) | All prose changes; instant rollback | None |
| M3 (pytest) | Test file deletion | LLM session transcripts attached to PR description (these are evidence, not files) |
| M4 (ADR-060) | ADR file deletion | None |

No schema, no DB, no CI changes. The single quirk is `STEP-0-METRICS.md` rows that may have accumulated between M1 merge and M1 revert. These rows are not load-bearing (REQ-006-13 says "absence of the file does not block /spec") and can be deleted in a follow-up commit.

## Decision Log

| Date | Decision | Rationale | Alternatives Considered |
|------|----------|-----------|------------------------|
| 2026-05-09 | Single PR with 6-7 bisect-friendly commits | Total diff <500 lines; commit 1 split into 1a/1b/1c so each Step 0 concept (skeleton, hedge list + operational tests, halt schema + kill criteria) is independently revertible | Multi-PR (rejected: too small); single squash (rejected: loses bisect); original v1 single commit 1 (rejected after critic Finding 5: 5 concepts in one diff) |
| 2026-05-09 | Keep all six questions, narrow via kill criteria | Retro evidence (9 cases) shows different questions catch different failures; Q3 alone catches 4 of 9, all six needed for case 1 (PR #1887) | Ship Q3 alone (rejected after retro analysis); ship Q1+Q3+Q5 only (rejected: still loses 1 of 9) |
| 2026-05-09 | Replace 13 dynamic /spec invocations with parser-based pytest + 6 LLM spot-checks | Pre-mortem F1: 13 LLM-dependent tests are non-deterministic and cost 1-3h wall time per run with no harness. Pytest parses hedge list from spec.md and runs `re.search` on T1/T5/T6/T7/T8 inputs deterministically. T2/T3/T4/T10/T12/T13 remain LLM-dependent because they probe interpretation, not regex; documented as one-time spot-checks | Original "manual verification, no harness" (rejected after pre-mortem); fully automated end-to-end (rejected: T2/T3 boundary requires LLM judgment) |
| 2026-05-09 | M2 exit criteria redefined from "byte-identical full file" to "byte-identical edited body sections only" | spec.md and SKILL.md have non-matching frontmatter (3-line offset confirmed). Full-file byte-identity is structurally impossible; edited-section identity is the meaningful invariant | Full-file diff (rejected: impossible); no diff check (rejected: drift is a known recurring failure) |
| 2026-05-09 | TASK-006-6 XML check resolved no-op during planning | Pre-read confirmed `src/copilot-cli/skills/memory/spec/skill-specification.xml` is memory-skill XML metadata (lines 1-242 are XML structure), not spec body prose. No "Step 1" / "Clarify" / "complexity tier" matches. No edit needed | Defer to M2 execution (rejected per critic Finding 6: 5-min planning cost vs M2 estimate uncertainty) |
| 2026-05-09 | STEP-0-METRICS.md tally written by Step 0 instruction (lazy-create) | REQ-006-13 measurement infrastructure had no owner in v1 plan. Adding "instruct agent to append tally line, lazy-create file" to M1 exit criteria fixes the unfireable kill criteria | Hook-based tally (rejected: out of scope for v1; future iteration); pre-create empty file in M1 commit (rejected: still requires write instruction in Step 0 prose anyway) |
| 2026-05-09 | `STEP_0_REQUIRES_ELICITATION` documented as prose convention only | Pre-mortem F2: no caller in the orchestrator parses halt reasons. Acknowledging this as a v1 limitation rather than fictional protocol enforcement | Build orchestrator parser (rejected: scope creep; out of REQ-006); remove auto-mode AC entirely (rejected: behavior is still useful as instruction even without enforcement) |

## Progress Log

| Date | Update | Agent |
|------|--------|-------|
| 2026-05-09 | Plan v1 created from REQ-006 v2 | milestone-planner |
| 2026-05-09 | Plan v2 after pre-mortem (5 failure modes) and critic review (6 defects). Changes: AC-13 added to M1 exit; STEP-0-METRICS.md tally instruction added to M1 exit; M2 exit redefined to body-sections-only; TASK-006-6 resolved no-op during planning; T1-T13 split into 6 automated pytest cases + 6 LLM spot-checks; commit 1 split into 1a/1b/1c for bisect; Reversibility expanded with what `git revert` does NOT cover; Risk Register expanded with `STEP_0_REQUIRES_ELICITATION` honest limitation, hedge-substring degradation risk, and spec.md/SKILL.md drift risk. Effort: 9.5-11.5h with M4. | implementer |

## Blockers

- None

## Related

- Issue: #1926
- REQ: REQ-006 v2
- DESIGN: DESIGN-006
- TASK: TASK-006
- Sibling issue: #1925 (ontology elicitation as Phase 0 of spec-generator)
- Evidence retro: `.agents/retrospective/2026-05-05-pr-1887-iteration-paradox.md` Phase 6
