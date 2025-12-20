# Pull Request

## Summary

<!-- Brief description of changes -->

## Specification References

<!-- Enable AI spec-to-implementation traceability -->
<!-- The ai-spec-validation workflow checks for these references -->

| Type | Reference | Description |
|------|-----------|-------------|
| **Issue** | Closes #<!-- issue number --> | <!-- Issue title --> |
| **Spec** | `.agents/planning/...` | <!-- Planning document --> |
| **Spec** | `.agents/specs/...` | <!-- Spec document (if applicable) --> |

### Spec Requirement Guidelines

| PR Type | Spec Required? | Guidance |
|---------|----------------|----------|
| **Feature** (`feat:`, `feat(scope):`) | ✅ Required | Link issue, REQ-*, or spec file in `.agents/planning/` |
| **Bug fix** (`fix:`, `fix(scope):`) | Optional | Link issue if exists; explain root cause if complex |
| **Refactor** (`refactor:`, `refactor(scope):`) | Optional | Explain rationale and scope in PR description |
| **Documentation** (`docs:`) | Not required | N/A |
| **Infrastructure** (`ci:`, `build:`, `chore:`) | Optional | Link ADR or design doc if architecture impacted |

<!--
Supported reference formats:
- Issues: "Closes #123", "Fixes #456", "Implements #789"
- Requirements: "REQ-001", "DESIGN-002", "TASK-003"
- Spec files: ".agents/specs/requirements/...", ".agents/planning/..."

For feature PRs: Create spec in .agents/planning/ before submitting if none exists.
For other PRs: Add references when traceability adds value.
-->

## Changes

<!-- Bulleted list of changes -->

-

## Type of Change

- [ ] Bug fix (non-breaking change fixing an issue)
- [ ] New feature (non-breaking change adding functionality)
- [ ] Breaking change (fix or feature causing existing functionality to change)
- [ ] Documentation update
- [ ] Infrastructure/CI change
- [ ] Refactoring (no functional changes)

## Testing

- [ ] Tests added/updated
- [ ] Manual testing completed
- [ ] No testing required (documentation only)

## Agent Review

<!-- Check applicable boxes for agent-assisted development -->

### Security Review

> Required for: Authentication, authorization, CI/CD, git hooks, secrets, infrastructure

- [ ] No security-critical changes in this PR
- [ ] Security agent reviewed infrastructure changes
- [ ] Security agent reviewed authentication/authorization changes
- [ ] Security patterns applied (see `.agents/security/`)

**Files requiring security review:**

<!-- List security-critical files if any:
- .github/workflows/...
- .githooks/...
- **/Auth/**/...
-->

### Other Agent Reviews

- [ ] Architect reviewed design changes
- [ ] Critic validated implementation plan
- [ ] QA verified test coverage

## Checklist

- [ ] Code follows project style guidelines
- [ ] Self-review completed
- [ ] Comments added for complex logic
- [ ] Documentation updated (if applicable)
- [ ] No new warnings introduced

## Related Issues

<!-- Link related issues: Fixes #123, Closes #456 -->

---

<!-- Optional: Add screenshots for UI changes -->
