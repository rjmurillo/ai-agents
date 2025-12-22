# dorny/paths-filter Checkout Requirement

**Date Learned**: 2025-12-20
**Source**: PR #121, PR #100
**Confidence**: High (owner-confirmed)

## The Lesson

When using the `dorny/paths-filter` action to implement conditional workflow execution with required status checks, **checkout is required in ALL jobs that interact with the pattern**, including:

1. **The check-paths job** - Required for paths-filter to read the repository and analyze file changes
2. **The skip job** - Required for consistency and proper workflow function

## Why This Matters

**User Impact**: Without proper checkout setup in all jobs using the dorny/paths-filter pattern, workflows may fail unexpectedly or produce incorrect results when attempting to skip based on file changes.

From PR #100 analysis:
- `dorny/paths-filter` compares changes against a base ref
- Without checkout, the action cannot read repository contents
- The pattern of "run on all PRs, filter internally" requires consistent setup across jobs

## The Anti-Pattern (WRONG)

```yaml
skip-review:
  name: Aggregate Results
  if: needs.check-changes.outputs.should-run != 'true'
  runs-on: ubuntu-latest
  steps:
    # NO CHECKOUT - This is WRONG!
    - name: Skip message
      run: echo "Skipped"
```

## The Correct Pattern

```yaml
skip-review:
  name: Aggregate Results
  if: needs.check-changes.outputs.should-run != 'true'
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5  # Required for dorny/paths-filter pattern
    
    - name: Skip message
      run: echo "Skipped"
```

## Evidence

- **PR #100**: Discovered that dorny/paths-filter requires checkout for proper function
- **PR #121**: Copilot incorrectly suggested removing checkout from skip job
- **Owner feedback**: "This is incorrect. This is required for `dorny/paths-filter`"

## Related Patterns

- `pester-tests.yml` - Reference implementation with check-paths + skip-tests jobs
- `ai-pr-quality-gate.yml` - Uses same pattern for check-changes + skip-review jobs
- `ai-spec-validation.yml` - Candidate workflow for future adoption of this pattern (currently does not use `dorny/paths-filter`)

## Applies To

Any workflow using the "paths-filter internal filtering" pattern where:
1. Workflow triggers on ALL PRs (no `paths:` filter at trigger level)
2. `dorny/paths-filter` used internally to detect relevant changes
3. Skip job satisfies required status checks when no relevant files changed
