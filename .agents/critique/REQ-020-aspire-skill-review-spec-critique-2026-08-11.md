# Critique: Aspire Skill Review Specification Suite

## Verdict
NEEDS_REVISION - Confidence: HIGH

## Summary
The spec suite (INTERVIEW, REQ-020, DESIGN-019, TASK-019 through TASK-023, CVA, pre-mortem, threat model, SLO) defines a commit-pinned Aspire skill review with targeted augmentations. The most critical concern is that REQ-020's Dependencies section lists `eval-knowledge-integration.py`, the wrong harness, contradicting every other artifact that correctly requires `eval-prompt-change.py`, and that acceptance criterion 11's "improvement" semantics conflict with the actual harness code where `has_improvement` is explicitly `NON_GATING_CRITERIA`.

## Scores by Axis
| Axis | Score | Notes |
|------|-------|-------|
| Completeness | 3/5 | Dependency error, improvement-semantics mismatch, wildcard paths unresolved |
| Alignment | 5/5 | Narrowest-wedge, demand-reality, and desperate-specificity checks all pass |
| Feasibility | 4/5 | SAML-blocked access is correctly handled; improvement gate needs reconciliation |
| Risk Coverage | 4/5 | Pre-mortem covers all Critical/High with Prevention/Detection/Response |
| Testability | 3/5 | AC 11 contradicts harness code; scenario file format not fully specified |
| Traceability | 4/5 | REQ→DESIGN→TASK chain intact; dependency list breaks the chain |

## Reasoning

1. **What breaks if this spec is wrong?** If an implementer reads REQ-020's Dependencies and uses `eval-knowledge-integration.py`, they measure skill-present-vs-absent rather than base-vs-candidate prompt comparison. That is exactly the failure mode R2 in the pre-mortem warns about. The spec's own risk mitigation is defeated by its own dependency list. If an implementer enforces AC 11's improvement requirement as a hard gate, they will conflict with `eval-prompt-change.py` line 87 which declares `has_improvement` as `NON_GATING_CRITERIA`. The implementer must either patch the harness (scope creep) or silently ignore the acceptance criterion.

2. **What assumptions contradict project constraints?** ADR-057 governs prompt behavioral evaluation. The harness (`eval-prompt-change.py` lines 85-87) explicitly places `has_improvement` in `NON_GATING_CRITERIA` with a comment: "the gate verdict never depends on them." AC 11 states improvement SHALL be required, a direct contradiction. The spec must either cite an ADR-057 amendment or defer improvement enforcement to human review rather than the harness gate.

3. **Strongest counterargument to chosen approach?** The spec could have treated improvement as a human-review annotation rather than a machine gate, which would align with ADR-057's existing non-gating classification. The spec chose to elevate it to a SHALL-level acceptance criterion without acknowledging the harness limitation, creating an unimplementable contract.

## Critical Findings

### 1. REQ-020 Dependencies list wrong eval script
**Where:** `REQ-020-aspire-skill-review.md` line ~168: `scripts/eval/eval-knowledge-integration.py`
**Impact:** Implementer following the dependency list uses the wrong harness, producing skill-present-vs-absent comparisons instead of base-vs-candidate prompt comparisons. This is the exact failure mode the pre-mortem (R2) was designed to prevent.
**Recommendation:** Replace `eval-knowledge-integration.py` with `eval-prompt-change.py` in the Dependencies section.

### 2. AC 11 improvement semantics conflict with harness code
**Where:** REQ-020 AC 11 ("SHALL require at least one improved scenario or a perfect base score") vs `eval-prompt-change.py` line 87 (`NON_GATING_CRITERIA = frozenset({"has_improvement"})`)
**Impact:** The acceptance criterion is unimplementable through the specified harness without modifying the harness itself, an out-of-scope change. An implementer who runs the harness and gets PASS will not have machine-enforced improvement evidence, making AC 11 a dead letter or forcing undocumented scope creep.
**Recommendation:** Either (a) add a TASK to amend the harness (with ADR-057 amendment), or (b) rewrite AC 11 to require human-verified improvement annotation in the eval report rather than a machine gate, and document the ADR-057 alignment.

### 3. Co-change checklist wildcards are unresolved in REQ-020
**Where:** REQ-020 lines ~146-147: `.claude/skills/*/SKILL.md` and `src/copilot-cli/skills/*/SKILL.md`
**Impact:** TASK-020 AC correctly requires wildcard resolution before TASK-021, but REQ-020 itself ships with wildcards. If TASK-020 is skipped or its output is lost, the requirement document contains unbuildable paths. The requirement should either be self-contained or explicitly mark these as "TASK-020 outputs, not yet resolved" with a status marker.
**Recommendation:** Add a status annotation to each wildcard entry (e.g., `[PENDING TASK-020]`) so the document's resolution state is machine-readable and auditable.

### 4. Scenario file creation is implicit, not explicit
**Where:** TASK-022 Files Affected lists `tests/evals/skills/aspire-skill-review-scenarios.json` as "Create" but no acceptance criterion specifies the scenario file's required content structure (positive, negative, edge scenarios for duplicate creation, product-specific copying, missing source identity).
**Impact:** The scenario file could be created with trivial or tautological scenarios that pass the harness but don't test the behaviors the spec claims to verify. The Implementation Notes mention what to detect but the AC doesn't require it.
**Recommendation:** Add an acceptance criterion to TASK-022 requiring at minimum one positive, one negative (duplicate-creation detection), and one edge (product-specific rejection) scenario with `expected_verdict` values that exercise the changed skill's judgment.

### 5. Redaction AC lacks verification method
**Where:** REQ-020 AC 13 ("SHALL redact tokens, SAML links, emails, and internal hostnames") and TASK-019/TASK-023.
**Impact:** No task specifies how redaction is verified. There is no grep-based check, no test, and no validation gate for sensitive data in durable artifacts. The threat model (T006, T007) maps to AC 13 but the mitigation is aspirational. No task owns the verification step.
**Recommendation:** Add a concrete verification step (e.g., regex scan of all created `.agents/analysis/` files for token/URL/email patterns) to TASK-023's acceptance criteria.

## Approval Conditions

1. Fix REQ-020 Dependencies: replace `eval-knowledge-integration.py` with `eval-prompt-change.py`.
2. Reconcile AC 11 with `eval-prompt-change.py`'s `NON_GATING_CRITERIA` declaration, either by scoping an ADR-057 amendment or rewriting AC 11 as a human-review gate.
3. Add status markers to co-change wildcards.

## Binary Check Results

| Check | Result | Evidence |
|-------|--------|----------|
| 9a Demand Reality | PASS | INTERVIEW Q1: "MattKot, myself, and Eduardo" |
| 9b Desperate Specificity | PASS | INTERVIEW Q3 and SLO Owner: "ConfigGen team" |
| 9c Narrowest Wedge | PASS | Q4 Wedge Revision documents "commit-pinned matrix plus targeted augmentations" and excludes reusable framework; all ACs trace to matrix+augment, not framework |
| 9d Prior Art | PASS | `## Prior Art / Constraints` exists in INTERVIEW with Chesterton's Fence search, SkillForge provenance, coverage notes, and justified absence-of-evidence statement |
| 9e Tier 3 | N/A | As specified |
| Gap: correct eval script | FAIL | REQ-020 Dependencies (line ~168) lists `eval-knowledge-integration.py`; all other artifacts correctly use `eval-prompt-change.py` |
| Gap: improvement semantics | FAIL | AC 11 requires improvement; harness line 87 declares `has_improvement` non-gating |
| Gap: scenario explicit creation | PARTIAL | TASK-022 creates the file but ACs don't specify required scenario categories |
| Gap: redaction AC | PARTIAL | AC 13 exists but no task owns verification |
| Gap: co-change wildcards | PASS (deferred) | TASK-020 AC requires resolution before TASK-021; REQ-020 lacks status marker |
| Pre-mortem coverage | PASS | All 3 Critical (R1-R3) and 4 High (R4-R7) risks have Prevention, Detection, and Response |

## Recommendation

Fix the REQ-020 dependency list (Finding 1) and reconcile AC 11 with `eval-prompt-change.py`'s non-gating `has_improvement` (Finding 2) before implementation begins.
