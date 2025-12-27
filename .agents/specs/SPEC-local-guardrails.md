# SPEC: Local Guardrails for AI Quality Gate Violation Prevention

**Document ID**: SPEC-LOCAL-GUARDRAILS
**Status**: CONSOLIDATED into Issue #230
**Created**: 2025-12-22
**Author**: Claude Code (orchestrator + 3 Plan agents)
**Consolidation Date**: 2025-12-22
**Consolidation Target**: [Issue #230](https://github.com/rjmurillo/ai-agents/issues/230)

> **Note**: This spec has been consolidated into Issue #230 "[P1] Implement Technical Guardrails for Autonomous Agent Execution" following 14-agent review that identified 70-80% overlap. Unique elements (test coverage detection, PR description validation) have been added as sub-tasks to Issue #230.

## Executive Summary

This specification defines local validation guardrails to prevent AI Quality Gate violations before PR creation. Each AI Quality Gate run consumes 6 premium GitHub Copilot requests. Analysis of 8 PRs shows 60% of CRITICAL_FAIL verdicts are preventable with local validation.

## Problem Statement

### Current State

The AI Quality Gate workflow (`.github/workflows/ai-pr-quality-gate.yml`) runs 6 AI agents on every PR:
- Security Agent
- QA Agent
- Analyst Agent
- Architect Agent
- DevOps Agent
- Roadmap Agent

Each agent invocation costs 1 premium GitHub Copilot request.

### Impact

When violations are caught post-hoc:
- **Cost**: 6 premium requests wasted per violating PR
- **Delay**: Fix-commit-push-wait cycle adds friction
- **Noise**: Multiple CI comments clutter PR discussion

### Evidence

Analysis of 8 PRs with AI Quality Gate Review comments:

| PR | Quality Gate | Session Protocol | Key Violations |
|----|-------------|------------------|----------------|
| #233 | WARN | - | QA: Test coverage warning |
| #232 | WARN | - | Security, QA, Analyst all WARN |
| #206 | PASS | - | Clean |
| #199 | CRITICAL_FAIL | - | Analyst: PR description vs diff mismatch |
| #194 | CRITICAL_FAIL | CRITICAL_FAIL (7 MUST) | QA + Session End violations |
| #143 | WARN | CRITICAL_FAIL (3 MUST) | QA, Architect + Session End |
| #141 | PASS | PASS | Clean |
| #202 | CRITICAL_FAIL | CRITICAL_FAIL (7 MUST) | QA + Session End violations |

### Violation Categories

| Category | Frequency | Preventable Locally |
|----------|-----------|---------------------|
| Session Protocol MUST failures | 60% | YES |
| QA test coverage gaps | 40% | PARTIAL (file presence) |
| Analyst PR description mismatch | 10% | YES |

## Requirements

This section uses RFC 2119 keywords: MUST, SHOULD, MAY.

### Functional Requirements

#### FR-1: Pre-PR Session Protocol Validation

The system MUST provide a validation script that checks Session Protocol compliance before PR creation.

**Acceptance Criteria**:
- [ ] Script exits 0 on PASS, 1 on FAIL, 2 on ERROR
- [ ] Script validates all MUST requirements from SESSION-PROTOCOL.md
- [ ] Script auto-detects session log for current branch/date
- [ ] Script provides pedagogical error messages with fix instructions
- [ ] Script integrates with existing Validate-SessionEnd.ps1

#### FR-2: PR Description Validation

The system MUST provide a validation script that detects PR description vs diff mismatches.

**Acceptance Criteria**:
- [ ] Script compares claimed files in description to actual diff
- [ ] Script issues CRITICAL_FAIL when description mentions files not in diff
- [ ] Script issues WARNING when major changes are not mentioned
- [ ] Script supports both inline body and file-based body input

#### FR-3: Validated PR Creation Wrapper

The system MUST provide a wrapper script that runs all validations before `gh pr create`.

**Acceptance Criteria**:
- [ ] Wrapper runs FR-1 validation (Session Protocol)
- [ ] Wrapper runs FR-2 validation (PR Description)
- [ ] Wrapper blocks PR creation if either validation fails
- [ ] Wrapper supports `-Force` escape hatch with audit trail

#### FR-4: Test Coverage Detection

The system SHOULD provide a detection script that warns about missing test files.

**Acceptance Criteria**:
- [ ] Script detects new/modified .ps1 files without corresponding .Tests.ps1
- [ ] Script follows documented test location patterns
- [ ] Script integrates with pre-commit hook as WARNING (non-blocking)
- [ ] Script supports ignore file for legitimate exceptions

### Non-Functional Requirements

#### NFR-1: Performance

- Pre-PR validation MUST complete in <5 seconds
- Test coverage detection MUST complete in <2 seconds
- Pre-commit hook total time SHOULD remain <10 seconds

#### NFR-2: Reliability

- Scripts MUST handle edge cases gracefully (no session log, no commits, dirty tree)
- Scripts MUST provide clear error messages for all failure modes
- Scripts MUST NOT leave the repository in an inconsistent state

#### NFR-3: Usability

- Error messages MUST include "WHAT HAPPENED", "WHY IT MATTERS", "HOW TO FIX"
- Escape hatches MUST be documented and auditable
- Integration with Claude Code SHOULD be seamless

#### NFR-4: Maintainability

- Scripts MUST follow PowerShell best practices (ADR-005)
- Scripts MUST include Pester test coverage
- Scripts MUST integrate with existing validation infrastructure

## Design Decisions

### DD-1: PowerShell-Only Implementation

All scripts will be PowerShell (.ps1) per ADR-005: PowerShell-Only Scripting Standard.

**Rationale**: Consistency with existing validation scripts, security hardening.

### DD-2: Reuse Existing Validation Scripts

Pre-PR validation will call existing Validate-SessionEnd.ps1 rather than duplicating logic.

**Rationale**: DRY principle, single source of truth for Session Protocol validation.

### DD-3: Non-Blocking Test Coverage Detection

Test coverage detection will be WARNING (non-blocking) in pre-commit.

**Rationale**: Low false positive rate preferred over aggressive enforcement. QA agent provides deeper analysis if needed.

### DD-4: Pedagogical Error Messages

All error messages will follow the pattern: WHAT HAPPENED → WHY IT MATTERS → HOW TO FIX.

**Rationale**: Aligns with Skill-Validation-002 pattern, guides correction rather than just flagging.

## Scope Exclusions

The following are explicitly out of scope:

1. **Test execution** - Only file presence checking, not running tests
2. **Deep code analysis** - No static analysis beyond pattern matching
3. **Remote API calls** - All validation is local-only
4. **Blocking security warnings** - Security detection remains WARNING

## Dependencies

| Dependency | Type | Status |
|-----------|------|--------|
| Validate-SessionEnd.ps1 | Internal | Available |
| Validate-SessionProtocol.ps1 | Internal | Available |
| markdownlint-cli2 | External | Available |
| PowerShell 7+ | Runtime | Required |
| gh CLI | Runtime | Required |

## Success Criteria

| Metric | Current | Target | Measurement |
|--------|---------|--------|-------------|
| Session Protocol CRITICAL_FAIL rate | 60% | <5% | CI workflow results |
| AI Quality Gate cost per violation | 6 requests | 0 | GitHub Copilot usage |
| Analyst CRITICAL_FAIL rate | 10% | <2% | CI workflow results |
| QA WARN rate | 40% | <15% | CI workflow results |
| Pre-PR validation bypass rate | N/A | <10% | Script audit logs |

## References

- `.agents/SESSION-PROTOCOL.md` - Session Protocol requirements
- `.github/workflows/ai-pr-quality-gate.yml` - AI Quality Gate workflow
- `.github/prompts/pr-quality-gate-*.md` - Agent prompt files
- `.githooks/pre-commit` - Pre-commit hook (ADR-004)
- `scripts/Validate-SessionEnd.ps1` - Existing validation script
