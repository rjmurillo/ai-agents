# Architecture ADR Compliance Documentation

## Skill-Architecture-016: ADR Reference in Workflow Comments (88%)

**Statement**: Document ADR reference in workflow comments when selecting non-default CI runners

**Context**: When choosing runners other than ubuntu-latest (e.g., ARM, Windows, macOS). Non-obvious runner choices require justification for maintainability and audit trail.

**Evidence**: PR #342 Copilot review: "Add ADR-014 comment explaining ARM runner selection"; compliance added at lines 34-35

**Pattern**:

```yaml
jobs:
  build:
    # ADR-014: Use ubuntu-24.04-arm to align with standardized ARM runners for CI.
    # ARM runners are selected here for cost-optimized, consistent validation workloads.
    runs-on: ubuntu-24.04-arm
```

**When to Document**:

| Runner Choice | Requires ADR Comment? | Example ADR |
|---------------|----------------------|-------------|
| `ubuntu-latest` | No (default) | N/A |
| `ubuntu-24.04-arm` | Yes | ADR-014 (cost optimization) |
| `windows-latest` | Yes | Explain why Windows needed |
| `macos-latest` | Yes | Explain why macOS needed |
| `self-hosted` | Yes | Security/compliance ADR |

**Benefits**:

1. **Maintainability**: Future developers understand why non-default runner was chosen
2. **Audit trail**: Architectural decisions visible in workflow itself
3. **Review efficiency**: Reviewers can validate against ADR without asking questions
4. **Consistency**: Prevents drift from documented standards

**Anti-Pattern**:

```yaml
# BAD: No explanation for non-default runner
runs-on: ubuntu-24.04-arm
```

**Copilot Review Trigger**: Copilot will comment if ADR reference missing for non-default runners

---

## Related ADRs

- **ADR-014**: ARM Runner Standardization (cost optimization, consistent CI)
- **ADR-006**: Thin Workflows, Testable Modules (workflow design patterns)

## Related Files

- `ci-runner-selection` - Runner performance and cost comparison
- `ci-deployment-validation` - Deployment workflow patterns
