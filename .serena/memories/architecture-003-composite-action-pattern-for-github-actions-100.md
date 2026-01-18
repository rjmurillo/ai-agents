# Architecture: Composite Action Pattern For Github Actions 100

## Skill-Architecture-003: Composite Action Pattern for GitHub Actions (100%)

**Statement**: When ≥2 workflows share logic, extract to composite action with parameterized inputs for reusability

**Context**: GitHub Actions workflow design. Apply during architecture phase when duplication detected.

**Trigger**: Designing ≥2 workflows with similar logic

**Evidence**: Session 03 (2025-12-18): 1 composite action (342 LOC) shared by 4 workflows saved ~1,368 LOC. Single reusable `ai-review` action with parameterized inputs (agent, prompt-file, context) eliminated duplication.

**Atomicity**: 100%

- Specific trigger (≥2 workflows) ✓
- Single concept (composite action extraction) ✓
- Actionable (create composite action) ✓
- Measurable (LOC saved = action LOC × uses - action LOC) ✓

**Impact**: 9/10 - High reusability, reduced maintenance burden

**Category**: CI/CD Architecture

**Tag**: helpful

**Created**: 2025-12-18

**Validated**: 1 (AI Workflow Implementation session)

**Pattern**:

```yaml
# .github/actions/my-action/action.yml
name: My Reusable Action
inputs:
  param1:
    description: 'Parameterized input'
    required: true
runs:
  using: composite
  steps:
    - name: Step 1
      shell: bash
      run: echo "${{ inputs.param1 }}"
```

**Usage in Workflows**:

```yaml
- uses: ./.github/actions/my-action
  with:
    param1: value
```

---

## Related

- [architecture-001-rolespecific-tool-allocation-92](architecture-001-rolespecific-tool-allocation-92.md)
- [architecture-002-model-selection-by-complexity-85](architecture-002-model-selection-by-complexity-85.md)
- [architecture-003-dry-exception-deployment](architecture-003-dry-exception-deployment.md)
- [architecture-004-producerconsumer-prompt-coordination-90](architecture-004-producerconsumer-prompt-coordination-90.md)
- [architecture-015-deployment-path-validation](architecture-015-deployment-path-validation.md)
