# Execution Plan: review-axes-convergence

## Metadata

| Field | Value |
|-------|-------|
| **Status** | In Progress |
| **Created** | 2026-05-10 |
| **Owner** | implementer |
| **Complexity** | Medium (Tier 2) |
| **Branch** | feat/issue-1934-review-axes-convergence |
| **Commit Budget** | 14 / 20 planned (see commit map in Progress Log) |

## Objectives

### M1: Foundation (critical path, start immediately)

Ordering: M1-01, M1-02, M1-03, M1-04 all unblocked (run in parallel). M1-05 requires M1-04. M1-06 requires M1-01 + M1-02 + M1-03.

- [ ] M1-01: Create `tests/lib/conftest.py` schema-validation fixture (`validate_axis_schema`) [XS] — commit C1
- [ ] M1-02: Author `analyst.md` + `architect.md` under `.claude/review-axes/` [S] — commit C2 (parallel with M1-01, M1-03, M1-04)
- [ ] M1-03: Author `qa.md` + `security.md` + `devops.md` + `roadmap.md` under `.claude/review-axes/` [S] — commit C3 (parallel with M1-01, M1-02, M1-04)
- [ ] M1-04: Implement `.claude/lib/ai_review_common.py` (`merge_verdicts`, `get_verdict_emoji`, `extract_verdict`) [M] — commit C4 (parallel with M1-01, M1-02, M1-03)
- [ ] M1-05: Write `tests/lib/test_ai_review_common.py` (100% branch coverage, all verdict combinations + UNKNOWN truth table) [S] — commit C5 (requires M1-04)
- [ ] M1-06: Write `tests/lib/test_axis_schema.py` (parametrized over all 6 axis files, exact section-title match) [XS] — commit C6 (requires M1-01 + M1-02 + M1-03)

### M2: Generation (starts after M1-02 + M1-03 commit; parallel with M3)

Ordering: M2-01 requires M1-02 + M1-03 (axis files needed for generator). M2-02 + M2-03 + M2-04 require M2-01. M2-05 requires M2-03.

- [ ] M2-01: Implement `build/scripts/generate_pr_quality_prompts.py` (idempotent, atomic write, `--dry-run`, static CI header literal, LF-only output) [M] — commit C7
- [ ] M2-02: Write `tests/build_scripts/test_generate_pr_quality_prompts.py` [S] — commit C8 (parallel with M2-03 + M2-04)
- [ ] M2-03: Add drift step to `.githooks/pre-push` (HEAD-commit comparison, unified diff on divergence, `command -v python3` guard) [S] — commit C9 (parallel with M2-02 + M2-04)
- [ ] M2-04: Add `drift-check` job to `.github/workflows/ai-pr-quality-gate.yml` (SHA-pinned actions, error annotation, job summary) [S] — commit C10 (parallel with M2-02 + M2-03)
- [ ] M2-05: Write `tests/hooks/test_drift_check.py` (positive + negative paths) [XS] — commit C11 (requires M2-03)

### M3: Integration (starts after M1-04 commit; parallel with M2)

Ordering: M3-01 requires M1-04 (ai_review_common.py must exist to be cited). M3-02 requires M1-04. M3-01 and M3-02 run in parallel.

- [ ] M3-01: Rewrite `.claude/commands/review.md` (6 canonical axes from `.claude/review-axes/`, 3 skill chains, merge_verdicts from ai_review_common.py, UNKNOWN handling, findings table) [M] — commit C12
- [ ] M3-02: Update `.claude/commands/pr-quality/all.md` (cite `ai_review_common.py`, remove `AIReviewCommon.psm1`) [XS] — commit C13 (parallel with M3-01)

### M4: Validation (terminal; requires all M1+M2+M3 commits merged)

Ordering: M4-01 requires M1-04 + M1-02 + M1-03 + M3-01. M4-02 requires M3-01 (design stabilized). M4-01 and M4-02 run in parallel. **M4-02 MUST land before final PR merge** (spec-coverage gate checks issue body).

- [ ] M4-01: Write `tests/integration/test_vendored_install.py` (`.claude/` subtree in `tmp_path`; `import ai_review_common` from copy; all 6 axis files present + schema-valid; no `.agents/` hard-coded paths) [S] — commit C14
- [ ] M4-02: Sync GitHub issue bodies #1933 + #1934 via `gh issue edit` (remove "7 axes", cite `ai_review_common.py`, reference 6+3=9 approach) [XS] — no repo commit (gh CLI side effect)

## Decision Log

| Date | Decision | Rationale | Alternatives Considered |
|------|----------|-----------|------------------------|
| 2026-05-10 | Scoped to 6 axes matching current CI | CI runs security/qa/analyst/architect/devops/roadmap; session-protocol is orphaned | 7 axes (add session-protocol): deferred, value unproven |
| 2026-05-10 | ai_review_common.py in .claude/lib/ (Python) | ADR-042 Python migration; must ship in vendored install | PowerShell psm1: retired in PR #1066; prose-only: drifts |
| 2026-05-10 | UNKNOWN semantics: downgrades PASS only | UNKNOWN from skill crash: real finding still surfaced via WARN/CRITICAL_FAIL; only PASS needs escalation | UNKNOWN > WARN: confusing; count-threshold: complex |
| 2026-05-10 | 6/3 family split as prose discriminator in /review | CVA: no new abstraction warranted; 10th axis heterogeneous case deferred (YAGNI) | Abstract Factory: premature; stub files in extras/: unnecessary indirection |
| 2026-05-10 | Canonical seed = translation not verbatim copy | CI prompts have no frontmatter, no Output Schema; must add both during seed | Verbatim copy: AC1 rejects because schema sections missing in CI source |
| 2026-05-10 | CI header in generated files is a static literal | Any time-varying token (timestamp, SHA) breaks idempotency | Generated timestamp: breaks idempotency; no header: loses "do not edit" signal |
| 2026-05-10 | Drift comparison target = HEAD commit not working tree | Author may have regenerated but not staged; hook must catch committed divergence | Working tree comparison: misses unstaged-but-pushed state |
| 2026-05-10 | M2 and M3 run in parallel after M1 | M3 needs only .claude/lib/ (M1); M2 needs .claude/review-axes/ (M1). No M2-M3 dependency | Serial M2 then M3: adds ~4-6 days elapsed; no benefit |

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Spec-coverage gate fails on stale issue body (#1933/#1934 say "7 axes") | MED | MED | M4-02 mandatory before final merge; exit criteria verify `gh issue view` output |
| Generator idempotency breaks if CI prompts edited upstream before M2 ships | MED | HIGH | One-time seed at M1; after M2 merges, CI prompts only change via generator. Drift check blocks direct edits. |
| Generator atomicity: `os.replace()` semantics differ on Windows | LOW | MED | Confirm `os.replace()` used; document Linux-only or add CRLF guard |
| /review prose (markdown) untestable by pytest | MED | MED | Merge logic in ai_review_common.py (100% covered). Structural grep + M4 vendored import test covers Python surface. Accept prose risk. |
| Schema incompatibility between M1-02 and M1-03 authors | MED | MED | M1-01 schema fixture defines exact section-title strings FIRST; M1-02/M1-03 derive from fixture. M1-06 validates both. |
| Bot reviewers thread on em-dashes in axis file prose | MED | LOW | Run dash guard before each push; fix-markdown-fences on axis files |
| Plugin manifest enumeration requires explicit .claude/review-axes/ listing | LOW | LOW | RESOLVED: Claude Code 2.1.122 rejects explicit discovery; ships by convention |
| Commit budget exceeded (18 tasks but 14 commits budgeted) | LOW | MED | Commit map (C1-C14) folds XS tasks into same-commit as adjacent XS. M4-02 is gh CLI, no repo commit. |

## Progress Log

| Date | Update | Agent |
|------|--------|-------|
| 2026-05-10 | Created plan. /spec completed (REQ-008/DESIGN-008/TASK-008). /plan milestones + decomposition done. Branch `feat/issue-1934-review-axes-convergence` created. | implementer |
| 2026-05-10 | Revised plan after critic review: corrected parallelism (M1-06 depends on M1-02+M1-03; M1-05 depends on M1-04; M2 starts only after M1-02+M1-03 committed). Added commit map C1-C14 (14 commits, 18 tasks, 4 XS fold). Added task sizing [XS/S/M]. Updated risk register with analyst pre-mortem findings. | implementer |
| 2026-05-10 | M0 PIVOT: discovered scripts/ai_review_common/ Python package already exists with merge_verdicts and get_verdict_emoji. AIReviewCommon.psm1 was retired in PR #1066/#1169. Existing sync_plugin_lib.py pattern (used for github_core, hook_utilities) added .claude/lib/ai_review_common/ as synced copy. 24 importers untouched. New M0 milestone added (1 commit). | implementer |
| 2026-05-10 | M1+M2+M3 substantially done (12 commits). M1: spec docs, sync infra, UNKNOWN handling+extract_verdict, 6 axes (2 commits), schema fixture+tests. M2: generator+29 tests, CI prompt regen (2 commits), pre-push drift hook. M3: /review rewrite, pr-quality/all.md citation fix. 534 tests pass. No em/en-dashes. | implementer |
| | **Commits 1-12**: d86cb99e (spec), 9f52354f (sync), d19e8e79 (UNKNOWN+extract_verdict), 9e7f0bda + 234d3c9f (axes), ba5a95f4 (schema tests), 7831d55c (generator+tests), 403b0a7b + b28371f4 (regen prompts), d74221a6 (pre-push hook), 6d884a17 (pr-quality/all.md), cb438de2 (/review rewrite). | |
| | **Remaining**: M2-04 CI drift-check job, M2-05 hook tests, M4-01 vendored test, M4-02 gh issue sync, exit gates. | |

## Blockers

- None. M1 tasks unblocked; implementer can start TASK-M1-01 through M1-04 in parallel.

## Acceptance Criteria Summary (from REQ-008)

| AC | Gate | Milestone |
|----|------|-----------|
| AC1: 6 canonical axis files with schema | pytest M1-06 | M1 |
| AC2: Generator idempotent, atomic write | pytest M2-02 | M2 |
| AC3: Drift blocked pre-push + CI | pytest M2-05, CI drift-check job | M2 |
| AC4: /review 9-axis merge | Structural grep M3-01 | M3 |
| AC5: ai_review_common.py 100% coverage | pytest M1-05 --cov-fail-under=100 | M1 |
| AC6: Vendored-install works (.claude/ only) | pytest M4-01 | M4 |
| AC7: pr-quality/all.md cites ai_review_common.py | grep M3-02 | M3 |
| AC8: Issue bodies updated (no "7 axes") | gh issue view M4-02 | M4 |

## Related

- Issue: #1934 (child)
- Epic: #1933
- Spec: `.agents/specs/requirements/REQ-008-review-axes-convergence.md`
- Design: `.agents/specs/design/DESIGN-008-review-axes-convergence.md`
- Tasks: `.agents/specs/tasks/TASK-008-review-axes-convergence.md`
- Interview: `.agents/specs/interviews/INTERVIEW-review-axes-convergence.md`
- Retro (source incident): `.agents/retrospective/2026-05-05-pr-1887-iteration-paradox.md`
- PR: (pending, opens when M1 complete)
