# PLAN: Local Guardrails Implementation

**Document ID**: PLAN-LOCAL-GUARDRAILS
**Status**: CONSOLIDATED into Issue #230
**Created**: 2025-12-22
**Spec Reference**: [SPEC-local-guardrails.md](../specs/SPEC-local-guardrails.md)
**Consolidation Date**: 2025-12-22
**Consolidation Target**: [Issue #230](https://github.com/rjmurillo/ai-agents/issues/230)

> **Note**: This plan has been consolidated into Issue #230 "[P1] Implement Technical Guardrails for Autonomous Agent Execution" following 14-agent review. See Session 67 for synthesis details.

## Overview

This plan implements local validation guardrails to prevent AI Quality Gate violations before PR creation, reducing premium GitHub Copilot request costs.

## Deliverables

| # | Deliverable | Type | Location |
|---|-------------|------|----------|
| 1 | `Validate-PrePR.ps1` | New Script | `scripts/` |
| 2 | `Detect-TestCoverageGaps.ps1` | New Script | `scripts/` |
| 3 | `Validate-PRDescription.ps1` | New Script | `.claude/skills/github/scripts/pr/` |
| 4 | `New-ValidatedPR.ps1` | New Script | `.claude/skills/github/scripts/pr/` |
| 5 | `.test-coverage-ignore` | Config | Repository root |
| 6 | Pre-commit hook update | Modification | `.githooks/pre-commit` |
| 7 | Pester tests | Tests | `scripts/tests/`, `.claude/skills/github/tests/` |

## Implementation Phases

### Phase 1: Foundation (Documentation)

**Status**: COMPLETE

**Deliverables**:
- [x] SPEC-local-guardrails.md
- [x] PLAN-local-guardrails.md (this document)

**Acceptance Criteria**:
- [x] Spec document contains RFC 2119 requirements
- [x] Plan document contains phased implementation roadmap

### Phase 2: Pre-PR Session Protocol Validation

**Status**: PENDING

**Objective**: Create BLOCKING pre-PR gate for Session Protocol compliance.

**Tasks**:

| Task | Description | File |
|------|-------------|------|
| 2.1 | Create Validate-PrePR.ps1 | `scripts/Validate-PrePR.ps1` |
| 2.2 | Create Pester tests | `scripts/tests/Validate-PrePR.Tests.ps1` |
| 2.3 | Document usage | `scripts/README.md` |

**Script Design**:

```powershell
# Validate-PrePR.ps1
param(
    [string]$Branch,
    [string]$BaseBranch = "main",
    [string]$SessionLogPath,
    [switch]$Fix,
    [switch]$CI
)

# 1. Auto-detect session log if not provided
# 2. Call Validate-SessionEnd.ps1 for comprehensive checks
# 3. Verify git status is clean
# 4. Verify commits exist for PR
# 5. Output pedagogical error messages on failure
```

**Exit Codes**:
- 0: PASS - PR creation can proceed
- 1: FAIL - Session Protocol violations
- 2: ERROR - Script/environment issue

**Dependencies**: Validate-SessionEnd.ps1

### Phase 3: PR Description Validation

**Status**: PENDING

**Objective**: Detect PR description vs diff mismatches before PR creation.

**Tasks**:

| Task | Description | File |
|------|-------------|------|
| 3.1 | Create Validate-PRDescription.ps1 | `.claude/skills/github/scripts/pr/Validate-PRDescription.ps1` |
| 3.2 | Create Pester tests | `.claude/skills/github/tests/Validate-PRDescription.Tests.ps1` |
| 3.3 | Update skill documentation | `.claude/skills/github/skill.md` |

**Script Design**:

```powershell
# Validate-PRDescription.ps1
param(
    [Parameter(Mandatory)][string]$Title,
    [string]$Body,
    [string]$BodyFile,
    [string]$BaseBranch = "main",
    [switch]$Strict
)

# 1. Get changed files from git diff
# 2. Parse file references from PR body
# 3. Compare claimed files to actual diff
# 4. Check for major changes not mentioned
# 5. Output verdict with recommendations
```

**Validation Checks**:

| Check | Severity | Description |
|-------|----------|-------------|
| C1 | CRITICAL | Files mentioned but not in diff |
| C2 | WARNING | Action verbs don't match diff operations |
| C3 | WARNING | Scope mismatch (description vs diff size) |
| C4 | WARNING | Major changes not mentioned |

### Phase 4: Integration (Validated PR Wrapper)

**Status**: PENDING

**Objective**: Integrate validations into `gh pr create` workflow.

**Tasks**:

| Task | Description | File |
|------|-------------|------|
| 4.1 | Create New-ValidatedPR.ps1 | `.claude/skills/github/scripts/pr/New-ValidatedPR.ps1` |
| 4.2 | Update skill documentation | `.claude/skills/github/skill.md` |

**Script Design**:

```powershell
# New-ValidatedPR.ps1
param(
    [Parameter(Mandatory)][string]$Title,
    [string]$Body,
    [string]$BodyFile,
    [string]$Base = "main",
    [switch]$Draft,
    [switch]$Force
)

# 1. Run Validate-PrePR.ps1 (unless -Force)
# 2. Run Validate-PRDescription.ps1 (unless -Force)
# 3. If both pass, call gh pr create
# 4. If -Force, log bypass and proceed
```

**Escape Hatch**:

When `-Force` is used:
1. Log bypass to session log
2. Require reason in PR body
3. Proceed with PR creation

### Phase 5: Test Coverage Detection

**Status**: PENDING

**Objective**: Warn about missing test files before commit.

**Tasks**:

| Task | Description | File |
|------|-------------|------|
| 5.1 | Create Detect-TestCoverageGaps.ps1 | `scripts/Detect-TestCoverageGaps.ps1` |
| 5.2 | Create ignore file | `.test-coverage-ignore` |
| 5.3 | Update pre-commit hook | `.githooks/pre-commit` |
| 5.4 | Create Pester tests | `scripts/tests/Detect-TestCoverageGaps.Tests.ps1` |

**Detection Rules**:

| Source Pattern | Expected Test Pattern |
|---------------|----------------------|
| `scripts/{name}.ps1` | `scripts/tests/{name}.Tests.ps1` |
| `build/scripts/{name}.ps1` | `build/scripts/tests/{name}.Tests.ps1` |
| `.github/scripts/{name}.ps1` | `.github/scripts/{name}.Tests.ps1` |
| `.claude/skills/{skill}/scripts/**/{name}.ps1` | `.claude/skills/{skill}/tests/{name}.Tests.ps1` |

**Pre-commit Integration**:

```bash
# Add to .githooks/pre-commit after ADR-005 section

#
# Test Coverage Detection (Non-blocking WARNING)
#
STAGED_PS1_FILES=$(echo "$STAGED_FILES" | grep -E '\.ps1$' | grep -v '\.Tests\.ps1$' || true)

if [ -n "$STAGED_PS1_FILES" ]; then
    echo_info "Checking test coverage..."
    # Call detection script
fi
```

### Phase 6: Documentation Update

**Status**: PENDING

**Objective**: Document new workflow in project documentation.

**Tasks**:

| Task | Description | File |
|------|-------------|------|
| 6.1 | Update AGENTS.md | `AGENTS.md` |
| 6.2 | Create memory | `.serena/memories/local-guardrails-patterns.md` |

## Dependency Graph

```
Phase 1 (Foundation)
    │
    ├── Phase 2 (Session Protocol)
    │       │
    │       └──┐
    │          │
    ├── Phase 3 (PR Description)
    │       │
    │       └──┐
    │          │
    │          v
    │     Phase 4 (Integration)
    │          │
    │          v
    │     Phase 6 (Documentation)
    │          │
    └── Phase 5 (Test Coverage) ──┘
```

## Test Strategy

### Unit Tests (Pester)

Each script will have corresponding Pester tests:

| Script | Test File |
|--------|-----------|
| Validate-PrePR.ps1 | Validate-PrePR.Tests.ps1 |
| Validate-PRDescription.ps1 | Validate-PRDescription.Tests.ps1 |
| Detect-TestCoverageGaps.ps1 | Detect-TestCoverageGaps.Tests.ps1 |
| New-ValidatedPR.ps1 | New-ValidatedPR.Tests.ps1 |

### Test Categories

| Category | Description |
|----------|-------------|
| PASS scenarios | Valid input, expected success |
| FAIL scenarios | Invalid input, expected failure |
| Edge cases | Empty files, missing dependencies |
| Integration | Scripts calling each other |

## Rollout Plan

### Step 1: Deploy Scripts (Non-blocking)

1. Deploy all scripts to repository
2. Document in AGENTS.md
3. Announce to team

### Step 2: Monitor Usage

1. Track bypass rate via session logs
2. Collect false positive reports
3. Tune detection patterns

### Step 3: Enforce (After n=10 PRs)

1. Review bypass reasons
2. Address false positives
3. Consider making test coverage BLOCKING

## Risk Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| False positives block valid PRs | High | Use WARNING for test coverage, provide escape hatch |
| Performance degradation | Medium | Target <5s validation time, optimize git operations |
| Script failures block work | High | Fail-safe design: errors = proceed with warning |
| Adoption resistance | Medium | Pedagogical error messages, clear documentation |

## Success Metrics

| Metric | Before | Target | Measurement |
|--------|--------|--------|-------------|
| Session Protocol CRITICAL_FAIL rate | 60% | <5% | CI results |
| AI Quality Gate cost per violation | 6 requests | 0 | Copilot usage |
| Analyst CRITICAL_FAIL rate | 10% | <2% | CI results |
| QA WARN rate | 40% | <15% | CI results |

## References

- [SPEC-local-guardrails.md](../specs/SPEC-local-guardrails.md)
- [SESSION-PROTOCOL.md](../SESSION-PROTOCOL.md)
- [ADR-004: Pre-commit Hooks](../architecture/ADR-004-pre-commit-hooks.md)
- [ADR-005: PowerShell-Only Scripting](../architecture/ADR-005-powershell-only-scripting.md)
