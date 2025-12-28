# PRD: Pre-PR Security Gate

**Version**: 1.0
**Date**: 2025-12-16
**Author**: Orchestrator Agent
**Status**: Draft

## Problem Statement

During PR #41 implementation, a new GitHub Actions workflow was created without security review, resulting in:

1. Missing workflow permissions (CodeQL alert)
2. Process gap where infrastructure changes bypassed security agent

The multi-agent workflow did not detect that adding `.github/workflows/pester-tests.yml` was a multi-domain change requiring devops and security agent consultation.

## Goals

1. **Automatic Detection**: Identify infrastructure file changes that require security review
2. **Pre-PR Validation**: Validate security patterns before PR creation
3. **Process Integration**: Integrate security checks into existing agent workflows
4. **Reduce Security Debt**: Prevent security issues from reaching PR review

## Non-Goals

- Replace CodeQL or other SAST tools (complementary, not replacement)
- Block all PRs without human approval (automation, not gatekeeping)
- Perform deep security analysis (pattern matching, not vulnerability scanning)

## User Stories

### US-1: Orchestrator Detects Infrastructure Changes

**As an** orchestrator agent
**I want to** automatically detect when implementation touches infrastructure files
**So that** I can route to the appropriate specialist agents (devops, security)

**Acceptance Criteria**:

- Detect files matching `.github/workflows/*`
- Detect files matching `.github/actions/*`
- Detect files matching `**/Dockerfile*`
- Detect files matching `**/*.yml` in CI/CD directories
- Trigger multi-domain impact analysis workflow

### US-2: Security Agent Reviews Workflow Files

**As a** security agent
**I want to** review new or modified GitHub Actions workflows
**So that** I can identify security issues before PR creation

**Acceptance Criteria**:

- Check for explicit `permissions` block
- Validate permissions follow least privilege
- Check for secrets exposure risks
- Check for pull_request_target with checkout (dangerous pattern)
- Output security review document

### US-3: Pre-Commit Security Validation

**As a** developer (human or agent)
**I want to** validate security patterns locally
**So that** I catch issues before pushing

**Acceptance Criteria**:

- PowerShell script for Windows
- Python script for cross-platform
- Check workflow files for common security patterns
- Non-blocking (warnings, not errors)
- Integrate with existing pre-commit hook

### US-4: Orchestrator Routes Infrastructure to DevOps

**As an** orchestrator agent
**I want to** automatically consult the devops agent for infrastructure changes
**So that** CI/CD changes are properly reviewed

**Acceptance Criteria**:

- Recognize infrastructure file patterns
- Include devops in impact analysis for infrastructure changes
- Document devops review in planning artifacts

## Technical Requirements

### TR-1: Infrastructure File Pattern Detection

**Location**: `src/claude/orchestrator.md` (and other platform variants)

**Implementation**:

```markdown
## Infrastructure File Patterns

The following file patterns indicate infrastructure changes requiring specialist review:

| Pattern | Specialist Agents |
|---------|-------------------|
| `.github/workflows/*` | devops, security |
| `.github/actions/*` | devops, security |
| `**/Dockerfile*` | devops, security |
| `.githooks/*` | devops |
| `*.yml` in `.github/` | devops, security |
| `azure-pipelines.yml` | devops, security |
| `.gitlab-ci.yml` | devops, security |
```

### TR-2: Workflow Security Patterns

**Location**: `.agents/security/workflow-security-patterns.md`

**Patterns to Validate**:

```yaml
# REQUIRED: Explicit permissions block
permissions:
  contents: read

# DANGEROUS: pull_request_target with checkout
on:
  pull_request_target:
# Warning if followed by:
- uses: actions/checkout@v4
  with:
    ref: ${{ github.event.pull_request.head.sha }}  # DANGEROUS

# REQUIRED for test reporters: checks write permission
permissions:
  checks: write  # Needed for dorny/test-reporter

# WARNING: Overly permissive
permissions: write-all  # AVOID
```

### TR-3: Pre-Commit Validation Script

**Location**: `.claude/skills/security-detection/validate-workflows.ps1`

**Usage**:

```powershell
# Validate all workflow files
pwsh .claude/skills/security-detection/validate-workflows.ps1

# Validate specific file
pwsh .claude/skills/security-detection/validate-workflows.ps1 -Path .github/workflows/pester-tests.yml
```

### TR-4: Orchestrator Routing Update

Update orchestrator routing table:

| If task involves... | Task Type | Agents Required |
|---------------------|-----------|-----------------|
| `.github/workflows/*` | Infrastructure | devops, security, qa |
| `.github/actions/*` | Infrastructure | devops, security |
| `Dockerfile*` | Infrastructure | devops, security |

## Implementation Plan

### Phase 1: Documentation (Low Effort)

1. Add workflow security patterns to `.agents/security/`
2. Update orchestrator documentation with infrastructure routing
3. Document in CLAUDE.md

### Phase 2: Validation Scripts (Medium Effort)

1. Create `validate-workflows.ps1` utility
2. Create `validate_workflows.py` utility
3. Add SKILL.md documentation
4. Integrate with pre-commit hook (optional)

### Phase 3: Agent System Updates (Medium Effort)

1. Update `src/claude/orchestrator.md` routing rules
2. Update `src/copilot-cli/orchestrator.agent.md`
3. Update `src/vs-code-agents/orchestrator.agent.md`
4. Add security review templates

## Success Metrics

| Metric | Target |
|--------|--------|
| Infrastructure changes auto-routed to devops | 100% |
| Security issues caught pre-PR | >80% |
| CodeQL workflow alerts | 0 new alerts |
| Developer friction | Minimal (warnings only) |

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Over-alerting causes alert fatigue | Use warnings, not errors; tune patterns |
| Slows down development | Pre-commit is optional; routing is fast |
| Patterns become outdated | Regular review of security patterns |

## Dependencies

- Existing orchestrator agent system
- Pre-commit hook infrastructure (already in place)
- Security agent definitions

## Timeline

| Phase | Duration | Deliverables |
|-------|----------|--------------|
| Phase 1 | 1 day | Documentation updates |
| Phase 2 | 2 days | Validation scripts |
| Phase 3 | 1 day | Agent system updates |

## References

- [GitHub: Automatic token authentication](https://docs.github.com/en/actions/security-for-github-actions/security-guides/automatic-token-authentication)
- [GitHub: Security hardening for GitHub Actions](https://docs.github.com/en/actions/security-for-github-actions/security-guides/security-hardening-for-github-actions)
- [PR #41 Issue Analysis](../analysis/pr41-issue-analysis.md)

## Appendix: PR #41 Gap Analysis

The security gap in PR #41 occurred because:

1. **No infrastructure file detection**: Orchestrator did not recognize workflow files as requiring security review
2. **Multi-domain change not detected**: Adding CI/CD is infrastructure + security + quality
3. **No pre-PR validation**: Security patterns were not validated locally

This PRD addresses all three gaps.
