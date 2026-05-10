# Execution Plan: REQ-008 Step 0.5 Memory-First Gate

## Metadata

| Field | Value |
|-------|-------|
| **Status** | In Progress |
| **Created** | 2026-05-09 |
| **Owner** | implementer |
| **Complexity** | Medium (Tier 2; 9.5-14.5 hours) |

## Objectives

- [x] M1: Verify three skill SKILL.md files exist and document invocation contract
- [x] M2: Insert Step 0.5 block in `.claude/commands/spec.md` (2 commits: 1d60205f scaffold, b97378f1 halt+supplemental+metrics)
- [x] M3: Append check 9d to Step 9 pre-mortem (serialized after M2)
- [ ] M4: Add static validation tests using heading-anchored parser
- [ ] M5: Manual + pytest-promoted validation of D1-D14 dynamic checks

## Milestones (revised post-critique)

### M1: Prerequisite Skill Contract Verification (XS, 0.5-1h)

**Exit criteria**:
- [ ] `chestertons-fence/SKILL.md` exists and `Skill(skill="chestertons-fence")` invocation contract documented in PR description
- [ ] `memory/SKILL.md` exists and `search_memory.py` invocation pattern documented
- [ ] `exploring-knowledge-graph/SKILL.md` exists and depth parameter contract documented
- [ ] Findings recorded in PR description (path, version, invocation pattern)

**Dependencies**: none.

### M2: Insert Step 0.5 Block (M, 4-6h, 2 commits)

**Pre-flight (locked before any commit)**:
- Step 0.5 heading text: `### Step 0.5: Memory-First Gate (blocking, runs after Step 0)`
- Halt info-string: `step0_5-halt`
- PriorArtBlock subsections: `### Direct prior art from memory`, `### Connected context from exploring-knowledge-graph`, `### Coverage notes`
- Sub-block heading on tier upgrade: `### Supplemental (Phase 5)`

**Commit 2A** `docs(spec): add Step 0.5 Memory-First Gate scaffold and skill invocations`
- AC-01 (heading order between Step 0 and Step 1)
- AC-02 (ProvisionalTier computation, both mapping tables, max() formula, hours extraction rule, default-T2 if no hours found)
- AC-03 (chestertons-fence invocation with target=Q3 path, change=Q4 wedge)
- AC-04 (memory invocation with topic definition, 3+ query variants per topic)
- AC-05 (exploring-knowledge-graph depth table per ProvisionalTier)
- AC-06 (zero-result coverage note rule)
- AC-07 (three degradation rules: chestertons-fence, Forgetful, exploring-knowledge-graph)
- AC-08 (entity adjudication workflow: in-scope/out-of-scope/blast-radius; auto-mode case-insensitive match rule; human-mode override path)
- PriorArtBlock format with three subsections (`### Direct prior art from memory`, `### Connected context from exploring-knowledge-graph`, `### Coverage notes`)
- 2A guard string: include literal `<!-- step0.5:incomplete-without-2b -->` HTML comment that 9d can detect (prevents 2A-only false-positive on AC-12 if 2B is reverted)
- Files: `.claude/commands/spec.md`

**Commit 2B** `docs(spec): add Step 0.5 halt criteria, supplemental hook, and metrics tally`
- AC-09 (H11 halt trigger; step0_5-halt block schema with 5 fields verbatim; deferral text verbatim; auto-mode threshold 3, human-mode threshold 2)
- AC-10 (supplemental Phase 5 hook; trigger formula `actual_tier > provisional_tier AND phases_needed(actual_tier) > phases_run(provisional_tier)`; `### Supplemental (Phase 5)` sub-block heading)
- AC-11 (STEP-0.5-METRICS.md tally line format; 100-entry rotation policy)
- 2B removes the `<!-- step0.5:incomplete-without-2b -->` guard string
- Files: `.claude/commands/spec.md`

**Exit criteria**:
- [ ] All 11 AC clauses (AC-01 through AC-11) present in Step 0.5 prose
- [ ] Halt info-string `step0_5-halt` cited verbatim with all 5 fields
- [ ] All three subsection heading strings cited verbatim
- [ ] Pre-commit hooks pass

**Dependencies**: M1.

### M3: Append Check 9d to Step 9 (XS, 1h, 1 commit)

**Commit 3** `docs(spec): add Step 9 check 9d for Prior Art / Constraints presence`
- Files: `.claude/commands/spec.md`

**Exit criteria**:
- [ ] Check 9d appears in Step 9 list after 9c (AC-12)
- [ ] PASS/FAIL conditions defined; references Step 0.5 subsection heading strings verbatim
- [ ] No reorder of 9a/9b/9c

**Dependencies**: M2 complete and merged (BOTH commits 2A AND 2B). 9d must include guard-string check: if `<!-- step0.5:incomplete-without-2b -->` is present in spec.md, 9d emits FAIL with reason "Step 0.5 implementation incomplete; 2B not landed". This prevents AC-12 false-positive on partial M2.

### M4: Static Validation Tests (S, 2-4h, 1 commit)

**Commit 4** `test(commands): add static validation for Step 0.5 spec.md insertion`
- Files: `tests/commands/test_spec_step0_5.py`, `tests/commands/step0_5_parser.py`

**Exit criteria**:
- [ ] Parser couples to heading strings, not line offsets (per pre-mortem F3)
- [ ] Static checks with explicit AC mapping (12 checks total covering 11 step-0.5 ACs + check 9d):
  - S1: heading order (AC-01)
  - S2: ProvisionalTier mapping tables present (AC-02)
  - S3: chestertons-fence invocation string with target/change params (AC-03)
  - S4: memory invocation prose mentions "3+" or "three" distinct queries (AC-04)
  - S5: depth table for Tier 1-2/3/4-5 present (AC-05)
  - S6: zero-result coverage note rule prose present (AC-06)
  - S7: all three degradation rules present (AC-07)
  - S8: AC-08 auto-mode case-insensitive match rule prose present, threshold 3 specified (AC-08)
  - S9: step0_5-halt info-string with all 5 field names; H11; deferral text verbatim (AC-09)
  - S10: supplemental trigger formula `actual_tier > provisional_tier AND phases_needed > phases_run` present (AC-10)
  - S11: STEP-0.5-METRICS.md string + tally format `<ISO-8601> | <pass|fail> | <trigger-or-none> | <check-or-none>` (AC-11)
  - S12: check 9d in Step 9 + guard-string detection (`<!-- step0.5:incomplete-without-2b -->` absence required) (AC-12)
- [ ] `compute_provisional_tier(q4_text, entity_count)` reference impl with 4 reference cases
- [ ] `pytest tests/commands/` exits 0
- [ ] Tests follow AAA pattern, no global state

**Dependencies**: M3 complete and merged.

### M5: Validation Run with Pytest-Promotion (S, 2-3h)

**Tasks**:
- D-list defined in `TASK-008-5` (`.agents/specs/tasks/TASK-008-spec-memory-first-gate.md`, "TASK-008-5: Manual validation run" section, lines D1-D14).
- Promote deterministic checks to pytest (8 cases): D1 (Step 0 → Step 0.5 ordering), D2 (ProvisionalTier=2 with 4-6h+2 entities), D3 (chestertons-fence target/change), D4 (3+ memory queries for "spec.md" topic), D5 (zero-result coverage note), D8 (3 blast-radius → H11 emitted), D10 (pass tally line), D11 (halt tally line).
- Manual checks (6, with tracked follow-on issue for promotion): D6 (Forgetful unavailable simulation), D7 (graph traversal entity discovery), D9 (1 blast-radius → no halt), D12 (Step 9 9d PASS), D13 (Step 9 9d FAIL after manual block removal), D14 (Step 3 tier upgrade triggers Phase 5 supplemental).
- Single live `/spec` invocation exercising halt path + pass path + degradation path.

**Commit 5** `test(commands): promote deterministic Step 0.5 dynamic checks to pytest`
- Files: `tests/commands/test_spec_step0_5_dynamic.py`

**Exit criteria**:
- [ ] 8 dynamic checks promoted to pytest; pass
- [ ] 6 manual checks documented in PR description with evidence (transcript or screenshot)
- [ ] Tracked issue filed for promoting remaining manual checks to automation
- [ ] `STEP-0.5-METRICS.md` shows correct format from real `/spec` run

**Dependencies**: M4.

## Dependency Graph

```
M1 -> M2 -> M3 -> M4 -> M5
```

Serial chain. M3 was originally parallel with M2 but pre-mortem F6 (merge conflict on spec.md) forced serialization.

## Decision Log

| Date | Decision | Rationale | Alternatives Considered |
|------|----------|-----------|------------------------|
| 2026-05-09 | Collapse M2 from 5 commits to 2 | Five sequential commits on one file = sequential coupling; no checkpoint between commits 1-4 (pre-mortem F2 + critic finding 2). Two commits separate scaffold (low-risk) from halt+metrics (validator-sensitive). | (a) 5 commits as originally planned; (b) 1 single commit losing reviewability |
| 2026-05-09 | Serialize M3 after M2 | Both edit `.claude/commands/spec.md`. Parallel branches cause rebase conflicts (pre-mortem F6, critic finding 3). M3's 9d references M2's heading strings. | Original parallel-with-M2 design |
| 2026-05-09 | Lock contract artifacts before M2 begins | Step 0.5 heading, halt info-string, subsection names locked in pre-flight. Prevents M4 parser from coupling to drifting line numbers (pre-mortem F3). | Iterative refinement during M2 |
| 2026-05-09 | M1 expanded to invocation contract verification | `ls`-only check is theater (pre-mortem F1, critic finding 6). Skill must be invocable, not merely present. | Original "verify file exists" scope |
| 2026-05-09 | M5 promotes deterministic checks to pytest | Manual-only validation degrades silently after ship (pre-mortem F5). 8 of 14 checks are deterministic enough to automate. | All-manual M5 |
| 2026-05-09 | Auto-mode blast-radius threshold = 3 | Conservative default at 2 produces false halts on Tier 3+ traversals (Step 9 pre-mortem #2). Human-mode keeps 2-entity threshold. | Keep at 2; raise both human and auto-mode |
| 2026-05-09 | Default ProvisionalTier = 2 if no hours found | Q4 free-text parsing fails on "a few days" / "not sure". T2 default + Step 3 supplemental (AC-10) is safety net (analyst GAP-01). | Default T3 conservative; halt on parse fail |
| 2026-05-09 | Q4 wedge revised to include gate infrastructure | Step 9 check 9c FAIL on original wedge ("three skill calls" only). Revised wedge includes halt criteria, adjudication, metrics, supplemental hook because these are inherent to any blocking gate. | Defer AC-10/AC-11 to follow-on; narrow ACs to fit original wedge |

## Progress Log

| Date | Update | Agent |
|------|--------|-------|
| 2026-05-09 | Plan created from REQ-008/DESIGN-008/TASK-008 after /spec workflow completed | planner |
| 2026-05-09 | Revised post pre-mortem (7 findings) and critic (6 findings); M2 collapsed, M3 serialized, M1 expanded, M5 partial pytest promotion | planner |
| 2026-05-09 | Critic v2 surgical fixes: AC-08 explicit in 2A; M4 12-check AC mapping; M5 D-list inlined with citation; 2A guard-string + M3 guard-detection prevents AC-12 false-positive on partial M2 | planner |
| 2026-05-09 | M1 complete. Three SKILL.md files verified; invocation contracts documented at .agents/plans/active/req-008-m1-skill-contracts.md. Branch feat/req-008-step-0-5-memory-first-gate. | implementer |
| 2026-05-10 | M2 complete. Step 0.5 inserted into .claude/commands/spec.md across 2 commits (1d60205f scaffold AC-01 to AC-08; b97378f1 halt+supplemental+metrics AC-09 to AC-11). Guard string introduced and removed. spec.md grew from 199 to 339 lines. | implementer |
| 2026-05-10 | M3 complete. Check 9d appended to Step 9 pre-mortem list (AC-12). 9a/9b/9c untouched. 9d FAIL conditions include guard-string detection per plan. Step 9 narrative updated to cover 9a-9d. | implementer |

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| M2 spec.md edit breaks /spec for all callers | LOW | HIGH | Per-commit revert path: `git revert <SHA>` of 2A or 2B. Two-commit structure isolates scaffold (2A, low-risk) from halt logic (2B, validator-sensitive). Emergency bypass: HTML-comment Step 0.5 prose. |
| M2 commit 2B fails after 2A lands | MED | LOW | spec.md after 2A only contains the `<!-- step0.5:incomplete-without-2b -->` guard string. Step 9 check 9d detects guard and emits FAIL. AC-12 cannot false-positive on partial M2. Revert 2A or proceed with 2B. |
| M4 parser couples to line numbers, breaks on M2 changes | MED | MED | Parser uses heading-string anchors (`### Step 0.5:`, `### Direct prior art from memory`). Pre-mortem F3 mitigation. |
| M5 manual checks degrade after ship | HIGH | MED | Promote 8 deterministic checks to pytest in M5. Track 6 remaining checks via follow-on issue. |
| ProvisionalTier parser miscalculates silently | MED | LOW | Step 3 supplemental (AC-10) catches under-traversal. Tier upgrade triggers Phase 5 retroactively. |
| Auto-mode blast-radius false halts block automated /spec | LOW (post-mitigation) | MED | Threshold raised to 3 in auto-mode. Manual override path documented. |
| Concurrent writes to STEP-0.5-METRICS.md | LOW | LOW | Same risk profile as STEP-0-METRICS.md. Single-author repo; concurrent /spec invocations rare. Defer locking to follow-on. |

## Deferred (out of scope for this plan)

- Copilot CLI twin (`src/copilot-cli/skills/spec/SKILL.md`) update for Step 0.5
- ADR for the gate itself (file follow-on if needed after first 30 invocations)
- Promoting D6/D7/D9/D12/D13/D14 to pytest (tracked issue)
- File locking on STEP-0.5-METRICS.md
- Entity name normalization alias table

## Blockers

- None at plan time.

## Related

- Issue: #1951
- Parent Epic: #1952
- Sibling: #1926 (Step 0, prerequisite via REQ-006)
- Spec: `.agents/specs/requirements/REQ-008-spec-memory-first-gate.md`
- Design: `.agents/specs/design/DESIGN-008-spec-memory-first-gate.md`
- Tasks: `.agents/specs/tasks/TASK-008-spec-memory-first-gate.md`
- Interview: `.agents/specs/interviews/INTERVIEW-1951-spec-memory-first-gate.md`
- PR: (pending)
- ADR: (none required for Tier 2)
