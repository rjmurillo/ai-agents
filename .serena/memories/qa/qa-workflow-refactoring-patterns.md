# QA: Workflow Refactoring Patterns

## Context

Testing GitHub Actions workflow refactorings requires different approach than code QA.

## Pattern: Static Analysis for Workflow Refactoring

When verifying workflow changes that don't affect business logic:

1. **Syntax Validation**: `gh workflow view <name> --yaml` to verify YAML valid
2. **Diff Analysis**: Compare before/after to identify changes
3. **API Compliance**: Verify action parameters against official docs
4. **Contract Preservation**: Confirm required status checks maintained
5. **Edge Case Review**: Check conditional logic for special cases (workflow_dispatch, etc.)

**When Sufficient**: Refactorings that reorganize without changing behavior
**When Insufficient**: Logic changes, new integrations, or critical path modifications

## Evidence Levels

| Level | Confidence | Sufficient For |
|-------|------------|----------------|
| Static analysis only | Medium | Non-critical refactorings |
| Static + CI run | High | Most workflow changes |
| Static + CI + integration test | Very High | Critical path changes |

## Issue #144 Learnings

**Problem**: Path list duplication in workflow (filter config vs echo output)
**Solution**: Single source in filter config, skip-tests references source
**QA Approach**: Static analysis sufficient for deduplication verification
**Gap**: No CI run yet, so recommend P1 before merge
**Unused Output**: Declared API (`testable-paths`) acceptable if documented as future use

## Red Flags in Workflow Refactoring

- Required status checks removed or renamed
- Conditional logic altered without clear justification
- Action API parameters not verified against official docs
- Edge cases (workflow_dispatch, manual triggers) not tested

## Related

- [qa-007-worktree-isolation-verification](qa-007-worktree-isolation-verification.md)
- [qa-benchmark-script-validation](qa-benchmark-script-validation.md)
- [qa-session-protocol-validation-patterns](qa-session-protocol-validation-patterns.md)
