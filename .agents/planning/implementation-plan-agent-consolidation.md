# Implementation Plan: 2-Variant Agent Consolidation

**Epic**: `epic-agent-consolidation.md`
**PRD**: `prd-agent-consolidation.md`
**Status**: **Approved with Conditions**

---

## Review Summary

| Agent | Status | Notes |
|-------|--------|-------|
| Architect | **Approved** | Design sound, follows existing patterns |
| DevOps | **Approved** | Minor: Add PowerShell-Yaml install step in CI |
| Security | **Approved** | Low risk, requires path validation |
| QA | **Needs Changes** | Test specifications required |

---

## Decision: Proceed with QA Conditions

The QA concerns are **implementation-time concerns** that do not require plan changes. They will be addressed during task execution:

### QA Conditions (Must Address During Implementation)

1. **TASK-006**: Create explicit `build/tests/Generate-Agents.Tests.ps1` with test cases
2. **TASK-012**: Increase effort from 30 min to 1.5 hours for PoC validation
3. **PRD Amendment**: Specify byte-comparison methodology (line endings, encoding)
4. **Add task**: Regression tests for agent functionality post-migration

---

## Specialist Review Details

### Architect Review

**Verdict**: Approved

**Strengths**:
- Build-time generation is appropriate for this problem
- `templates/` directory structure follows logical separation
- PowerShell aligns with existing `build/scripts/` patterns
- Platform config files enable future extensibility

**Recommendations (Non-Blocking)**:
- Add `# AUTO-GENERATED` header comment to generated files
- Consider `--fix` mode for local development

**Document**: `.agents/architecture/2-variant-consolidation-review.md`

---

### DevOps Review

**Verdict**: Approved

**Strengths**:
- Workflow design consistent with existing `pester-tests.yml`
- Path filtering appropriately scoped
- No secrets required

**Recommendations**:
- Add `workflow_dispatch` for manual triggering
- Add PowerShell-Yaml module installation step in CI
- Use `ubuntu-latest` for drift detection (lighter weight)
- Add issue deduplication for drift alerts

---

### Security Review

**Verdict**: Approved (Low Risk)

| Category | Risk Level |
|----------|------------|
| Build Script Security | Low |
| CI Workflow Security | Low |
| Path Traversal | Low |
| Supply Chain | Low |
| Sensitive Data | None |

**Required Conditions**:
1. Validate output paths remain within repository root
2. Use minimal GitHub Actions permissions

**Recommendations**:
- Consider JSON config instead of YAML to avoid external dependency
- Add `# AUTO-GENERATED` header to prevent accidental edits

---

### QA Review

**Verdict**: Needs Changes

**Gaps Identified**:

| Gap | Priority | Resolution |
|-----|----------|------------|
| No test file specification in TASK-006 | High | Add during implementation |
| Byte-comparison methodology undefined | High | Document in PRD amendment |
| QA effort underestimated (30 min) | High | Increase to 1.5 hours |
| No regression tests | Medium | Add test cases |
| Drift detection test cases missing | Medium | Add during Phase 2 |

**Document**: `.agents/qa/001-agent-consolidation-test-strategy-review.md`

---

## Final Approval

**Consensus Reached**: Yes (with conditions)

**Approved By**:
- Architect Agent
- DevOps Agent
- Security Agent
- QA Agent (conditional)

**Date**: 2025-12-15

---

## Work Breakdown

Reference: `.agents/planning/tasks-agent-consolidation.md`

### Phase 1: 2-Variant Consolidation (8-10 hours)

| Task ID | Task | Agent | Priority |
|---------|------|-------|----------|
| TASK-001 | Create templates directory structure | implementer | P0 |
| TASK-002 | Create config directory structure | implementer | P0 |
| TASK-003 | Create vscode.yaml config | implementer | P0 |
| TASK-004 | Create copilot-cli.yaml config | implementer | P0 |
| TASK-005 | Build script: Parse shared source | implementer | P0 |
| TASK-006 | Build script: Frontmatter transform + tests | implementer | P0 |
| TASK-007 | Build script: Output generation | implementer | P0 |
| TASK-008 | Build script: CI integration | implementer | P0 |
| TASK-009 | Migrate: analyst.shared.md (PoC) | implementer | P0 |
| TASK-010 | Migrate: implementer.shared.md (PoC) | implementer | P0 |
| TASK-011 | Migrate: orchestrator.shared.md (PoC) | implementer | P0 |
| TASK-012 | PoC Validation (QA) | qa | P0 |
| TASK-013 | Migrate: Remaining 15 agents | implementer | P1 |
| TASK-014 | CI validation workflow | devops | P1 |
| TASK-015 | Update CONTRIBUTING.md | explainer | P2 |

### Phase 2: Diff-Linting CI (4-6 hours)

| Task ID | Task | Agent | Priority |
|---------|------|-------|----------|
| TASK-016 | Drift detection script: Core logic | implementer | P1 |
| TASK-017 | Drift detection script: Exclusion patterns | implementer | P1 |
| TASK-018 | Drift detection script: Tests | implementer | P1 |
| TASK-019 | Weekly drift detection workflow | devops | P1 |
| TASK-020 | Drift alert issue template | devops | P2 |
| TASK-021 | Update templates README | explainer | P2 |

---

## Quality Gates

1. **PoC Validation** (TASK-012): 3 agents generate byte-identical outputs
2. **Full Migration** (TASK-013): All 18 agents validated
3. **CI Integration** (TASK-014): Manual edits blocked by CI
4. **Drift Detection** (TASK-018): Known differences detected correctly

---

## Success Metrics (90-Day Review)

| Metric | Target | Measurement |
|--------|--------|-------------|
| File count | 36 (down from 54) | `find templates/ src/ -name "*.md" | wc -l` |
| Build time | < 5 seconds | CI job duration |
| CI validation | 100% blocking | Failed PRs with manual edits |
| Drift alerts | Weekly reports | Issue count with `drift-detected` label |

---

## Next Steps

1. **implementer**: Begin TASK-001 (directory structure)
2. **implementer**: Create `Generate-Agents.Tests.ps1` (per QA requirement)
3. **explainer**: Amend PRD with byte-comparison methodology

---

*Generated by Orchestrator Agent - 2025-12-15*
