# Critique: Milestone Tracking Automation

**Date**: 2026-01-09
**Branch**: feat/milestone-backstop
**Critique Document**: `.agents/critique/milestone-tracking-critique.md`
**Verdict**: NEEDS REVISION

## Key Findings

### Critical Issues

1. **Untested delegation pattern**: Set-ItemMilestone.ps1 delegates to Set-IssueMilestone.ps1 but integration tests are incomplete. Both scripts check milestone existence (double validation). Exit code 5 from skill conflicts with orchestrator skip logic.

2. **No semantic milestone fallback**: If repo has zero semantic milestones, workflow fails with exit 2. No graceful degradation or auto-creation. Adoption friction for new repositories.

3. **Race condition risk**: PR close + issue close can trigger concurrent runs for same item. No concurrency control in workflow. Potential API rate limit exhaustion.

### Important Issues

4. **Missing -Force parameter**: Skip logic preserves manual assignments but provides no override mechanism for bulk milestone migrations.

5. **Detection script location**: Get-LatestSemanticMilestone.ps1 lives in scripts/ (workflow-specific) but is general-purpose (reusable). Should be in .claude/skills/github/scripts/milestone/.

6. **Test coverage gaps**: Mock fidelity is low. Tests acknowledge integration gaps with "would verify end-to-end behavior" comments.

7. **No cost analysis**: Workflow runs on all branches (ARM runner) but no data on cost vs. benefit. Main branch filtering may be sufficient.

8. **Semantic version pattern too restrictive**: Regex only matches X.Y.Z, not pre-release versions (1.0.0-beta).

### Minor Issues

9. **GITHUB_OUTPUT validation**: No write failure detection if environment variable unset or file read-only.

10. **No rate limit handling**: API calls without pre-flight rate limit checks.

11. **Markdown injection risk**: Step summary includes milestone titles without sanitization.

## Architectural Trade-Offs

### Semantic Version Auto-Detection

**Pro**: Flexible, no hardcoded names, convention-driven
**Con**: Assumes semantic versioning adoption, fails if convention not followed
**Recommendation**: Add -CreateIfMissing or -FallbackMilestone parameter

### Skip Existing Milestones

**Pro**: Preserves manual curation, non-invasive, idempotent
**Con**: No force-update mechanism for bulk operations
**Recommendation**: Add -Force parameter for override scenarios

### Separate Detection Script

**Pro**: Reusable, testable in isolation
**Con**: Extra file to maintain, indirection in orchestration
**Recommendation**: Move to .claude/skills/github/ for cross-repo reuse

### Delegate to Set-IssueMilestone.ps1 Skill

**Pro**: DRY principle, skill has validation and error handling
**Con**: Double validation (orchestrator + skill), exit code conflict potential
**Recommendation**: Either refactor to use skill -Force OR document defense-in-depth rationale

### Support All Branches

**Pro**: Comprehensive tracking, unified milestone management
**Con**: Higher workflow cost (ARM runner time), potentially unnecessary for feature branches
**Recommendation**: Analyze run frequency per branch, filter to main if >80% are feature branches

## Pre-PR Readiness Gaps

1. **CI simulation**: No evidence of manual workflow trigger testing
2. **Environment variables**: GH_TOKEN requirement not documented in workflow README
3. **Protected branch testing**: No validation on protected branch with required status checks

**Recommendation**: Add workflow_dispatch trigger for manual testing before PR.

## Approval Conditions

Before merging:
- Integration tests for skill delegation OR rationale documented
- Concurrency control added to workflow
- -Force parameter implemented OR documented as future enhancement
- Detection script location rationale documented
- README added with semantic milestone prerequisite
- Cost analysis completed OR main branch filtering implemented

## Alternative Approaches Considered

1. **GitHub Projects V2**: Use custom fields for version tracking (more flexible, higher complexity)
2. **Hardcoded milestone**: Follow moq.analyzers "vNext" pattern (simpler, less flexible)
3. **Label-based tracking**: Use labels instead of milestones (no limit, loses UI)

## Strengths Acknowledged

- ADR compliance: PowerShell-only (ADR-005), thin workflows (ADR-006), exit codes (ADR-035)
- Comprehensive Pester test structure
- DRY delegation to existing skill
- Structured output to GITHUB_OUTPUT
- Proper version comparison using [System.Version]
- Clear step summaries for CI feedback

## Related Memories

- ci-infrastructure-milestone-tracking (implementation context)
- usage-mandatory (skill delegation requirement)
- pattern-thin-workflows (workflow architecture)
- validation-pre-pr-checklist (pre-PR gates)

## Session Reference

Critique session: 2026-01-09
Next action: Route to planner for revision addressing critical issues
