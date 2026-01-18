# Architecture: Workflow Simplification Preference

## Skill-Architecture-016: Workflow Simplification Preference

**Statement**: When resolving workflow merge conflicts, prefer simpler single-script approach over multi-step complexity

**Atomicity**: 87%

**Context**: Merge conflict in workflow files where one version simplified steps into script

**Evidence**: PR #296 - Conflict between feature branch's multi-step workflow (synthesize, prepare steps) and main's simplified single-script approach, accepted simpler version (commit 378ff4a)

**Trigger**: Merge conflict in .github/workflows/*.yml where main has simplified workflow steps

**Principle**: Simplicity over complexity in workflow design (thin workflows pattern)

**Related Skills**:
- pattern-thin-workflows
- Skill-Git-001 (pre-commit validation)
- Skill-Analysis-001 (comprehensive analysis)

**SMART Validation**:
- Specific: Y - One concept: workflow simplification preference
- Measurable: Y - PR #296 conflict resolved, merge successful
- Attainable: Y - Standard git conflict resolution
- Relevant: Y - Applies to workflow refactoring conflicts
- Timely: Y - Trigger: Merge conflict in workflow files

## Iteration 5 Summary

**PRs Addressed**: 3
- PR #235: Session protocol fix (ADR-014 legacy session)
- PR #298: Pester tests trigger (path filter workaround)
- PR #296: Merge conflict resolution (workflow simplification)

**Success Rate**: 100% (all PRs unblocked/fixed)

**Skills Extracted**: 3 novel patterns
- 1 Governance skill (legacy session remediation)
- 1 CI Infrastructure skill (required check bypass)
- 1 Architecture skill (workflow simplification)

**ROTI**: 3/4 (High return)

**Patterns Identified**:
1. ADR-014 Legacy Session Logs - Sessions before ADR adoption need remediation
2. Path-Filtered Required Checks - Manual triggers needed for path-filtered required checks
3. Workflow Refactoring Drift - Accept simpler approach when resolving workflow conflicts

**Recommended Memory Files**:
- `.serena/memories/skills-governance.md` - Add Skill-Governance-010
- `.serena/memories/skills-ci-infrastructure.md` - Add Skill-CI-Infrastructure-006
- `.serena/memories/skills-architecture.md` - Add Skill-Architecture-016

## Related

- [architecture-001-rolespecific-tool-allocation-92](architecture-001-rolespecific-tool-allocation-92.md)
- [architecture-002-model-selection-by-complexity-85](architecture-002-model-selection-by-complexity-85.md)
- [architecture-003-composite-action-pattern-for-github-actions-100](architecture-003-composite-action-pattern-for-github-actions-100.md)
- [architecture-003-dry-exception-deployment](architecture-003-dry-exception-deployment.md)
- [architecture-004-producerconsumer-prompt-coordination-90](architecture-004-producerconsumer-prompt-coordination-90.md)
