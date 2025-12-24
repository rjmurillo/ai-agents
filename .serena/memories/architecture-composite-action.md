# Skill-Architecture-003: Composite Action Pattern

**Statement**: When 2+ workflows share logic, extract to composite action with parameterized inputs

**Context**: GitHub Actions workflow design

**Evidence**: Session 03: 1 composite action (342 LOC) shared by 4 workflows saved ~1,368 LOC

**Atomicity**: 100%

**Impact**: 9/10

## Pattern

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

## Usage in Workflows

```yaml
- uses: ./.github/actions/my-action
  with:
    param1: value
```

## When to Apply

- Trigger: 2+ workflows with similar logic
- Measurable: LOC saved = action LOC × uses - action LOC
