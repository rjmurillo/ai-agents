# Matrix Strategy with Artifacts Pattern

**Statement**: Use artifacts (not job outputs) for parallel matrix processing

**Context**: Parallel validation jobs that need to share results

**Evidence**: Job outputs only expose one leg of a matrix

**Atomicity**: 92%

**Impact**: 8/10

## Implementation

```yaml
jobs:
  detect-changes:
    outputs:
      files: ${{ steps.find.outputs.json_array }}

  validate:
    needs: detect-changes
    strategy:
      matrix:
        file: ${{ fromJson(needs.detect-changes.outputs.files) }}
    steps:
      - uses: actions/upload-artifact@v4
        with:
          name: result-${{ hashFiles(matrix.file) }}
          path: validation-results/

  aggregate:
    needs: [detect-changes, validate]
    steps:
      - uses: actions/download-artifact@v4
        with:
          pattern: result-*
          merge-multiple: true
```

## Common Mistake

Using job outputs with matrix - only one matrix leg populates outputs. Use artifacts instead.
