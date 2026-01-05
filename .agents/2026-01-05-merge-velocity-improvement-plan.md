## Merge Velocity Analysis & Improvement Plan
**Date:** 2026-01-05
**Scope:**
-   **PRs:** Created since 2025-12-27 (N=193 analyzed)
-   **Issues:** Created/Closed since 2025-12-20 (N=200 analyzed)

### Top 10 Bottlenecks by Category

#### 1. Time to PR Ready (First Commit → PR Creation)
Impact: Large "invisible work" phases where code is written but not visible.
1. **#458 (49.29h)**: `fix(security): address GraphQL injection` (Complexity hidden in local dev)
2. **#453 (46.27h)**: `fix(pr-maintenance): improve bot classification`
3. **#771 (15.93h)**: `docs(security): add CWE-699 and OWASP agentic security research`
4. **#797 (11.67h)**: `feat: Create VM bootstrap script`
5. **#704 (11.40h)**: `docs(analysis): issue triage identifying duplicates`
6. **#719 (10.67h)**: `fix(tests): correct comment about regex parsing`
7. **#718 (10.67h)**: `fix(tests): clarify non-numeric ID test behavior`
8. **#717 (10.66h)**: `fix(traceability): support alphanumeric ID suffixes`
9. **#561 (9.42h)**: `fix(validation): detect docs-only from staged files`
10. **#560 (9.37h)**: `docs(analysis): identify GitHub skill PowerShell reuse`

#### 2. Review Time (PR Creation → Last Approval)
Impact: Major delays in Getting to Yes. Correlates with complex features and validation script bugs.
1. **#460 (38.23h)**: `fix(ai-review): simplify retry count`
2. **#733 (33.06h)**: `fix(docs): historical reference protocol compliance`
3. **#465 (31.13h)**: `fix(ci): Surface AI Quality Gate failures`
4. **#532 (31.03h)**: `refactor(workflows): standardize output naming`
5. **#531 (29.55h)**: `refactor(workflow): convert skip-tests XML generation`
6. **#735 (29.48h)**: `feat(memory): Phase 2A Memory System`
7. **#538 (27.99h)**: `test(copilot-detection): add integration tests`
8. **#543 (27.24h)**: `feat(copilot-detection): implement actual file comparison`
9. **#526 (26.64h)**: `feat(ci): add PSScriptAnalyzer validation`
10. **#530 (26.64h)**: `feat(github): add review thread management scripts`

#### 3. Merge Time (PR Creation → Merge)
Impact: Almost identical to Review Time, indicating efficient merge-after-approval but slow approval.
1. **#460 (38.92h)**: `fix(ai-review): simplify retry count`
2. **#733 (33.06h)**: `fix(docs): historical reference protocol compliance`
3. **#465 (31.51h)**: `fix(ci): Surface AI Quality Gate failures`
4. **#531 (29.55h)**: `refactor(workflow): convert skip-tests XML generation`
5. **#735 (29.33h)**: `feat(memory): Phase 2A Memory System`
6. **#538 (27.99h)**: `test(copilot-detection): add integration tests`
7. **#543 (27.24h)**: `feat(copilot-detection): implement actual file comparison`
8. **#526 (26.64h)**: `feat(ci): add PSScriptAnalyzer validation`
9. **#530 (26.64h)**: `feat(github): add review thread management scripts`
10. **#557 (26.02h)**: `docs(architecture): add ADR-035`

---

### Remediation Plan

#### 1. Stabilize Validation Tooling (Reduce Issue Churn)
**Observation**: High-churn issues (#784, #796, #778, #781) and delayed PRs (#465, #531) are frequently caused by bugs in the validation scripts themselves (Validate-Session.ps1, Compare-DiffContent).
**Plan**:
- Treat `scripts/` as production code with higher test coverage requirements.
- **Immediate Action**: Fix the regex/pipe parsing issues in `Validate-Session.ps1` (Issue #784) and memory evidence bugs (#778).
- **Target**: Zero "tooling bug" blockers in the next sprint.

#### 2. Atomic Work & "WIP" PRs
**Observation**: PRs #458 and #453 had >45h lead time before PR ready, suggesting massive local changes or "stacked" work.
**Plan**:
- **Draft PR Policy**: Open Draft PRs immediately upon starting work (Time to Ready -> 0).
- **Benefits**: Early CI feedback, visibility for `orchestrator`, prevents "big bang" integration.
- **Target**: Reduce max "Time to Ready" to < 4h.

#### 3. Parallelize Review & Implementation (Issue #168)
**Observation**: Review times average ~30h for significant changes.
**Plan**:
- Implement **Parallel Agent Execution** (as planned in #168).
- Allow `QA` agent to generate test plans *while* `Implementer` is coding.
- Allow `Critic` to review specs *before* implementation starts, reducing post-PR rework.
- **Target**: Cut Review Time by 50% by front-loading feedback.

#### 4. Decouple Documentation from Code
**Observation**: Docs PRs (#733, #771) take 33h+ to review/merge, often blocking dependent work.
**Plan**:
- **Async Docs**: Allow merging feature code with "Docs Pending" tag if strictly internal.
- **Separate Lifecycle**: Process docs updates in a separate, faster track (e.g., auto-merge for non-normative changes).
- **Target**: Merge docs PRs in < 4h.

#### 5. Automated Noise Reduction (Bot Management)
**Observation**: "Review Time" includes dealing with bot noise.
**Plan**:
- Enhance `pr-comment-responder` to auto-dismiss low-confidence bot comments.
- **Target**: Reduce human cognitive load during review.
